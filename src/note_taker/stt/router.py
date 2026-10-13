import asyncio
import logging
from functools import partial

from . import create_stt_provider
from .base import SpeakerCallback, STTProvider

logger = logging.getLogger(__name__)


class SpeakerRouter:
    """Runs one STT stream per speaker, so overlapping speech stays separate and labelled."""

    def __init__(self, on_transcript: SpeakerCallback, mode: str | None = None):
        self._on_transcript = on_transcript
        self._mode = mode
        self._streams: dict[int, STTProvider] = {}
        self._spare: STTProvider | None = None
        self._starting: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        # Started ahead of the meeting so a bad key or model fails early; the first speaker uses it.
        self._spare = create_stt_provider(mode=self._mode)
        await self._spare.start()

    def push_audio(self, pcm: bytes, source: int) -> None:
        if source not in self._streams:
            self._streams[source] = self._open(f"Speaker {len(self._streams) + 1}")
        self._streams[source].push_audio(pcm)

    async def stop(self) -> None:
        await asyncio.gather(*self._starting)
        providers = [*self._streams.values(), *([self._spare] if self._spare else [])]
        results = await asyncio.gather(*(p.stop() for p in providers), return_exceptions=True)
        for error in results:
            if isinstance(error, Exception):
                logger.error("transcription stream failed: %r", error)

    def _open(self, speaker: str) -> STTProvider:
        on_transcript = partial(self._on_transcript, speaker=speaker)
        if self._spare:
            provider, self._spare = self._spare, None
            provider.on_transcript = on_transcript
            return provider

        provider = create_stt_provider(on_transcript, self._mode)
        task = asyncio.create_task(self._start(provider, speaker))
        self._starting.add(task)
        task.add_done_callback(self._starting.discard)
        return provider

    async def _start(self, provider: STTProvider, speaker: str) -> None:
        try:
            await provider.start()
        except Exception:
            logger.exception("could not start transcription for %s", speaker)
