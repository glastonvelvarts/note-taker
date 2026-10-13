import asyncio
import contextlib
import json
import os
from urllib.parse import urlencode

import websockets

from .base import SAMPLE_RATE, STTProvider, TranscriptCallback

AUDIO_QUEUE_MAX = 100
IDLE_SECONDS = 1
KEEPALIVE_SECONDS = 5
RECONNECT_SECONDS = 2
CLOSE_TIMEOUT_SECONDS = 5
KEEPALIVE = json.dumps({"type": "KeepAlive"})
FINALIZE = json.dumps({"type": "Finalize"})
CLOSE_STREAM = json.dumps({"type": "CloseStream"})


class DeepgramProvider(STTProvider):
    """Live transcription over Deepgram's streaming websocket."""

    def __init__(
        self,
        on_transcript: TranscriptCallback | None = None,
        model: str = "nova-3",
        language: str = "en",
        api_key: str | None = None,
    ):
        super().__init__(on_transcript)
        api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is required for STT_MODE=deepgram")
        query = urlencode(
            {
                "model": model,
                "language": language,
                "encoding": "linear16",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
                "punctuate": "true",
                "interim_results": "true",
            }
        )
        self._url = f"wss://api.deepgram.com/v1/listen?{query}"
        self._headers = {"Authorization": f"Token {api_key}"}
        self._audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=AUDIO_QUEUE_MAX)
        self._ws: websockets.ClientConnection | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        self._ws = await self._connect()
        self._task = asyncio.create_task(self._run())

    def push_audio(self, pcm: bytes) -> None:
        if self._audio.full():
            self._audio.get_nowait()
        self._audio.put_nowait(pcm)

    async def stop(self) -> None:
        self._stopping = True
        if self._ws:
            with contextlib.suppress(websockets.ConnectionClosed):
                await self._ws.send(CLOSE_STREAM)
        if self._task:
            # Deepgram flushes the last results, then closes the socket and ends the task.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._task, CLOSE_TIMEOUT_SECONDS)
            self._task = None

    async def _connect(self) -> websockets.ClientConnection:
        return await websockets.connect(self._url, additional_headers=self._headers)

    async def _run(self) -> None:
        while True:
            sender = asyncio.create_task(self._sender(self._ws))
            try:
                await self._receiver(self._ws)
            finally:
                sender.cancel()
                await self._ws.close()
                self._ws = None
            if self._stopping:
                return
            self._ws = await self._reconnect()

    async def _reconnect(self) -> websockets.ClientConnection:
        while True:
            try:
                return await self._connect()
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException):
                await asyncio.sleep(RECONNECT_SECONDS)

    async def _sender(self, ws: websockets.ClientConnection) -> None:
        idle = True
        with contextlib.suppress(websockets.ConnectionClosed):
            while True:
                timeout = KEEPALIVE_SECONDS if idle else IDLE_SECONDS
                try:
                    message = await asyncio.wait_for(self._audio.get(), timeout)
                    idle = False
                except asyncio.TimeoutError:
                    # Audio stops when the speaker does, so ask for the words still pending.
                    message = KEEPALIVE if idle else FINALIZE
                    idle = True
                await ws.send(message)

    async def _receiver(self, ws: websockets.ClientConnection) -> None:
        with contextlib.suppress(websockets.ConnectionClosed):
            async for message in ws:
                data = json.loads(message)
                if data.get("type") != "Results":
                    continue
                transcript = data["channel"]["alternatives"][0]["transcript"].strip()
                if transcript and self.on_transcript:
                    self.on_transcript(transcript, data.get("is_final", False))
