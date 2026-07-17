import asyncio
import base64

import numpy as np
import webrtcvad
from faster_whisper import WhisperModel

from .base import STTProvider, TranscriptCallback

FRAME_MS = 30
SAMPLE_RATE = 16000
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2
SILENCE_HANGOVER_MS = 800
MAX_SEGMENT_MS = 15_000
MIN_SEGMENT_FRAMES = 5


class WhisperProvider(STTProvider):
    def __init__(
        self,
        on_transcript: TranscriptCallback | None = None,
        model_size: str = "small",
        device: str = "cuda",
        compute_type: str = "float16",
        vad_aggressiveness: int = 2,
    ):
        super().__init__(on_transcript)
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        self.model: WhisperModel | None = None
        self._byte_buffer = bytearray()
        self._speech_buffer = bytearray()
        self._silence_ms = 0
        self._speech_ms = 0
        self._in_speech = False
        self._inference_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self.model = await asyncio.to_thread(
            WhisperModel,
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        print("[stt/whisper] model loaded, ready")

    def push_audio(self, b64_data: str) -> None:
        self._byte_buffer.extend(base64.b64decode(b64_data))
        while len(self._byte_buffer) >= FRAME_BYTES:
            frame = bytes(self._byte_buffer[:FRAME_BYTES])
            del self._byte_buffer[:FRAME_BYTES]
            self._process_frame(frame)

    def _process_frame(self, frame: bytes) -> None:
        if self.vad.is_speech(frame, SAMPLE_RATE):
            self._speech_buffer.extend(frame)
            self._speech_ms += FRAME_MS
            self._silence_ms = 0
            self._in_speech = True
        elif self._in_speech:
            self._speech_buffer.extend(frame)
            self._silence_ms += FRAME_MS

        if self._in_speech and (
            self._silence_ms >= SILENCE_HANGOVER_MS
            or self._speech_ms >= MAX_SEGMENT_MS
        ):
            self._schedule_transcription(self._take_segment())

    def _take_segment(self) -> bytes:
        segment = bytes(self._speech_buffer)
        self._speech_buffer.clear()
        self._silence_ms = 0
        self._speech_ms = 0
        self._in_speech = False
        return segment

    def _schedule_transcription(self, segment: bytes) -> None:
        task = asyncio.create_task(self._transcribe(segment))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _transcribe(self, pcm_bytes: bytes) -> None:
        if len(pcm_bytes) < FRAME_BYTES * MIN_SEGMENT_FRAMES:
            return
        async with self._inference_lock:
            text = await asyncio.to_thread(self._run_inference, pcm_bytes)
        if text and self.on_transcript:
            self.on_transcript(text, True)

    def _run_inference(self, pcm_bytes: bytes) -> str:
        if not self.model:
            return ""
        audio = (
            np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            / 32768.0
        )
        segments, _ = self.model.transcribe(
            audio, language="en", beam_size=1
        )
        return " ".join(
            segment.text.strip() for segment in segments
        ).strip()

    async def stop(self) -> None:
        if self._speech_buffer:
            self._schedule_transcription(self._take_segment())
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
