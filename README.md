# Voice-Controlled Local AI Agent

This project implements a local AI agent capable of:
1. Speech-to-Text via Whisper (`openai-whisper`).
2. Intent Classification via Local LLM (`ollama`).
3. Tool Execution with restrictions to an `output/` folder.
4. User Interface via Streamlit.

## Setup Instructions

1. **Use Python 3.10 or 3.11 (recommended):**
   Whisper does not yet work reliably on Python 3.13. Install Python 3.10 or 3.11, then create and activate a virtualenv in this folder, for example:
   ```bash
   py -3.11 -m venv .venv
   .\.venv\Scripts\activate
   ```

2. **Install requirements:**
   Make sure you have `ffmpeg` installed on your system for Whisper to process audio files.
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Install and run Ollama:**
   Download and install [Ollama](https://ollama.com/) on your local machine if not already installed.
   Pull the local LLM used:
   ```bash
   ollama run llama3
   ```

4. **Run the Application (website):**
   Recommended (auto-opens browser):
   ```bash
   .\.venv\Scripts\python.exe run_website.py
   ```

   Or classic Streamlit command:
   ```bash
   streamlit run app.py
   ```

5. **Optional: auto-run on VS Code workspace open**
   This repository includes a task configured with `runOn: folderOpen` in `.vscode/tasks.json`, and `.vscode/settings.json` enables automatic tasks.
   When you open this workspace in VS Code, the website launcher will start automatically.

## Architecture

* **UI (website)**: Streamlit provides a browser-based frontend to record from microphone or upload audio, then view transcriptions and results.
* **STT**: Whisper (`openai-whisper`, `base` model) runs locally for offline transcription.
* **Intent & Code Generation**: A local Ollama server (model `llama3`) classifies intents and generates any requested code via HTTP.
* **Execution Engine**: Custom Python code maps intents to file operations within the `output/` folder securely, with human-in-the-loop confirmation.

## Bonus Features Implemented

* **Compound Commands** – multiple intents in one utterance (e.g. "summarize and save to summary.txt").
* **Human-in-the-Loop** – UI confirmation before executing any file operations.
* **Graceful Degradation** – clear error messages when STT or LLM are unavailable or fail.
* **Memory** – in-session history of transcripts, intents, actions, and outputs is shown in the UI.
* **Model Benchmarking Hooks** – UI surfaces STT time and intent LLM time to help compare performance in the article.
