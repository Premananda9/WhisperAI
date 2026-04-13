try:
    import whisper
except ImportError:  # Whisper may not be available on all Python versions
    whisper = None

import os
import json
import time
import re
import shutil
import tempfile
from typing import List, Dict, Any

import requests

# Ensure output directory exists (Safety Constraint)
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CONNECT_TIMEOUT_SEC = float(os.getenv("OLLAMA_CONNECT_TIMEOUT_SEC", "10"))
OLLAMA_READ_TIMEOUT_SEC = float(os.getenv("OLLAMA_READ_TIMEOUT_SEC", "300"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))
OLLAMA_RETRY_BACKOFF_SEC = float(os.getenv("OLLAMA_RETRY_BACKOFF_SEC", "1.5"))
OLLAMA_MODEL_INTENT = os.getenv("OLLAMA_MODEL_INTENT", "llama3")
OLLAMA_MODEL_CODE = os.getenv("OLLAMA_MODEL_CODE", "llama3")

ALLOWED_INTENTS = {"create_file", "write_code", "summarize", "general_chat"}

# Lightweight runtime memory so follow-up commands (e.g. "summarize") can
# reuse the previous question/code even if explicit text is omitted.
RUNTIME_MEMORY = {
    "last_raw_text": "",
    "last_generated_code": "",
    "last_generated_code_language": "",
    "last_generated_code_file": "",
    "last_code_requirement": "",
}


def _ensure_ffmpeg_available():
    """Ensure an ffmpeg executable is reachable for Whisper.

    Whisper shells out to the `ffmpeg` command when reading audio.
    If system ffmpeg is not installed, fall back to imageio-ffmpeg's bundled binary.
    """
    existing = shutil.which("ffmpeg")
    if existing:
        return existing

    try:
        import imageio_ffmpeg  # type: ignore

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        # Whisper invokes "ffmpeg" by name. imageio-ffmpeg ships a versioned
        # executable filename (e.g. ffmpeg-win-x86_64-v7.1.exe), so create a
        # stable alias named ffmpeg.exe and prepend its folder to PATH.
        alias_dir = os.path.join(tempfile.gettempdir(), "local_voice_agent_bin")
        os.makedirs(alias_dir, exist_ok=True)
        alias_exe = os.path.join(alias_dir, "ffmpeg.exe")

        if not os.path.exists(alias_exe):
            shutil.copy2(ffmpeg_exe, alias_exe)

        os.environ["PATH"] = alias_dir + os.pathsep + os.environ.get("PATH", "")

        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg alias could not be resolved on PATH.")
        return alias_exe
    except Exception as e:
        raise RuntimeError(
            "ffmpeg is required for audio transcription but was not found. "
            "Install ffmpeg or add imageio-ffmpeg to the environment."
        ) from e


