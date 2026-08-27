import os
from pathlib import Path

TRANSCRIPTS_DIR = Path(os.path.expanduser("~/Desktop/live_copilot_poc/transcripts"))
PROCESSED_DIR = TRANSCRIPTS_DIR / "processed"
NAME_MAPPING_PATH = Path(__file__).parent / "name_mapping.json"
MIN_TRANSCRIPT_CHARS = 200
GROQ_MODEL = "openai/gpt-oss-120b"
