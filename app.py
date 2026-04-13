import streamlit as st
st.set_page_config(page_title="Local Voice Agent", layout="wide")
import os
import agent
import uuid

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;700;800&family=Space+Grotesk:wght@400;500;700&display=swap');

    :root {
        --bg-1: #05070d;
        --bg-2: #080d16;
        --bg-3: #0d1320;
        --card: rgba(11, 17, 31, 0.78);
        --line: rgba(72, 208, 255, 0.2);
        --text-main: #e7f6ff;
        --text-muted: #9ec4d8;
        --accent-1: #22d3ee;
        --accent-2: #00ffa3;
        --accent-3: #ff7a18;
        --accent-4: #7af3ff;
    }

    html, body, [class*="css"]  {
        font-family: 'Space Grotesk', sans-serif;
    }

    h1, h2, h3 {
        font-family: 'Sora', sans-serif;
        letter-spacing: 0.2px;
    }

    .stApp {
        background:
            radial-gradient(52rem 30rem at 92% -8%, rgba(34, 211, 238, 0.18), transparent 60%),
            radial-gradient(48rem 30rem at -12% 8%, rgba(0, 255, 163, 0.13), transparent 56%),
            radial-gradient(46rem 22rem at 50% 118%, rgba(255, 122, 24, 0.11), transparent 60%),
            linear-gradient(140deg, var(--bg-1), var(--bg-2) 58%, var(--bg-3));
        color: var(--text-main);
    }

    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        background-image:
            linear-gradient(rgba(122, 243, 255, 0.045) 1px, transparent 1px),
            linear-gradient(90deg, rgba(122, 243, 255, 0.045) 1px, transparent 1px);
        background-size: 38px 38px;
        pointer-events: none;
        opacity: 0.28;
        z-index: 0;
    }

    .hero-card {
        position: relative;
        overflow: hidden;
        background: linear-gradient(150deg, rgba(14, 22, 40, 0.9), rgba(7, 13, 25, 0.75));
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 1.2rem;
        box-shadow: 0 26px 60px rgba(0, 0, 0, 0.5), 0 0 32px rgba(34, 211, 238, 0.22);
        z-index: 1;
    }

    .hero-grid {
        display: grid;
        grid-template-columns: 1.4fr 0.9fr;
        gap: 1rem;
        align-items: center;
    }

    .hero-veil {
        position: absolute;
        inset: 0;
        background: linear-gradient(115deg, rgba(122, 243, 255, 0.07), rgba(255,255,255,0));
        pointer-events: none;
    }

    .hero-title {
        margin: 0;
        color: var(--text-main);
        font-size: clamp(1.5rem, 2.4vw, 2.15rem);
        font-weight: 800;
        text-shadow: 0 0 18px rgba(122, 243, 255, 0.35);
    }

    .hero-sub {
        margin-top: 0.4rem;
        margin-bottom: 0.65rem;
        color: var(--text-muted);
        font-size: 1rem;
    }

    .panel-card {
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 0.95rem 1rem;
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.45), 0 0 20px rgba(34, 211, 238, 0.1);
        transition: transform 0.22s ease, box-shadow 0.22s ease;
        margin-bottom: 0.9rem;
        z-index: 1;
        position: relative;
    }

    .panel-card:hover {
        transform: translateY(-5px) perspective(760px) rotateX(2deg) rotateY(-1deg);
        box-shadow: 0 28px 48px rgba(0, 0, 0, 0.52), 0 0 26px rgba(34, 211, 238, 0.22);
    }

    .pill-row {
        display: flex;
        gap: 0.55rem;
        flex-wrap: wrap;
        margin: 0.45rem 0 0.2rem 0;
    }

    .pill {
        font-size: 0.8rem;
        color: #dffbff;
        border: 1px solid rgba(34, 211, 238, 0.4);
        background: linear-gradient(180deg, rgba(34, 211, 238, 0.26), rgba(34, 211, 238, 0.1));
        border-radius: 999px;
        padding: 0.2rem 0.58rem;
        font-weight: 600;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.22), 0 4px 12px rgba(34, 211, 238, 0.2);
    }

    .pill.success {
        border-color: rgba(0, 255, 163, 0.45);
        background: rgba(0, 255, 163, 0.16);
    }

    .pill.warn {
        border-color: rgba(255, 122, 24, 0.45);
        background: rgba(255, 122, 24, 0.16);
    }

    .scene-wrap {
        display: grid;
        place-items: center;
        min-height: 150px;
    }

    .scene {
        width: 132px;
        height: 132px;
        position: relative;
        perspective: 650px;
    }

    .cube {
        width: 88px;
        height: 88px;
        position: absolute;
        top: 22px;
        left: 22px;
        transform-style: preserve-3d;
        animation: cubeSpin 9s infinite linear;
    }

    .face {
        position: absolute;
        width: 88px;
        height: 88px;
        border: 1px solid rgba(122, 243, 255, 0.34);
        background: linear-gradient(155deg, rgba(34,211,238,0.36), rgba(0,255,163,0.18));
        box-shadow: inset 0 0 22px rgba(255,255,255,0.16), 0 0 16px rgba(122, 243, 255, 0.28);
        backdrop-filter: blur(1px);
    }

    .face.front { transform: translateZ(44px); }
    .face.back { transform: rotateY(180deg) translateZ(44px); }
    .face.right { transform: rotateY(90deg) translateZ(44px); }
    .face.left { transform: rotateY(-90deg) translateZ(44px); }
    .face.top { transform: rotateX(90deg) translateZ(44px); }
    .face.bottom { transform: rotateX(-90deg) translateZ(44px); }

    .orb {
        position: absolute;
        width: 26px;
        height: 26px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #fff, rgba(255,122,24,0.9));
        filter: blur(0.2px);
        box-shadow: 0 12px 24px rgba(255, 122, 24, 0.4);
        animation: orbit 6s infinite ease-in-out;
    }

    .orb.one { top: 4px; left: 94px; }
    .orb.two { top: 92px; left: 2px; animation-delay: -2.2s; }

    @keyframes cubeSpin {
        0% { transform: rotateX(-16deg) rotateY(0deg); }
        50% { transform: rotateX(14deg) rotateY(180deg); }
        100% { transform: rotateX(-16deg) rotateY(360deg); }
    }

    @keyframes orbit {
        0% { transform: translate3d(0,0,0) scale(1); opacity: 0.95; }
        50% { transform: translate3d(-8px,-10px,0) scale(1.16); opacity: 1; }
        100% { transform: translate3d(0,0,0) scale(1); opacity: 0.95; }
    }

    .stButton > button {
        border-radius: 12px;
        border: 1px solid rgba(34, 211, 238, 0.38);
        background: linear-gradient(180deg, rgba(15, 26, 45, 0.95), rgba(8, 16, 30, 0.92));
        color: #e7f6ff;
        box-shadow: 0 8px 18px rgba(0, 0, 0, 0.4), 0 0 18px rgba(34, 211, 238, 0.22), inset 0 1px 0 rgba(122,243,255,0.22);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 12px 20px rgba(0, 0, 0, 0.48), 0 0 24px rgba(34, 211, 238, 0.34), inset 0 1px 0 rgba(122,243,255,0.22);
    }

    .stButton > button:active {
        transform: translateY(0px);
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.48), 0 0 14px rgba(34, 211, 238, 0.24), inset 0 1px 0 rgba(122,243,255,0.2);
    }

    .stRadio label, .stFileUploader label, .stCaption, .stMarkdown, .stText, .stSubheader {
        color: var(--text-main) !important;
    }

    .stCodeBlock, pre, code {
        border: 1px solid rgba(122, 243, 255, 0.28) !important;
        box-shadow: 0 0 18px rgba(34, 211, 238, 0.14);
    }

    .stAlert {
        border-radius: 12px !important;
        border: 1px solid rgba(122, 243, 255, 0.2) !important;
    }

    @media (max-width: 860px) {
        .hero-grid {
            grid-template-columns: 1fr;
        }
        .scene-wrap {
            min-height: 120px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-veil"></div>
        <div class="hero-grid">
            <div>
                <h1 class="hero-title">Voice-Controlled Local AI Agent</h1>
                <p class="hero-sub">A local-first assistant that transcribes audio, detects intent, and executes safe actions in the output folder.</p>
                <div class="pill-row">
                    <span class="pill">Local STT</span>
                    <span class="pill success">Compound Intents</span>
                    <span class="pill warn">Human-in-the-Loop</span>
                </div>
            </div>
            <div class="scene-wrap" aria-hidden="true">
                <div class="scene">
                    <div class="cube">
                        <div class="face front"></div>
                        <div class="face back"></div>
                        <div class="face right"></div>
                        <div class="face left"></div>
                        <div class="face top"></div>
                        <div class="face bottom"></div>
                    </div>
                    <div class="orb one"></div>
                    <div class="orb two"></div>
                </div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Initialize session state for memory
if "history" not in st.session_state:
    st.session_state["history"] = []
if "last_transcription" not in st.session_state:
    st.session_state["last_transcription"] = None
if "last_commands" not in st.session_state:
    st.session_state["last_commands"] = None
if "last_intent_error" not in st.session_state:
    st.session_state["last_intent_error"] = None
if "last_stt_meta" not in st.session_state:
    st.session_state["last_stt_meta"] = None
if "last_intent_llm_time" not in st.session_state:
    st.session_state["last_intent_llm_time"] = None

# Input choice: microphone or file upload
source_options = ["Upload file"]
mic_supported = hasattr(st, "audio_input")
if mic_supported:
    source_options.insert(0, "Microphone")

left, right = st.columns([1.25, 1])
with left:
    mode = st.radio("Audio source", source_options, index=0, horizontal=True)
with right:
    st.caption("Tip: Use short, specific prompts for better intent detection.")

audio_bytes = None
audio_file = None

if mode == "Microphone" and mic_supported:
    st.write("Record a short command, then click Process Audio.")
    # Use native Streamlit microphone input for a simpler, cleaner setup.
    mic_audio = st.audio_input("Record from microphone")
    if mic_audio is not None:
        audio_bytes = mic_audio.read()
else:
    # Provide an option to upload an audio file
    audio_file = st.file_uploader("Upload Audio (wav/mp3)", type=["wav", "mp3"])

if st.button("Process Audio"):
    if not audio_bytes and not audio_file:
        st.warning("Please record audio or upload a file first.")
    else:
        with st.spinner("Processing audio and understanding intent..."):
            # Save audio data to a temporary wav file
            audio_path = f"temp_{uuid.uuid4().hex}.wav"
            with open(audio_path, "wb") as f:
                if audio_bytes:
                    f.write(audio_bytes)
                else:
                    f.write(audio_file.read())

            # Speech-to-text with graceful degradation
            stt_result = agent.transcribe_audio(audio_path)
            st.session_state["last_stt_meta"] = stt_result
            if stt_result.get("error"):
                st.error(stt_result["error"])
                st.session_state["last_transcription"] = None
                st.session_state["last_commands"] = None
            else:
                transcription = stt_result.get("text", "")
                st.session_state["last_transcription"] = transcription

                # Detect (possibly compound) intents
                result = agent.detect_intent(transcription)
                st.session_state["last_commands"] = result.get("commands", [])
                st.session_state["last_intent_error"] = result.get("error")
                st.session_state["last_intent_llm_time"] = result.get("llm_duration_sec")

        # Clean up temporary audio file
        if "audio_path" in locals() and os.path.exists(audio_path):
            os.remove(audio_path)


# Display latest transcription and intents if available
if st.session_state.get("last_transcription"):
    st.subheader("Transcription")
    st.write(st.session_state["last_transcription"])
    stt_meta = st.session_state.get("last_stt_meta") or {}
    if stt_meta.get("duration_sec") is not None:
        st.caption(f"STT processing time: {stt_meta['duration_sec']:.2f} seconds")

commands = st.session_state.get("last_commands") or []
intent_error = st.session_state.get("last_intent_error")
intent_llm_time = st.session_state.get("last_intent_llm_time")

if commands:
    st.subheader("Detected Commands")
    st.json(commands)
    if intent_llm_time is not None:
        st.caption(f"Intent LLM time: {intent_llm_time:.2f} seconds")
    if intent_error:
        st.warning(f"Intent model had an issue; using best-effort result. Details: {intent_error}")

    # Human-in-the-loop confirmation before any file operations
    st.info("Review the detected commands above. When you're ready, confirm to execute them.")
    if st.button("✅ Confirm and Execute Actions"):
        with st.spinner("Executing local tools..."):
            actions, outputs = agent.execute_commands(commands, st.session_state["last_transcription"])

            st.subheader("System Actions Executed")
            for idx, summary in enumerate(actions):
                st.markdown(f"**Step {idx+1} - Intent:** {summary['intent']}")
                st.write(f"Parameters: {summary['parameters']}")
                st.write(f"Action Taken: {summary['action_taken']}")
                st.write("Output snippet:")
                st.code(str(outputs[idx])[:500])

            # Update in-session memory
            st.session_state["history"].append(
                {
                    "transcription": st.session_state["last_transcription"],
                    "commands": commands,
                    "actions": actions,
                    "outputs": [str(o) for o in outputs],
                }
            )

elif intent_error:
    # No commands but we had an error – degrade gracefully
    st.warning("Could not confidently map your request to a known intent; treating as general chat if retried.")


# Session memory: show history of interactions
if st.session_state["history"]:
    st.subheader("Session History")
    for i, item in enumerate(reversed(st.session_state["history"])):
        st.markdown(f"**Interaction {len(st.session_state['history']) - i}:**")
        st.write("Transcript:")
        st.write(item["transcription"])
        st.write("Commands:")
        st.json(item["commands"])
        st.write("Actions:")
        st.json(item["actions"])
