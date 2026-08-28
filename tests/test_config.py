import os
from pathlib import Path

from config import _resolve_transcripts_dir


def test_resolve_transcripts_dir_uses_env_override(monkeypatch):
    monkeypatch.setenv("MEETING_COPILOT_TRANSCRIPTS_DIR", "/tmp/custom_transcripts")
    assert _resolve_transcripts_dir() == Path("/tmp/custom_transcripts")


def test_resolve_transcripts_dir_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("MEETING_COPILOT_TRANSCRIPTS_DIR", raising=False)
    assert _resolve_transcripts_dir() == Path(
        os.path.expanduser("~/Desktop/live_copilot_poc/transcripts")
    )


def test_resolve_transcripts_dir_expands_user_in_override(monkeypatch):
    monkeypatch.setenv("MEETING_COPILOT_TRANSCRIPTS_DIR", "~/custom_transcripts")
    assert _resolve_transcripts_dir() == Path(os.path.expanduser("~/custom_transcripts"))
