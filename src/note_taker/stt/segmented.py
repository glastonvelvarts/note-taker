import asyncio
import logging
from abc import abstractmethod

import webrtcvad

from .base import SAMPLE_RATE, STTProvider, TranscriptCallback

logger = logging.getLogger(__name__)

FRAME_MS = 30
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2
SILENCE_MS = 800
MIN_SPEECH_MS = 240
MAX_SPEECH_MS = 15_000


class SegmentedProvider(STTProvider):
    """Splits the stream into utterances with VAD and transcribes them in order."""

    def __init__(
        self,
        on_transcript: TranscriptCallback | None = None,
        vad_aggressiveness: int = 2,
    ):
        super().__init__(on_transcript)
        self._vad = webrtcvad.Vad(vad_aggressiveness)
        self._pending = bytearray()
        self._speech = bytearray()
        self._speech_ms = 0
        self._silence_ms = 0
        self._segments: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._idle_timer: asyncio.TimerHandle | None = None

    @abstractmethod
    async def transcribe(self, pcm: bytes) -> str:
        pass

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._work())

    def push_audio(self, pcm: bytes) -> None:
        self._pending.extend(pcm)
        while len(self._pending) >= FRAME_BYTES:
            frame = bytes(self._pending[:FRAME_BYTES])
            del self._pending[:FRAME_BYTES]
            self._process_frame(frame)

        # Audio stops arriving when a speaker mutes, so silence alone can't end the segment.
        if self._idle_timer:
            self._idle_timer.cancel()
        self._idle_timer = asyncio.get_running_loop().call_later(SILENCE_MS / 1000, self._flush)

    async def stop(self) -> None:
        if self._idle_timer:
            self._idle_timer.cancel()
        self._flush()
        if self._worker:
            self._segments.put_nowait(None)
            await self._worker
            self._worker = None

    def _process_frame(self, frame: bytes) -> None:
        if self._vad.is_speech(frame, SAMPLE_RATE):
            self._speech.extend(frame)
            self._speech_ms += FRAME_MS
            self._silence_ms = 0
        elif self._speech:
            self._speech.extend(frame)
            self._silence_ms += FRAME_MS

        if self._silence_ms >= SILENCE_MS or self._speech_ms >= MAX_SPEECH_MS:
            self._flush()

    def _flush(self) -> None:
        if self._speech_ms >= MIN_SPEECH_MS:
            self._segments.put_nowait(bytes(self._speech))
        self._speech.clear()
        self._speech_ms = 0
        self._silence_ms = 0

    async def _work(self) -> None:
        while (segment := await self._segments.get()) is not None:
            try:
                text = await self.transcribe(segment)
            except Exception:
                logger.exception("transcription failed, segment dropped")
                continue
            if text and self.on_transcript:
                self.on_transcript(text, True)
