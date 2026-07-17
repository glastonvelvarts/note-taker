from abc import ABC, abstractmethod
from collections.abc import Callable

TranscriptCallback = Callable[[str, bool], None]


class STTProvider(ABC):
    """Common interface for speech-to-text backends."""

    def __init__(self, on_transcript: TranscriptCallback | None = None):
        self.on_transcript = on_transcript

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    def push_audio(self, b64_data: str) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass
