import time

from transcript_source import find_latest_unprocessed, mark_processed, read_transcript


def test_find_latest_unprocessed_picks_newest_and_ignores_processed_dir(tmp_path):
    transcripts_dir = tmp_path / "transcripts"
    processed_dir = transcripts_dir / "processed"
    transcripts_dir.mkdir()
    processed_dir.mkdir()

    older = transcripts_dir / "2026-08-25_10-00-00.txt"
    older.write_text("old")
    time.sleep(0.01)
    newer = transcripts_dir / "2026-08-26_10-00-00.txt"
    newer.write_text("new")
    # newer mtime than both, but lives in processed/ and must be ignored
    (processed_dir / "2026-08-27_10-00-00.txt").write_text("already handled")

    result = find_latest_unprocessed(transcripts_dir, processed_dir)

    assert result == newer


def test_find_latest_unprocessed_returns_none_when_nothing_unprocessed(tmp_path):
    transcripts_dir = tmp_path / "transcripts"
    processed_dir = transcripts_dir / "processed"
    transcripts_dir.mkdir()
    processed_dir.mkdir()

    assert find_latest_unprocessed(transcripts_dir, processed_dir) is None


def test_read_transcript_returns_file_contents(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("[10:00:00] Ты: привет", encoding="utf-8")

    assert read_transcript(f) == "[10:00:00] Ты: привет"


def test_mark_processed_moves_file_into_processed_dir(tmp_path):
    transcripts_dir = tmp_path / "transcripts"
    processed_dir = transcripts_dir / "processed"
    transcripts_dir.mkdir()
    f = transcripts_dir / "t.txt"
    f.write_text("content")

    mark_processed(f, processed_dir)

    assert not f.exists()
    assert (processed_dir / "t.txt").read_text() == "content"
