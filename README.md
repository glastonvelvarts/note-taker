# Note Taker

A Google Meet bot that joins a call as your Google account, transcribes it live with a label per speaker and summarizes the transcript.

Speech-to-text is pluggable: Deepgram, OpenAI (or any OpenAI-compatible server) and fully local Whisper are supported out of the box.

> Only record or transcribe meetings whose participants have agreed to it.

## Install

Requires Python 3.10+ and Google Chrome.

```bash
pip install note-taker
```

For local transcription with [faster-whisper](https://github.com/SYSTRAN/faster-whisper):

```bash
pip install "note-taker[whisper]"
```

## Quick start

Put the keys for the providers you use in a `.env` file in the directory you run the commands from:

```env
DEEPGRAM_API_KEY=your_deepgram_key
GEMINI_API_KEY=your_gemini_key
```

Sign in to Google once. The profile name is any label you like:

```bash
note-taker login me
```

A Chrome window opens. Sign in, close the window, then press Enter.

Join a meeting:

```bash
note-taker join https://meet.google.com/abc-defg-hij me
```

Finalized speech is printed as it arrives and saved as `.txt` and `.json`:

```
Speaker 1: The marketing budget needs to be approved by Friday afternoon.
Speaker 2: I will send the customer contract to the legal team tomorrow morning.
```

Press `Ctrl+C` to leave. If the bot can't join, the error names a screenshot of what it saw.

Everything the bot stores lives in `~/.note-taker` (`profiles/`, `transcripts/`, `screenshots/`). Set `NOTE_TAKER_HOME` to use another folder.

Summarize a transcript:

```bash
note-taker summarize ~/.note-taker/transcripts/me_1784322349.txt
```

## Speakers

Meet sends each talking participant as a separate audio source. The bot transcribes every source on its own stream, so people talking over each other are still transcribed cleanly, and numbers the speakers in the order they are first heard. Meet does not expose names on this path, so the labels are `Speaker 1`, `Speaker 2`, and so on.

## Speech-to-text providers

Pick one with `STT_MODE` or `note-taker join --stt <mode>`.

| `STT_MODE` | Runs | Needs | Default model |
| --- | --- | --- | --- |
| `deepgram` (default) | Deepgram streaming API | `DEEPGRAM_API_KEY` | `nova-3` |
| `openai` | OpenAI or any OpenAI-compatible server | `OPENAI_API_KEY` | `gpt-transcribe` |
| `whisper` | On your machine | `note-taker[whisper]` | `small` |

| Variable | Applies to | Purpose |
| --- | --- | --- |
| `STT_LANGUAGE` | all | Spoken language, default `en`. Deepgram also accepts `multi`. |
| `DEEPGRAM_MODEL` | deepgram | Model name |
| `OPENAI_STT_MODEL` | openai | Model name |
| `OPENAI_BASE_URL` | openai | Endpoint of an OpenAI-compatible server |
| `WHISPER_MODEL` | whisper | Model size or path, e.g. `tiny`, `small`, `large-v3` |
| `WHISPER_DEVICE` | whisper | `cpu` (default) or `cuda` |
| `WHISPER_COMPUTE_TYPE` | whisper | Defaults to `int8` on CPU and `float16` on CUDA |

`deepgram` streams audio and gives the lowest latency. `openai` and `whisper` cut the audio into utterances with voice activity detection and transcribe each one when the speaker pauses.

`WHISPER_DEVICE=cuda` needs the NVIDIA cuBLAS and cuDNN libraries, see the [faster-whisper GPU notes](https://github.com/SYSTRAN/faster-whisper#gpu).

The `openai` mode works with anything that implements `/v1/audio/transcriptions`, hosted or self-hosted:

```env
STT_MODE=openai
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=your_groq_key
OPENAI_STT_MODEL=whisper-large-v3-turbo
```

## Summaries

Pick the provider with `SUMMARY_PROVIDER`.

| `SUMMARY_PROVIDER` | Needs | Default model |
| --- | --- | --- |
| `gemini` (default) | `GEMINI_API_KEY` | `gemini-3.8-flash` |
| `openai` | `OPENAI_API_KEY` | `gpt-6-luna` |
| `ollama` | A local [Ollama](https://ollama.com/) server | `llama3.2` |

`SUMMARY_MODEL` overrides the model and `SUMMARY_BASE_URL` the endpoint.

## Use as a library

```python
import asyncio

from note_taker import join_meeting, summarize_transcript


def on_transcript(text: str, is_final: bool, speaker: str) -> None:
    if is_final:
        print(f"{speaker}: {text}")


collector = asyncio.run(
    join_meeting("https://meet.google.com/abc-defg-hij", "me", on_transcript)
)
print(summarize_transcript(collector.full_text()))
```

To add a speech-to-text backend, subclass `note_taker.stt.STTProvider`, or `note_taker.stt.segmented.SegmentedProvider` if the backend transcribes whole utterances rather than a stream.

## Limitations

- Speakers are numbered, not named.
- Each speaker opens one stream to the speech-to-text provider, so large meetings need a provider plan that allows that many concurrent streams.

## Development

```bash
git clone <repo-url>
cd note-taker
uv sync --all-extras
uv run note-taker --help
uv build
```

## License

MIT
