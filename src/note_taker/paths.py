import os
from pathlib import Path


def data_dir(name: str) -> Path:
    """Folder for profiles, transcripts and screenshots under NOTE_TAKER_HOME (~/.note-taker)."""
    return Path(os.getenv("NOTE_TAKER_HOME") or Path.home() / ".note-taker", name).resolve()
