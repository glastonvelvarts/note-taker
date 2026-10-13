import os

from .base import SpeakerCallback, STTProvider, TranscriptCallback

STT_MODES = ("deepgram", "openai", "whisper")


def _env(**names: str) -> dict[str, str]:
    return {arg: os.environ[name] for arg, name in names.items() if os.getenv(name)}


def create_stt_provider(
    on_transcript: TranscriptCallback | None = None,
    mode: str | None = None,
) -> STTProvider:
    mode = (mode or os.getenv("STT_MODE", "deepgram")).lower()

    if mode == "deepgram":
        from .deepgram_provider import DeepgramProvider

        return DeepgramProvider(
            on_transcript, **_env(model="DEEPGRAM_MODEL", language="STT_LANGUAGE")
        )

    if mode == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(
            on_transcript, **_env(model="OPENAI_STT_MODEL", language="STT_LANGUAGE")
        )

    if mode == "whisper":
        try:
            from .whisper_provider import WhisperProvider
        except ImportError as error:
            raise ImportError(
                'STT_MODE=whisper needs the extra: pip install "note-taker[whisper]"'
            ) from error

        return WhisperProvider(
            on_transcript,
            **_env(
                model_size="WHISPER_MODEL",
                device="WHISPER_DEVICE",
                compute_type="WHISPER_COMPUTE_TYPE",
                language="STT_LANGUAGE",
            ),
        )

    raise ValueError(f"unknown STT_MODE {mode!r}, expected one of {STT_MODES}")


__all__ = [
    "STT_MODES",
    "STTProvider",
    "SpeakerCallback",
    "TranscriptCallback",
    "create_stt_provider",
]
