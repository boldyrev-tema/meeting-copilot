import shutil
from pathlib import Path
from typing import Optional


def find_latest_unprocessed(transcripts_dir: Path, processed_dir: Path) -> Optional[Path]:
    candidates = list(transcripts_dir.glob("*.txt"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def read_transcript(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def mark_processed(path: Path, processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(processed_dir / path.name))