def _ollama_chat(
    model: str,
    messages: List[Dict[str, Any]],
    *,
    options: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Minimal HTTP client for a local Ollama server.

    This avoids needing the `ollama` Python package and instead talks to
    the default local server at http://127.0.0.1:11434.
    """
    last_error = None
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
    }
    if options:
        payload["options"] = options

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=(OLLAMA_CONNECT_TIMEOUT_SEC, OLLAMA_READ_TIMEOUT_SEC),
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            last_error = e
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            # Retry transient server-side errors.
            if status is not None and 500 <= status < 600:
                last_error = e
            else:
                raise RuntimeError(f"Error calling local Ollama server: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Error calling local Ollama server: {e}") from e

        if attempt < OLLAMA_MAX_RETRIES:
            time.sleep(OLLAMA_RETRY_BACKOFF_SEC * attempt)

    raise RuntimeError(
        "Error calling local Ollama server: request timed out or connection failed "
        f"after {OLLAMA_MAX_RETRIES} attempt(s). Last error: {last_error}"
    )


def _extract_first_json_object(raw_text: str) -> Dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object detected in model output.")
    return json.loads(raw_text[start : end + 1])


def _strip_code_fences(text: str) -> str:
    """Remove optional markdown fences from model code output."""
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _normalize_commands(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    commands = data.get("commands")
    if not isinstance(commands, list):
        intent = data.get("intent", "general_chat")
        params = data.get("parameters", {})
        commands = [{"intent": intent, "parameters": params}]

    normalized: List[Dict[str, Any]] = []
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        intent = str(cmd.get("intent", "general_chat")).strip().lower()
        if intent not in ALLOWED_INTENTS:
            intent = "general_chat"
        params = cmd.get("parameters", {})
        if not isinstance(params, dict):
            params = {}
        normalized.append({"intent": intent, "parameters": params})

    if not normalized:
        normalized = [{"intent": "general_chat", "parameters": {}}]
    return normalized


def _infer_language_from_text(text: str) -> str:
    t = text.lower()
    if "java" in t:
        return "java"
    if "python" in t:
        return "python"
    if "javascript" in t or "js" in t:
        return "javascript"
    if "c++" in t or "cpp" in t:
        return "cpp"
    return "python"


def _looks_like_code_request(text: str) -> bool:
    t = text.lower()
    keywords = [
        "write",
        "code",
        "program",
        "java",
        "python",
        "algorithm",
        "print",
        "palindrome",
        "function",
        "class",
    ]
    return any(k in t for k in keywords)


def _extract_filename_from_text(text: str) -> str:
    """Extract a likely filename from free-form text."""
    t = _safe_text(text)
    if not t:
        return ""

    match = re.search(r"\b([A-Za-z0-9_\-]+\.(txt|md|py|java|json|csv|log))\b", t, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _rule_based_commands(text: str) -> List[Dict[str, Any]]:
    """Deterministic fallback intent detection for critical intents."""
    raw = _safe_text(text)
    t = raw.lower()
    commands: List[Dict[str, Any]] = []

    create_markers = ["create file", "make file", "new file", "create a file", "make a file"]
    write_markers = [
        "write code",
        "generate code",
        "create code",
        "write a program",
        "build a program",
        "implement",
        "algorithm",
        "function",
        "class",
    ]

    wants_create = any(m in t for m in create_markers)
    wants_write = any(m in t for m in write_markers) or _looks_like_code_request(raw)

    if wants_create:
        filename = _extract_filename_from_text(raw) or "notes.txt"
        commands.append({"intent": "create_file", "parameters": {"filename": filename}})

    if wants_write:
        language = _infer_language_from_text(raw)
        default_filename = "Main.java" if language == "java" else "code.py"
        filename = _extract_filename_from_text(raw) or default_filename
        commands.append(
            {
                "intent": "write_code",
                "parameters": {
                    "language": language,
                    "filename": filename,
                    "description": raw,
                },
            }
        )

    return commands


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _is_placeholder_text(text: str) -> bool:
    t = _safe_text(text).lower()
    if not t:
        return True
    placeholders = {
        "it",
        "this",
        "that",
        "these",
        "those",
        "same",
        "same thing",
        "summarize",
        "summarize it",
        "summarize this",
        "explain it",
        "explain this",
    }
    return t in placeholders


def _looks_like_empty_or_apology_response(text: str) -> bool:
    t = _safe_text(text).lower()
    if not t:
        return True
    weak_markers = [
        "i apologize",
        "didn't provide any text",
        "did not provide any text",
        "please share the text",
        "no text provided",
        "cannot summarize",
        "can't summarize",
    ]
    return any(marker in t for marker in weak_markers)


def _build_question_explanation(question: str, requirement: str, language: str, source_file: str) -> str:
    q = _safe_text(question)
    req = _safe_text(requirement)
    lang = _safe_text(language) or "auto"
    src = _safe_text(source_file) or "generated source"

    focus = req or q or "User requested a coding task."
    return (
        "Question Explanation:\n"
        f"- User request: {focus}\n"
        f"- Expected implementation language: {lang}\n"
        f"- Output file: {src}\n"
        "- Goal: Implement the requested logic correctly and produce runnable code.\n"
        "- Verification: Check constraints, edge cases, and correctness of output."
    )


def _load_latest_generated_code_from_output() -> tuple[str, str, str]:
    """Best-effort fallback to pick latest generated source from output/."""
    candidates = [
        ("java", "Main.java"),
        ("python", "code.py"),
    ]
    best = ("", "", "")
    best_mtime = -1.0

    for lang, name in candidates:
        path = os.path.join(OUTPUT_DIR, name)
        if not os.path.exists(path):
            continue
        try:
            mtime = os.path.getmtime(path)
            if mtime > best_mtime:
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
                best = (src, lang, path)
                best_mtime = mtime
        except Exception:
            continue

    return best


def _refine_code_requirement(raw_text: str, language: str) -> str:
    """Convert noisy/transcribed requests into a clean coding requirement.

    This prevents literal sentence copying into code output and preserves
    constraints like ranges, conditions, and expected behavior.
    """
    prompt = f"""
    You are a coding requirement normalizer.
    Rewrite the user request as a precise implementation requirement.

    Rules:
    - Preserve exact constraints (ranges, conditions, edge cases).
    - Correct obvious speech-to-text mistakes.
    - Keep it concise and implementation-focused.
    - Do NOT add new requirements.
    - Return plain text only.

    Target language: {language or 'auto'}
    User request: {raw_text}
    """

    try:
        response = _ollama_chat(
            OLLAMA_MODEL_INTENT,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": 180,
            },
        )
        refined = response["message"]["content"].strip()
        return refined or raw_text
    except Exception:
        return raw_text


def _find_missing_constraints(requirement: str, code: str) -> List[str]:
    """Detect obvious missing constraints between requirement and generated code."""
    req = (requirement or "").lower()
    src = (code or "").lower()
    missing: List[str] = []

    if "palindrome" in req and not any(k in src for k in ["palindrome", "reverse", "stringbuilder", "while", "% 10"]):
        missing.append("Palindrome-checking logic is missing.")

    if "1 to 200" in req and "200" not in src:
        missing.append("Range boundary up to 200 is missing.")

    if "print" in req and "println" not in src and "print(" not in src:
        missing.append("Output/printing logic appears missing.")

    return missing


def _generate_code_with_repair(description: str, language: str) -> str:
    """Generate code and automatically run one corrective pass if constraints are missed."""
    base_prompt = (
        "You are a senior software engineer writing production-quality code. "
        "Implement the requirement faithfully. "
        "Do not print or hardcode the requirement sentence as output text. "
        "Generate logic that computes the asked result. "
        "If language is Java, return a complete class Main with a main method. "
        "Return ONLY raw source code, no markdown, no explanation. "
        f"Language hint: {language or 'auto'}. "
        "Requirement: "
        f"{description}"
    )

    initial = _ollama_chat(
        OLLAMA_MODEL_CODE,
        messages=[{"role": "user", "content": base_prompt}],
        options={
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": 1100,
            "repeat_penalty": 1.1,
        },
    )
    code = _strip_code_fences(initial["message"]["content"])

    missing = _find_missing_constraints(description, code)
    if not missing:
        return code

    repair_prompt = (
        "Revise the code to satisfy all requirement constraints. "
        "Keep code executable and complete. "
        "Return ONLY raw source code, no markdown, no explanation.\n\n"
        f"Requirement:\n{description}\n\n"
        f"Current code:\n{code}\n\n"
        "Missing constraints:\n"
        + "\n".join(f"- {m}" for m in missing)
    )

    revised = _ollama_chat(
        OLLAMA_MODEL_CODE,
        messages=[{"role": "user", "content": repair_prompt}],
        options={
            "temperature": 0,
            "top_p": 0.9,
            "num_predict": 1300,
            "repeat_penalty": 1.15,
        },
    )
    return _strip_code_fences(revised["message"]["content"])

def transcribe_audio(audio_path):
    """Transcribes the given audio file using a local Whisper model.

    Returns a dict with keys:
    - "text": transcription string (may be empty on failure).
    - "error": None on success, or a human-readable error message.
    - "duration_sec": float processing time to help with benchmarking.
    """
    start = time.time()
    result_data = {"text": "", "error": None, "duration_sec": None}
    # Using 'base' model for speed; can be changed to 'small', 'medium', etc.
    try:
        if whisper is None:
            result_data["error"] = "Local Whisper STT is not available in this environment."
        else:
            _ensure_ffmpeg_available()
            model = whisper.load_model("base")
            result = model.transcribe(audio_path)
            text = (result or {}).get("text", "").strip()
            result_data["duration_sec"] = time.time() - start
            if not text:
                result_data["error"] = "Could not understand audio (silence or unintelligible speech)."
            else:
                result_data["text"] = text
    except Exception as e:
        result_data["error"] = f"Error transcribing audio: {e}"
        result_data["duration_sec"] = time.time() - start
    return result_data

def detect_intent(text):
    """Use a local LLM to classify one or more intents.

    Returns a dict with keys:
    - "commands": list of {"intent", "parameters"} objects.
    - "error": optional error string if graceful fallback was used.

    This supports compound commands such as
    "Summarize this text and save it to summary.txt".
    """
    heuristic_commands = _rule_based_commands(text)

    prompt = f"""
    You are an intent classification system for a local voice agent.
    Analyze the user's input and break it into one or more commands.

    The possible intents for each command are:
    - "create_file": create an empty file or folder.
    - "write_code": generate code and write it to a file.
    - "summarize": summarize provided text; you may optionally include
      an "output_filename" parameter if the user asks to save the summary
      (e.g. "summary.txt").
    - "general_chat": general conversation.

    User Input: "{text}"

        Respond strictly as JSON with this structure:
    {{
      "commands": [
                {{"intent": "create_file", "parameters": {{"filename": "notes.txt"}}}},
                {{"intent": "write_code", "parameters": {{"language": "java", "filename": "Main.java", "description": "..."}}}},
                {{"intent": "summarize", "parameters": {{"text": "...", "output_filename": "summary.txt"}}}}
      ]
    }}

    If you are unsure, return a single command with
    "intent": "general_chat" and an empty "parameters" object.

        Few-shot guidance for high precision on required intents:
        - Input: "create a file named notes.txt"
            Output: {{"commands": [{{"intent": "create_file", "parameters": {{"filename": "notes.txt"}}}}]}}
        - Input: "write java code to print prime numbers"
            Output: {{"commands": [{{"intent": "write_code", "parameters": {{"language": "java", "filename": "Main.java", "description": "write java code to print prime numbers"}}}}]}}
        - Input: "create file todo.txt and write python code to read it"
            Output: {{"commands": [{{"intent": "create_file", "parameters": {{"filename": "todo.txt"}}}}, {{"intent": "write_code", "parameters": {{"language": "python", "filename": "code.py", "description": "write python code to read todo.txt"}}}}]}}

        Important rules:
        - If user asks for code in any language, choose intent "write_code".
                - If user asks to create a file, choose intent "create_file" and extract filename.
        - Preserve all user requirements, constraints, and ranges in parameters.description.
        - Fix obvious speech-to-text spelling mistakes in requirements (example: "palomrum" => "palindrome").
        - Keep JSON valid.

                Heuristic suggestion from deterministic parser (use it unless clearly wrong):
                {json.dumps({"commands": heuristic_commands}, ensure_ascii=True)}
    """

    start = time.time()
    try:
        # Assuming a local Ollama server with model 'llama3'
        response = _ollama_chat(
            OLLAMA_MODEL_INTENT,
            messages=[
                {"role": "user", "content": prompt},
            ],
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": 220,
            },
        )
        llm_duration = time.time() - start
        content = response["message"]["content"]
        data = _extract_first_json_object(content)
        commands = _normalize_commands(data)

        # Deterministic rescue for core intents.
        only_general = len(commands) == 1 and commands[0]["intent"] == "general_chat"
        if only_general and heuristic_commands:
            commands = heuristic_commands

        # Backfill missing filename for create_file if model omitted it.
        for cmd in commands:
            if cmd.get("intent") == "create_file":
                params = cmd.setdefault("parameters", {})
                if not _safe_text(params.get("filename")):
                    params["filename"] = _extract_filename_from_text(text) or "notes.txt"

            if cmd.get("intent") == "write_code":
                params = cmd.setdefault("parameters", {})
                if not _safe_text(params.get("description")):
                    params["description"] = text
                if not _safe_text(params.get("language")):
                    params["language"] = _infer_language_from_text(text)
                if not _safe_text(params.get("filename")):
                    params["filename"] = "Main.java" if params["language"] == "java" else "code.py"

        # Safety net for code requests missed by model and heuristics.
        if only_general and _looks_like_code_request(text):
            commands = [
                {
                    "intent": "write_code",
                    "parameters": {
                        "language": _infer_language_from_text(text),
                        "filename": "Main.java" if _infer_language_from_text(text) == "java" else "code.py",
                        "description": text,
                    },
                }
            ]
        return {"commands": commands, "error": None, "llm_duration_sec": llm_duration}
    except Exception as e:
        # Graceful degradation: fall back to general chat
        return {
            "commands": [{"intent": "general_chat", "parameters": {}}],
            "error": str(e),
            "llm_duration_sec": time.time() - start,
        }

def _execute_single_action(intent, parameters, raw_text, context=None):
    """Execute a single intent.

    Returns (action_taken, final_output, updated_context).
    """
    action_taken = ""
    final_output = ""
    context = dict(context or {})

    if intent == "create_file":
        filename = parameters.get("filename", "default.txt")
        filepath = os.path.join(OUTPUT_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("")
            action_taken = f"Created file: {filepath}"
            final_output = f"Successfully created {filename} in {OUTPUT_DIR}."
        except Exception as e:
            action_taken = "Failed to create file."
            final_output = str(e)

    elif intent == "write_code":
        language = str(parameters.get("language", "")).strip().lower()
        default_filename = "Main.java" if language == "java" else "code.py"
        filename = parameters.get("filename", default_filename)

        # Accept multiple common parameter names from classifier output.
        description = (
            parameters.get("description")
            or parameters.get("code")
            or parameters.get("task")
            or parameters.get("prompt")
            or raw_text
        )
        description = _refine_code_requirement(description, language)
        filepath = os.path.join(OUTPUT_DIR, filename)

        start = time.time()
        try:
            code = _generate_code_with_repair(description, language)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            action_taken = f"Generated code and saved to {filepath}."
            final_output = code
            context["last_llm_duration_sec"] = time.time() - start
            context["last_generated_code"] = code
            context["last_generated_code_language"] = language or _infer_language_from_text(description)
            context["last_generated_code_file"] = filepath
            context["last_code_requirement"] = description
        except Exception as e:
            action_taken = "Failed to generate code."
            final_output = str(e)

    elif intent == "summarize":
        explicit_text = _safe_text(parameters.get("text"))
        if _is_placeholder_text(explicit_text):
            explicit_text = ""
        last_code = _safe_text(context.get("last_generated_code"))
        wants_code_explanation = (
            not explicit_text
            or "code" in explicit_text.lower()
        )

        if wants_code_explanation and not last_code:
            file_code, file_lang, file_path = _load_latest_generated_code_from_output()
            if file_code:
                last_code = file_code
                context["last_generated_code"] = file_code
                context["last_generated_code_language"] = file_lang
                context["last_generated_code_file"] = file_path

        if wants_code_explanation and last_code:
            lang = context.get("last_generated_code_language") or "unknown"
            source_name = os.path.basename(str(context.get("last_generated_code_file") or "generated file"))
            prompt = (
                "Explain the following generated code in clear, concise points. "
                "Cover: what it does, core logic, important conditions/loops, time complexity, "
                "and suggested improvements.\n\n"
                f"Language: {lang}\n"
                f"Source file: {source_name}\n"
                f"Code:\n{last_code}"
            )
        else:
            text_to_summarize = (
                explicit_text
                or _safe_text(raw_text)
                or _safe_text(context.get("last_code_requirement"))
                or _safe_text(context.get("last_raw_text"))
                or _safe_text(RUNTIME_MEMORY.get("last_code_requirement"))
                or _safe_text(RUNTIME_MEMORY.get("last_raw_text"))
            )
            prompt = f"Summarize the following text concisely: {text_to_summarize}"

        start = time.time()
        try:
            response = _ollama_chat(
                OLLAMA_MODEL_CODE,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "num_predict": 500,
                },
            )
            summary = _safe_text(response["message"].get("content"))
            if _looks_like_empty_or_apology_response(summary):
                summary = _build_question_explanation(
                    question=_safe_text(raw_text) or _safe_text(context.get("last_raw_text")),
                    requirement=_safe_text(context.get("last_code_requirement")) or _safe_text(RUNTIME_MEMORY.get("last_code_requirement")),
                    language=_safe_text(context.get("last_generated_code_language")),
                    source_file=os.path.basename(_safe_text(context.get("last_generated_code_file"))),
                )
            action_taken = "Summarized text."
            final_output = summary
            context["last_llm_duration_sec"] = time.time() - start

            # Optional compound behaviour: save summary to a file
            output_filename = parameters.get("output_filename")
            if output_filename:
                filepath = os.path.join(OUTPUT_DIR, output_filename)
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(summary)
                    action_taken += f" Summary also saved to {filepath}."
                except Exception as e:
                    action_taken += f" Failed to save summary: {e}"
        except Exception as e:
            action_taken = "Summarization fallback generated."
            final_output = _build_question_explanation(
                question=_safe_text(raw_text) or _safe_text(context.get("last_raw_text")),
                requirement=_safe_text(context.get("last_code_requirement")) or _safe_text(RUNTIME_MEMORY.get("last_code_requirement")),
                language=_safe_text(context.get("last_generated_code_language")),
                source_file=os.path.basename(_safe_text(context.get("last_generated_code_file"))),
            )

    else:
        # general_chat or unknown intent
        start = time.time()
        try:
            response = _ollama_chat(
                OLLAMA_MODEL_CODE,
                messages=[{"role": "user", "content": raw_text}],
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_predict": 500,
                },
            )
            action_taken = "Engaged in general chat."
            final_output = response["message"]["content"]
        except Exception as e:
            action_taken = "Chat failure."
            final_output = str(e)
        context["last_llm_duration_sec"] = time.time() - start

    context["last_intent"] = intent
    context["last_output"] = final_output
    return action_taken, final_output, context


def execute_commands(commands, raw_text):
    """Execute a list of commands (compound commands support).

    Returns a tuple (actions, outputs) where:
    - actions: list of dicts with intent, parameters and description.
    - outputs: list of raw outputs for each command.
    """
    context = {
        "raw_text": raw_text,
        "last_raw_text": _safe_text(raw_text) or _safe_text(RUNTIME_MEMORY.get("last_raw_text")),
        "last_generated_code": _safe_text(RUNTIME_MEMORY.get("last_generated_code")),
        "last_generated_code_language": _safe_text(RUNTIME_MEMORY.get("last_generated_code_language")),
        "last_generated_code_file": _safe_text(RUNTIME_MEMORY.get("last_generated_code_file")),
        "last_code_requirement": _safe_text(RUNTIME_MEMORY.get("last_code_requirement")),
    }
    actions_summary = []
    outputs = []
    for cmd in commands:
        intent = cmd.get("intent", "general_chat")
        parameters = cmd.get("parameters", {})
        action_taken, final_output, context = _execute_single_action(
            intent, parameters, raw_text, context
        )
        actions_summary.append(
            {
                "intent": intent,
                "parameters": parameters,
                "action_taken": action_taken,
                "llm_duration_sec": context.get("last_llm_duration_sec"),
            }
        )
        outputs.append(final_output)

    # Persist latest useful context for follow-up voice commands.
    RUNTIME_MEMORY["last_raw_text"] = _safe_text(raw_text) or _safe_text(context.get("last_raw_text"))
    RUNTIME_MEMORY["last_generated_code"] = _safe_text(context.get("last_generated_code"))
    RUNTIME_MEMORY["last_generated_code_language"] = _safe_text(context.get("last_generated_code_language"))
    RUNTIME_MEMORY["last_generated_code_file"] = _safe_text(context.get("last_generated_code_file"))
    RUNTIME_MEMORY["last_code_requirement"] = _safe_text(context.get("last_code_requirement"))

    return actions_summary, outputs


def execute_action(intent, parameters, raw_text):
    """Backward-compatible helper for executing a single action.

    Used by older UI code; wraps :func:`execute_commands`.
    """
    actions, outputs = execute_commands(
        [{"intent": intent, "parameters": parameters}], raw_text
    )
    first_action = actions[0]["action_taken"] if actions else ""
    first_output = outputs[0] if outputs else ""
    return first_action, first_output
