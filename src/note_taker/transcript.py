import json
import time
from pathlib import Path


class TranscriptCollector:
    """Keeps final transcript segments and mirrors them to <base_path>.json/.txt."""

    def __init__(self, base_path: str | Path):
        self.entries: list[dict[str, float | str]] = []
        self.json_path = Path(f"{base_path}.json")
        self.txt_path = Path(f"{base_path}.txt")

    def add(self, text: str, is_final: bool, speaker: str) -> None:
        text = text.strip()
        if not is_final or not text:
            return
        self.entries.append({"t": time.time(), "speaker": speaker, "text": text})
        self.save()

    def full_text(self) -> str:
        return "\n".join(f"{entry['speaker']}: {entry['text']}" for entry in self.entries)

    def save(self) -> None:
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.txt_path.write_text(self.full_text(), encoding="utf-8")
