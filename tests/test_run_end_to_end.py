import json
from unittest.mock import patch

import run
from jira_client import JiraTicketResult


def _write_credentials(tmp_path):
    groq_path = tmp_path / "groq.env"
    groq_path.write_text("GROQ_API_KEY=fake-groq-key\n")

    jira_path = tmp_path / "jira.env"
    jira_path.write_text(
        "JIRA_BASE_URL=https://example.atlassian.net\n"
        "JIRA_EMAIL=a@b.com\n"
        "JIRA_API_TOKEN=fake-token\n"
        "JIRA_PROJECT_KEY=PROJ\n"
    )

    telegram_path = tmp_path / "telegram.env"
    telegram_path.write_text("TELEGRAM_BOT_TOKEN=fake-bot-token\nTELEGRAM_CHAT_ID=12345\n")

    return groq_path, jira_path, telegram_path


def _setup_run_paths(monkeypatch, tmp_path):
    transcripts_dir = tmp_path / "transcripts"
    processed_dir = transcripts_dir / "processed"
    transcripts_dir.mkdir()

    name_mapping_path = tmp_path / "name_mapping.json"
    name_mapping_path.write_text(json.dumps({"Артём": "artem.boldyrev"}), encoding="utf-8")

    groq_path, jira_path, telegram_path = _write_credentials(tmp_path)

    monkeypatch.setattr(run, "TRANSCRIPTS_DIR", transcripts_dir)
    monkeypatch.setattr(run, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(run, "NAME_MAPPING_PATH", name_mapping_path)
    monkeypatch.setattr(run, "MIN_TRANSCRIPT_CHARS", 10)
    monkeypatch.setattr(run, "GROQ_API_KEY_PATH", str(groq_path))
    monkeypatch.setattr(run, "JIRA_CREDENTIALS_PATH", str(jira_path))
    monkeypatch.setattr(run, "TELEGRAM_CREDENTIALS_PATH", str(telegram_path))

    return transcripts_dir, processed_dir


def test_run_happy_path_creates_ticket_and_moves_file(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_10-00-00.txt"
    transcript_file.write_text(
        "[10:00:00] Собеседник: Артём, нужно сделать отчёт до пятницы.", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract.return_value = [
            {
                "who": "Артём",
                "what": "сделать отчёт до пятницы",
                "quote": "нужно сделать отчёт до пятницы",
            }
        ]
        mock_create.return_value = JiraTicketResult(
            success=True, url="https://example.atlassian.net/browse/PROJ-1"
        )

        exit_code = run.run()

    assert exit_code == 0
    mock_create.assert_called_once()
    mock_send.assert_called_once()
    assert not transcript_file.exists()
    assert (processed_dir / transcript_file.name).exists()


def test_run_hallucinated_quote_skips_ticket_but_still_completes(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_11-00-00.txt"
    transcript_file.write_text(
        "[11:00:00] Собеседник: Привет, как прошли выходные?", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract.return_value = [
            {
                "who": "Артём",
                "what": "сделать отчёт до пятницы",
                "quote": "нужно сделать отчёт до пятницы",  # не встречается в транскрипте
            }
        ]

        exit_code = run.run()

    assert exit_code == 0
    mock_create.assert_not_called()
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][2]
    assert "требуют проверки" in sent_text.lower()
    assert not transcript_file.exists()
    assert (processed_dir / transcript_file.name).exists()


def test_run_no_unprocessed_file_returns_zero_without_calling_llm(monkeypatch, tmp_path):
    _setup_run_paths(monkeypatch, tmp_path)

    with patch("run.extract_tasks") as mock_extract:
        exit_code = run.run()

    assert exit_code == 0
    mock_extract.assert_not_called()


def test_run_llm_failure_does_not_move_file(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_12-00-00.txt"
    transcript_file.write_text(
        "[12:00:00] Собеседник: длинный текст для прохождения порога длины транскрипта",
        encoding="utf-8",
    )

    with patch("run.extract_tasks") as mock_extract:
        from task_extraction import LLMCallError

        mock_extract.side_effect = LLMCallError("timeout")
        exit_code = run.run()

    assert exit_code == 1
    assert transcript_file.exists()
    assert not (processed_dir / transcript_file.name).exists()


def test_run_short_transcript_skips_llm_call(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(run, "MIN_TRANSCRIPT_CHARS", 200)
    transcript_file = transcripts_dir / "2026-08-27_09-00-00.txt"
    transcript_file.write_text("[09:00:00] Ты: привет", encoding="utf-8")

    with patch("run.extract_tasks") as mock_extract:
        exit_code = run.run()

    assert exit_code == 0
    mock_extract.assert_not_called()
    assert transcript_file.exists()
    assert not (processed_dir / transcript_file.name).exists()


def test_run_one_ticket_succeeds_one_fails_both_reported(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)
    name_mapping_path = tmp_path / "name_mapping.json"
    name_mapping_path.write_text(
        json.dumps({"Артём": "artem.boldyrev", "Иван": "ivan.petrov"}), encoding="utf-8"
    )
    monkeypatch.setattr(run, "NAME_MAPPING_PATH", name_mapping_path)

    transcript_file = transcripts_dir / "2026-08-27_14-00-00.txt"
    transcript_file.write_text(
        "[14:00:00] Собеседник: Артём, нужно сделать отчёт. Иван, нужно обновить сайт.",
        encoding="utf-8",
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract.return_value = [
            {"who": "Артём", "what": "сделать отчёт", "quote": "нужно сделать отчёт"},
            {"who": "Иван", "what": "обновить сайт", "quote": "нужно обновить сайт"},
        ]
        mock_create.side_effect = [
            JiraTicketResult(success=True, url="https://example.atlassian.net/browse/PROJ-1"),
            JiraTicketResult(success=False, error="403 Forbidden"),
        ]

        exit_code = run.run()

    assert exit_code == 0
    assert mock_create.call_count == 2
    sent_text = mock_send.call_args[0][2]
    assert "PROJ-1" in sent_text
    assert "403 Forbidden" in sent_text
    assert not transcript_file.exists()
    assert (processed_dir / transcript_file.name).exists()


def test_run_missing_jira_credential_does_not_move_file_or_create_ticket(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)

    # Overwrite the Jira credentials file with one missing JIRA_PROJECT_KEY.
    jira_path = tmp_path / "jira.env"
    jira_path.write_text(
        "JIRA_BASE_URL=https://example.atlassian.net\n"
        "JIRA_EMAIL=a@b.com\n"
        "JIRA_API_TOKEN=fake-token\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run, "JIRA_CREDENTIALS_PATH", str(jira_path))

    transcript_file = transcripts_dir / "2026-08-27_15-00-00.txt"
    transcript_file.write_text(
        "[15:00:00] Собеседник: Артём, нужно сделать отчёт до пятницы.", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract.return_value = [
            {
                "who": "Артём",
                "what": "сделать отчёт до пятницы",
                "quote": "нужно сделать отчёт до пятницы",
            }
        ]

        exit_code = run.run()

    assert exit_code == 1
    mock_create.assert_not_called()
    mock_send.assert_not_called()
    assert transcript_file.exists()
    assert not (processed_dir / transcript_file.name).exists()


def test_run_telegram_failure_does_not_move_file(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_13-00-00.txt"
    transcript_file.write_text(
        "[13:00:00] Собеседник: Артём, нужно сделать отчёт до пятницы.", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract.return_value = [
            {
                "who": "Артём",
                "what": "сделать отчёт до пятницы",
                "quote": "нужно сделать отчёт до пятницы",
            }
        ]
        mock_create.return_value = JiraTicketResult(
            success=True, url="https://example.atlassian.net/browse/PROJ-1"
        )
        from telegram_notify import TelegramSendError

        mock_send.side_effect = TelegramSendError("network down")

        exit_code = run.run()

    assert exit_code == 1
    assert transcript_file.exists()
    assert not (processed_dir / transcript_file.name).exists()


def test_run_truncates_long_report_before_sending_to_telegram(monkeypatch, tmp_path):
    transcripts_dir, processed_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_16-00-00.txt"
    transcript_file.write_text(
        "[16:00:00] Собеседник: Привет, как прошли выходные?", encoding="utf-8"
    )

    long_report = "x" * 5000

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.build_report") as mock_build_report, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract.return_value = []
        mock_build_report.return_value = long_report

        exit_code = run.run()

    assert exit_code == 0
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][2]
    assert len(sent_text) <= run.TELEGRAM_MESSAGE_LIMIT
    assert "отчёт обрезан" in sent_text
    assert not transcript_file.exists()
    assert (processed_dir / transcript_file.name).exists()
