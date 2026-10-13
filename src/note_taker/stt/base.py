from abc import ABC, abstractmethod
from collections.abc import Callable

SAMPLE_RATE = 16000

TranscriptCallback = Callable[[str, bool], None]
SpeakerCallback = Callable[[str, bool, str], None]


class STTProvider(ABC):
    """Speech-to-text backend fed with 16 kHz mono PCM16 audio."""

    def __init__(self, on_transcript: TranscriptCallback | None = None):
        self.on_transcript = on_transcript

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    def push_audio(self, pcm: bytes) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass
