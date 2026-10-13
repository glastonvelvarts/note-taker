import asyncio
from functools import lru_cache

import numpy as np
from faster_whisper import WhisperModel

from .base import SAMPLE_RATE, TranscriptCallback
from .segmented import SegmentedProvider


@lru_cache
def _load_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    # Missing CUDA libraries only fail on the first inference, so run one on silence now.
    list(model.transcribe(np.zeros(SAMPLE_RATE, np.float32), language="en")[0])
    return model


class WhisperProvider(SegmentedProvider):
    """Local transcription with faster-whisper; streams share one loaded model."""

    def __init__(
        self,
        on_transcript: TranscriptCallback | None = None,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str | None = None,
        language: str | None = "en",
    ):
        super().__init__(on_transcript)
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type or ("float16" if device == "cuda" else "int8")
        self.language = language
        self._model: WhisperModel | None = None

    async def start(self) -> None:
        self._model = await asyncio.to_thread(
            _load_model, self.model_size, self.device, self.compute_type
        )
        await super().start()

    async def transcribe(self, pcm: bytes) -> str:
        return await asyncio.to_thread(self._run_inference, pcm)

    def _run_inference(self, pcm: bytes) -> str:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(audio, language=self.language, beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()
