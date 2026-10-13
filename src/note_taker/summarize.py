import os

from openai import OpenAI

# Every provider is reached through its OpenAI-compatible chat endpoint.
PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-3.8-flash",
    },
    "openai": {
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-6-luna",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "model": "llama3.2",
    },
}

PROMPT = """Summarize the following meeting transcript into:
- Key points
- Decisions made
- Action items

Transcript:
{transcript}"""


def summarize_transcript(
    transcript: str,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    provider = (provider or os.getenv("SUMMARY_PROVIDER", "gemini")).lower()
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown SUMMARY_PROVIDER {provider!r}, expected one of {tuple(PROVIDERS)}"
        )
    config = PROVIDERS[provider]

    api_key = "local"
    if config["api_key_env"]:
        api_key = os.getenv(config["api_key_env"])
        if not api_key:
            raise RuntimeError(
                f"{config['api_key_env']} is required for SUMMARY_PROVIDER={provider}"
            )

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("SUMMARY_BASE_URL") or config["base_url"],
    )
    response = client.chat.completions.create(
        model=model or os.getenv("SUMMARY_MODEL") or config["model"],
        messages=[{"role": "user", "content": PROMPT.format(transcript=transcript)}],
    )
    return response.choices[0].message.content
