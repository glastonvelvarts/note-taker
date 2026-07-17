import asyncio
import base64
import json
import os

import websockets
from dotenv import load_dotenv

from .base import STTProvider, TranscriptCallback

load_dotenv()

_AUDIO_QUEUE_MAX = 100


class DeepgramProvider(STTProvider):
    def __init__(
        self,
        sample_rate: int = 16000,
        on_transcript: TranscriptCallback | None = None,
    ):
        super().__init__(on_transcript)
        self.sample_rate = sample_rate
        self.audio_queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=_AUDIO_QUEUE_MAX
        )
        self._task: asyncio.Task[None] | None = None
        self._ws = None
        self._stopping = False

    def push_audio(self, b64_data: str) -> None:
        try:
            self.audio_queue.put_nowait(b64_data)
        except asyncio.QueueFull:
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.audio_queue.put_nowait(b64_data)
            except asyncio.QueueFull:
                pass

    async def start(self) -> None:
        if not os.getenv("DEEPGRAM_API_KEY"):
            raise RuntimeError("DEEPGRAM_API_KEY is required for STT_MODE=deepgram")
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await asyncio.sleep(0.25)
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _run(self) -> None:
        url = (
            "wss://api.deepgram.com/v1/listen"
            f"?encoding=linear16&sample_rate={self.sample_rate}&channels=1"
            "&punctuate=true&interim_results=true"
        )
        headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}

        while not self._stopping:
            try:
                async with websockets.connect(
                    url, additional_headers=headers
                ) as ws:
                    self._ws = ws
                    print("[stt/deepgram] connected")
                    await asyncio.gather(
                        self._sender(ws), self._receiver(ws)
                    )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if self._stopping:
                    break
                print(
                    "[stt/deepgram] connection died: "
                    f"{error!r}, reconnecting in 2s"
                )
                await asyncio.sleep(2)
            finally:
                self._ws = None

    async def _sender(self, ws) -> None:
        while True:
            b64_data = await self.audio_queue.get()
            await ws.send(base64.b64decode(b64_data))

    async def _receiver(self, ws) -> None:
        async for message in ws:
            data = json.loads(message)
            msg_type = data.get("type")
            if msg_type and msg_type not in ("Results", "Metadata"):
                print(f"[stt/deepgram] message: {msg_type} {data}")
            if data.get("error") or msg_type == "Error":
                print(f"[stt/deepgram] error: {data}")
                continue
            try:
                transcript = data["channel"]["alternatives"][0]["transcript"]
            except (KeyError, IndexError):
                continue
            if not transcript.strip():
                continue
            if self.on_transcript:
                self.on_transcript(transcript, data.get("is_final", False))
