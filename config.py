import os
from pathlib import Path

DEFAULT_TRANSCRIPTS_DIR = "~/Desktop/live_copilot_poc/transcripts"


def _resolve_transcripts_dir() -> Path:
    override = os.environ.get("MEETING_COPILOT_TRANSCRIPTS_DIR")
    return Path(os.path.expanduser(override or DEFAULT_TRANSCRIPTS_DIR))


TRANSCRIPTS_DIR = _resolve_transcripts_dir()
PROCESSED_DIR = TRANSCRIPTS_DIR / "processed"
SUMMARIES_DIR = Path(__file__).parent / "summaries"
NAME_MAPPING_PATH = Path(__file__).parent / "name_mapping.json"
MIN_TRANSCRIPT_CHARS = 200
