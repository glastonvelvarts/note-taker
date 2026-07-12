# Note Taker

A Google Meet bot that joins calls, transcribes audio in real time, and can summarize meeting transcripts.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (this project uses **uv**, not pip)
- Google Chrome installed locally
- A [Deepgram](https://deepgram.com/) API key (live transcription)
- A [Google AI](https://aistudio.google.com/apikey) API key (summarization only)

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from the project root:

```bash
uv sync
```

That reads `pyproject.toml` / `uv.lock` and installs everything into a local `.venv`. Use `uv run` for all commands below — don't use `pip install`.

A `requirements.txt` is also included (generated from the lockfile) if you need a plain dependency list, but **`uv sync` is the way to install**.

Create a `.env` file in the project root:

```env
DEEPGRAM_API_KEY=your_deepgram_key
GEMINI_API_KEY=your_gemini_key
```

Log in to Google once so the bot can join Meet as your account. Use any label for the profile (e.g. your name):

```bash
uv run python login_setup.py <user_name>
```

A Chrome window opens — sign in to Google, close the window, then press Enter in the terminal. The session is saved under `profiles/<user_id>/`.

## Run the bot

```bash
uv run python bot.py <meeting_url> <user_id>
```

Example:

```bash
uv run python bot.py https://meet.google.com/abc-defg-hij glaston
```

The bot opens Chrome, joins the meeting, and prints live transcripts to the terminal:

```
[...] partial transcript
[FINAL] finalized transcript
```

Press `Ctrl+C` to leave and shut down.

If the bot fails to join, check `join_failed.png` or `not_admitted.png` in the project folder.

## Summarize a transcript

Save a transcript to `transcript.txt`, then install the summarizer dependency and run:

```bash
uv add google-generativeai
uv run python main.py
```

This prints a summary with key points, decisions, and action items.

## Adding dependencies

Use uv, not pip:

```bash
uv add <package>
```

To refresh `requirements.txt` after dependency changes:

```bash
uv export --no-hashes -o requirements.txt
```
