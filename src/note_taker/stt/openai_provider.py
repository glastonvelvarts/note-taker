import io
import wave

from openai import AsyncOpenAI

from .base import SAMPLE_RATE, TranscriptCallback
from .segmented import SegmentedProvider


def _to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


class OpenAIProvider(SegmentedProvider):
    """Transcription through OpenAI or any server exposing /v1/audio/transcriptions.

    The client reads OPENAI_API_KEY and OPENAI_BASE_URL when they are not passed in.
    """

    def __init__(
        self,
        on_transcript: TranscriptCallback | None = None,
        model: str = "gpt-transcribe",
        language: str | None = "en",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__(on_transcript)
        self.model = model
        self._language = {}
        if language:
            # gpt-transcribe takes a list of expected languages, older models a single one.
            self._language = (
                {"languages": [language]}
                if model.startswith("gpt-transcribe")
                else {"language": language}
            )
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def transcribe(self, pcm: bytes) -> str:
        result = await self._client.audio.transcriptions.create(
            model=self.model,
            file=("audio.wav", _to_wav(pcm), "audio/wav"),
            **self._language,
        )
        return result.text.strip()

    async def stop(self) -> None:
        await super().stop()
        await self._client.close()
