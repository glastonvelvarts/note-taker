import os

from .base import STTProvider, TranscriptCallback


def create_stt_provider(
    on_transcript: TranscriptCallback | None = None,
    mode: str | None = None,
) -> STTProvider:
    selected_mode = (mode or os.getenv("STT_MODE", "deepgram")).lower()

    if selected_mode == "deepgram":
        from .deepgram_provider import DeepgramProvider

        return DeepgramProvider(on_transcript=on_transcript)

    if selected_mode == "whisper":
        from .whisper_provider import WhisperProvider

        device = os.getenv("WHISPER_DEVICE", "cuda")
        default_compute_type = "float16" if device == "cuda" else "int8"
        return WhisperProvider(
            on_transcript=on_transcript,
            device=device,
            model_size=os.getenv("WHISPER_MODEL", "small"),
            compute_type=os.getenv(
                "WHISPER_COMPUTE_TYPE", default_compute_type
            ),
        )

    raise ValueError(f"unknown STT_MODE: {selected_mode}")


__all__ = ["STTProvider", "create_stt_provider"]
