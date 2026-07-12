import asyncio
import base64
import json
import os
import websockets
from dotenv import load_dotenv

load_dotenv()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


class DeepgramStreamer:
    """Streams PCM16 audio to Deepgram and yields live transcripts."""

    def __init__(self, sample_rate: int = 16000, on_transcript=None):
        self.sample_rate = sample_rate
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.on_transcript = on_transcript  # optional callback(text, is_final)
        self._task: asyncio.Task | None = None
        self._ws = None

    def push_audio(self, b64_data: str):
        """Called synchronously from wherever audio chunks arrive (e.g. exposed JS callback)."""
        self.audio_queue.put_nowait(b64_data)

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()

    async def _run(self):
        url = (
            "wss://api.deepgram.com/v1/listen"
            f"?encoding=linear16&sample_rate={self.sample_rate}&channels=1"
            "&punctuate=true&interim_results=true"
        )
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            print("[stt/deepgram] connected")
            await asyncio.gather(self._sender(ws), self._receiver(ws))

    async def _sender(self, ws):
        while True:
            b64_data = await self.audio_queue.get()
            pcm_bytes = base64.b64decode(b64_data)
            await ws.send(pcm_bytes)

    async def _receiver(self, ws):
        async for message in ws:
            data = json.loads(message)
            try:
                transcript = data["channel"]["alternatives"][0]["transcript"]
            except (KeyError, IndexError):
                continue
            if not transcript.strip():
                continue
            is_final = data.get("is_final", False)
            if self.on_transcript:
                self.on_transcript(transcript, is_final)
            else:
                tag = "[FINAL]" if is_final else "[...]"
                print(f"{tag} {transcript}")