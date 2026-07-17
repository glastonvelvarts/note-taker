import json
import time
from pathlib import Path


class TranscriptCollector:
    def __init__(self):
        self.entries: list[dict[str, float | str]] = []
        self._json_path: Path | None = None
        self._txt_path: Path | None = None

    def set_output(self, base_path: str | Path) -> None:
        base = Path(base_path)
        base.parent.mkdir(parents=True, exist_ok=True)
        self._json_path = Path(f"{base}.json")
        self._txt_path = Path(f"{base}.txt")
        self.save()

    def add(self, text: str, is_final: bool) -> None:
        if not is_final or not text.strip():
            return
        self.entries.append({"t": time.time(), "text": text.strip()})
        self.save()

    def full_text(self) -> str:
        return " ".join(str(entry["text"]) for entry in self.entries)

    def save(self, path: str | Path | None = None) -> None:
        if path is not None:
            self.set_output(path)
            return
        if self._json_path is None or self._txt_path is None:
            return
        self._json_path.write_text(
            json.dumps(self.entries, indent=2), encoding="utf-8"
        )
        self._txt_path.write_text(self.full_text(), encoding="utf-8")

    def save_plain(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.full_text(), encoding="utf-8")
