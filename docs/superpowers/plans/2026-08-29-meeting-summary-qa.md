# Meeting Summary Q&A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a call, generate a structured "question → answer/decision" Markdown summary (not a generic recap) alongside the existing Jira task detection, so a person who missed the call can later ask `live_copilot_poc`'s existing Knowledge Base what was discussed.

**Architecture:** Two new pure/isolated modules (`summary_extraction.py` for a second, independent Groq call; `summary_markdown.py` for formatting) wired into the existing `run.py` as a self-contained step that runs *before*, and fully independently of, the already-working Jira detection code — a failure in one must never affect the other. The saved `.md` file is the only integration point with `live_copilot_poc`; delivery into its Knowledge Base stays a manual, human step.

**Tech Stack:** Python 3, `requests` (same raw-HTTP Groq pattern as `task_extraction.py`, no SDK), `pytest` + `unittest.mock` for tests.

**Spec:** `/Users/tema/Desktop/meeting_copilot/docs/superpowers/specs/2026-08-29-meeting-summary-qa-design.md`

## Global Constraints

- `LLMCallError` and `LLMResponseParseError` are NOT redefined — `summary_extraction.py` imports both from `task_extraction.py`. This is what lets `run.py` catch both modules' failures with one shared exception tuple.
- Same Groq call pattern as `task_extraction.py`: raw `requests.post` to `https://api.groq.com/openai/v1/chat/completions`, `config.GROQ_MODEL`, `response_format: json_object`, `temperature: 0`, `Authorization: Bearer <key>` header, 60s timeout.
- Saved format is Markdown, not JSON — `live_copilot_poc`'s Knowledge Base embeds plain text files.
- File path: `config.SUMMARIES_DIR / f"{transcript_path.stem}.md"` (e.g. `summaries/2026-08-28_10-00-00.md`). `summaries/` is created automatically if missing and is **not** committed to git — add `summaries/` to `.gitignore`.
- **Summary generation must run BEFORE the existing Jira task-detection call in `run.py`, in its own non-propagating `try/except`, and the existing, already-reviewed Jira/Telegram code must not change its own behavior** — only thread a new `summary_note` string through to `report.build_report`. A schema-specific parse failure in one Groq prompt says nothing about whether the other, unrelated prompt will also fail — gating one behind the other's success would silently lose good summaries for no correctness benefit (see spec's Поток данных §1 for the full reasoning).
- A summary failure — LLM call/parse error OR a disk write error — must never prevent an already-successful Jira ticket from being reported, and must never block the transcript's move to `processed/`.
- Every quote in a Q&A pair is checked with the existing `quote_verification.verify_quote` — unverified pairs go into a separate "Требует проверки" section in the saved file, never silently dropped.
- All external calls (Groq) are mocked in the automated test suite — no real network calls in `pytest`.
- Flat file layout (no package/`__init__.py`), matching the established project convention.

---

### Task 1: `summary_extraction.py` — second, independent Groq call

**Files:**
- Create: `~/Desktop/meeting_copilot/summary_extraction.py`
- Test: `~/Desktop/meeting_copilot/tests/test_summary_extraction.py`

**Interfaces:**
- Consumes: `config.GROQ_MODEL` (existing), `task_extraction.LLMCallError`, `task_extraction.LLMResponseParseError` (existing, imported not redefined).
- Produces: `summary_extraction.extract_qa_pairs(transcript: str, api_key: str) -> list` — each item is a dict with string keys `"question"`, `"answer"`, `"quote"`. Raises `task_extraction.LLMCallError` on network/HTTP failure, `task_extraction.LLMResponseParseError` on malformed JSON, non-list `items`, a non-dict item, a missing key, or a non-string/empty value for any of the three fields.

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_summary_extraction.py`:
```python
import json
from unittest.mock import Mock, patch

import pytest
import requests

from summary_extraction import extract_qa_pairs
from task_extraction import LLMCallError, LLMResponseParseError


def _mock_groq_response(content_dict):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(content_dict)}}]
    }
    return mock_resp


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_returns_parsed_items(mock_post):
    mock_post.return_value = _mock_groq_response(
        {
            "items": [
                {
                    "question": "Когда релиз?",
                    "answer": "В пятницу",
                    "quote": "релиз в пятницу",
                }
            ]
        }
    )

    items = extract_qa_pairs("транскрипт...", api_key="fake")

    assert items == [
        {"question": "Когда релиз?", "answer": "В пятницу", "quote": "релиз в пятницу"}
    ]


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_returns_empty_list_when_nothing_substantive(mock_post):
    mock_post.return_value = _mock_groq_response({"items": []})

    items = extract_qa_pairs("привет, как дела", api_key="fake")

    assert items == []


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_llm_call_error_on_network_failure(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")

    with pytest.raises(LLMCallError):
        extract_qa_pairs("транскрипт", api_key="fake")


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_parse_error_on_invalid_json_content(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "не json"}}]}
    mock_post.return_value = mock_resp

    with pytest.raises(LLMResponseParseError):
        extract_qa_pairs("транскрипт", api_key="fake")


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_parse_error_when_answer_is_not_a_string(mock_post):
    mock_post.return_value = _mock_groq_response(
        {"items": [{"question": "Когда релиз?", "answer": None, "quote": "релиз в пятницу"}]}
    )

    with pytest.raises(LLMResponseParseError):
        extract_qa_pairs("транскрипт", api_key="fake")


@patch("summary_extraction.requests.post")
def test_extract_qa_pairs_raises_parse_error_when_items_is_not_a_list(mock_post):
    mock_post.return_value = _mock_groq_response({"items": "not a list"})

    with pytest.raises(LLMResponseParseError):
        extract_qa_pairs("транскрипт", api_key="fake")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_summary_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'summary_extraction'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/summary_extraction.py`:
```python
import json

import requests

from config import GROQ_MODEL
from task_extraction import LLMCallError, LLMResponseParseError

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "Ты анализируешь транскрипт рабочего созвона между коллегами. "
    "Твоя задача — выделить содержательные вопросы или темы, которые "
    "реально обсуждались, и краткий ответ или принятое решение по каждому.\n\n"
    "Верни СТРОГО JSON-объект вида:\n"
    '{"items": [{"question": "о чём был вопрос/тема", '
    '"answer": "какой ответ/решение", '
    '"quote": "дословная цитата из транскрипта, подтверждающая это"}]}\n\n'
    "Правила:\n"
    "- Не пересказывай светскую беседу (приветствия, погода, личные темы) — "
    "только содержательные рабочие вопросы и решения.\n"
    "- Поле quote ОБЯЗАНО быть дословной выпиской из транскрипта, "
    "без перефразирования.\n"
    "- Если содержательного обсуждения не было — верни {\"items\": []}.\n"
    "- Не придумывай вопросы или решения, которых нет в тексте."
)


def extract_qa_pairs(transcript: str, api_key: str) -> list:
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Транскрипт созвона:\n{transcript}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    try:
        resp = requests.post(
            GROQ_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise LLMCallError(str(e)) from e

    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise LLMResponseParseError(str(e)) from e

    try:
        parsed = json.loads(content)
        items = parsed["items"]

        if not isinstance(items, list):
            raise TypeError(f"items must be a list, got {type(items).__name__}")

        for item in items:
            if not isinstance(item, dict):
                raise TypeError(f"item must be a dict, got {type(item).__name__}")
            if not all(k in item for k in ("question", "answer", "quote")):
                raise KeyError(f"item missing required keys: {item}")
            for k in ("question", "answer", "quote"):
                if not isinstance(item[k], str) or not item[k]:
                    raise TypeError(
                        f"item field {k!r} must be a non-empty string, got {item[k]!r}"
                    )
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise LLMResponseParseError(f"{e} — raw response: {content!r}") from e

    return items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_summary_extraction.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add summary_extraction.py tests/test_summary_extraction.py
git commit -m "Add independent Groq call for meeting Q&A summary extraction"
```

---

### Task 2: `summary_markdown.py` — Markdown formatting

**Files:**
- Create: `~/Desktop/meeting_copilot/summary_markdown.py`
- Test: `~/Desktop/meeting_copilot/tests/test_summary_markdown.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (plain dicts with `question`/`answer`/`quote` keys, matching what Task 1 produces).
- Produces: `summary_markdown.derive_meeting_label(transcript_stem: str) -> str` — `"2026-08-28_10-00-00"` → `"2026-08-28 10:00"`.
- Produces: `summary_markdown.build_summary_markdown(meeting_label: str, qa_pairs: list, needs_review: list) -> str`.

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_summary_markdown.py`:
```python
from summary_markdown import build_summary_markdown, derive_meeting_label


def test_derive_meeting_label_formats_date_and_time():
    assert derive_meeting_label("2026-08-28_10-00-00") == "2026-08-28 10:00"


def test_build_summary_markdown_lists_qa_pairs():
    qa_pairs = [
        {"question": "Когда релиз?", "answer": "В пятницу", "quote": "релиз в пятницу"}
    ]

    text = build_summary_markdown("2026-08-28 10:00", qa_pairs, [])

    assert "2026-08-28 10:00" in text
    assert "Когда релиз?" in text
    assert "В пятницу" in text


def test_build_summary_markdown_includes_needs_review_section():
    needs_review = [
        {
            "question": "Кто ответственный?",
            "answer": "Непонятно",
            "quote": "выдуманная цитата",
        }
    ]

    text = build_summary_markdown("2026-08-28 10:00", [], needs_review)

    assert "Требует проверки" in text
    assert "Кто ответственный?" in text


def test_build_summary_markdown_says_nothing_substantive_when_both_empty():
    text = build_summary_markdown("2026-08-28 10:00", [], [])

    assert "Ничего существенного не обсуждалось" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_summary_markdown.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'summary_markdown'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/summary_markdown.py`:
```python
def derive_meeting_label(transcript_stem: str) -> str:
    date_part, _, time_part = transcript_stem.partition("_")
    hh, mm, _ss = time_part.split("-")
    return f"{date_part} {hh}:{mm}"


def build_summary_markdown(meeting_label: str, qa_pairs: list, needs_review: list) -> str:
    lines = [f"# Саммари созвона — {meeting_label}"]

    if qa_pairs:
        lines.append("\n## Обсуждали")
        for item in qa_pairs:
            lines.append(f"\n### {item['question']}")
            lines.append(item["answer"])

    if needs_review:
        lines.append("\n## Требует проверки (цитата не найдена дословно)")
        for item in needs_review:
            lines.append(f"\n- **Вопрос:** {item['question']}")
            lines.append(f"  **Ответ (не подтверждён):** {item['answer']}")

    if not qa_pairs and not needs_review:
        lines.append("\nНичего существенного не обсуждалось.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_summary_markdown.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add summary_markdown.py tests/test_summary_markdown.py
git commit -m "Add Markdown formatter for meeting Q&A summaries"
```

---

### Task 3: `report.py` — thread through an optional summary note

**Files:**
- Modify: `~/Desktop/meeting_copilot/report.py`
- Test: `~/Desktop/meeting_copilot/tests/test_report.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `report.build_report(created, needs_review, skipped, jira_errors, summary_note=None) -> str` — same as before, with one new optional keyword argument. Existing callers that don't pass it see identical output.

- [ ] **Step 1: Write the failing tests**

Add to `~/Desktop/meeting_copilot/tests/test_report.py` (append, don't remove the existing 5 tests):
```python
def test_build_report_appends_summary_note_when_present():
    text = build_report([], [], [], [], summary_note="саммари сохранено: summaries/x.md")

    assert "саммари сохранено: summaries/x.md" in text


def test_build_report_omits_summary_line_when_absent():
    text = build_report([], [], [], [])

    assert "📝" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_report.py -v`
Expected: FAIL — `TypeError: build_report() got an unexpected keyword argument 'summary_note'`

- [ ] **Step 3: Write the implementation**

Modify `~/Desktop/meeting_copilot/report.py` — change the signature and add one block at the end, keep everything else identical:
```python
def build_report(created, needs_review, skipped, jira_errors, summary_note=None):
    lines = ["Отчёт по обработке транскрипта:"]

    if created:
        lines.append("\n✅ Созданы тикеты:")
        for item in created:
            lines.append(f"- {item['who']}: {item['what']} — {item['url']}")

    if needs_review:
        lines.append("\n⚠️ Требуют проверки (цитата не найдена дословно):")
        for item in needs_review:
            lines.append(f"- {item['who']}: {item['what']} (цитата: «{item['quote']}»)")

    if skipped:
        lines.append("\n⏭ Пропущено (имя не сопоставлено):")
        for item in skipped:
            lines.append(f"- {item['who']}: {item['what']} (цитата: «{item['quote']}»)")

    if jira_errors:
        lines.append("\n❌ Ошибки создания тикета в Jira:")
        for item in jira_errors:
            lines.append(f"- {item['who']}: {item['what']} — {item['error']}")

    if not (created or needs_review or skipped or jira_errors):
        lines.append("\nЗадач не найдено.")

    if summary_note:
        lines.append(f"\n📝 {summary_note}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_report.py -v`
Expected: PASS (7 tests — 5 pre-existing plus the 2 new ones)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add report.py tests/test_report.py
git commit -m "Add optional summary-note line to the report"
```

---

### Task 4: `run.py` — wire in the independent summary step

This is the integration task. It touches `config.py` (one new constant), `.gitignore` (one new entry), `run.py` (a new helper function plus threading `summary_note` through), and `tests/test_run_end_to_end.py` (every existing test needs one added mock, plus new tests for the summary-specific behavior).

**Files:**
- Modify: `~/Desktop/meeting_copilot/config.py`
- Modify: `~/Desktop/meeting_copilot/.gitignore`
- Modify: `~/Desktop/meeting_copilot/run.py`
- Modify: `~/Desktop/meeting_copilot/tests/test_run_end_to_end.py`

**Interfaces:**
- Consumes: `summary_extraction.extract_qa_pairs` (Task 1), `summary_markdown.build_summary_markdown` + `summary_markdown.derive_meeting_label` (Task 2), `report.build_report(..., summary_note=None)` (Task 3), `quote_verification.verify_quote` (existing, unchanged), `task_extraction.LLMCallError` / `LLMResponseParseError` (existing, unchanged — now also raised by `summary_extraction`).
- Produces: `run._generate_and_save_summary(transcript: str, transcript_path: Path, api_key: str) -> str` — never raises; always returns a short status string used as `report.build_report`'s `summary_note`. `run.SUMMARIES_DIR` (re-exported from `config`, patchable by tests the same way `run.TRANSCRIPTS_DIR` already is).

- [ ] **Step 1: Write the failing tests**

First, modify `~/Desktop/meeting_copilot/config.py` — add one line (keep everything else identical):
```python
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
GROQ_MODEL = "openai/gpt-oss-120b"
```

Then add `summaries/` to `~/Desktop/meeting_copilot/.gitignore` (append a line, keep the existing ones):
```
__pycache__/
*.pyc
*.pyo
*.egg-info/
.pytest_cache/
.venv/
venv/
summaries/
```

Now replace the full content of `~/Desktop/meeting_copilot/tests/test_run_end_to_end.py` with this (every pre-existing test keeps its original assertions; each gets one added `patch("run.extract_qa_pairs")` with `.return_value = []` so summary generation is a no-op for tests that aren't about it; `_setup_run_paths` now also returns `summaries_dir`; four new tests are appended at the end):

```python
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
    summaries_dir = tmp_path / "summaries"
    transcripts_dir.mkdir()

    name_mapping_path = tmp_path / "name_mapping.json"
    name_mapping_path.write_text(json.dumps({"Артём": "artem.boldyrev"}), encoding="utf-8")

    groq_path, jira_path, telegram_path = _write_credentials(tmp_path)

    monkeypatch.setattr(run, "TRANSCRIPTS_DIR", transcripts_dir)
    monkeypatch.setattr(run, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(run, "SUMMARIES_DIR", summaries_dir)
    monkeypatch.setattr(run, "NAME_MAPPING_PATH", name_mapping_path)
    monkeypatch.setattr(run, "MIN_TRANSCRIPT_CHARS", 10)
    monkeypatch.setattr(run, "GROQ_API_KEY_PATH", str(groq_path))
    monkeypatch.setattr(run, "JIRA_CREDENTIALS_PATH", str(jira_path))
    monkeypatch.setattr(run, "TELEGRAM_CREDENTIALS_PATH", str(telegram_path))

    return transcripts_dir, processed_dir, summaries_dir


def test_run_happy_path_creates_ticket_and_moves_file(monkeypatch, tmp_path):
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_10-00-00.txt"
    transcript_file.write_text(
        "[10:00:00] Собеседник: Артём, нужно сделать отчёт до пятницы.", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract_qa.return_value = []
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
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_11-00-00.txt"
    transcript_file.write_text(
        "[11:00:00] Собеседник: Привет, как прошли выходные?", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract_qa.return_value = []
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
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_12-00-00.txt"
    transcript_file.write_text(
        "[12:00:00] Собеседник: длинный текст для прохождения порога длины транскрипта",
        encoding="utf-8",
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa:
        from task_extraction import LLMCallError

        mock_extract_qa.return_value = []
        mock_extract.side_effect = LLMCallError("timeout")
        exit_code = run.run()

    assert exit_code == 1
    assert transcript_file.exists()
    assert not (processed_dir / transcript_file.name).exists()


def test_run_short_transcript_skips_llm_call(monkeypatch, tmp_path):
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
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
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
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
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract_qa.return_value = []
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
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)

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
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract_qa.return_value = []
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
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_13-00-00.txt"
    transcript_file.write_text(
        "[13:00:00] Собеседник: Артём, нужно сделать отчёт до пятницы.", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract_qa.return_value = []
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
    transcripts_dir, processed_dir, _summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-27_16-00-00.txt"
    transcript_file.write_text(
        "[16:00:00] Собеседник: Привет, как прошли выходные?", encoding="utf-8"
    )

    long_report = "x" * 5000

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.build_report") as mock_build_report, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract_qa.return_value = []
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


def test_run_generates_and_saves_summary_alongside_ticket(monkeypatch, tmp_path):
    transcripts_dir, processed_dir, summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-28_10-00-00.txt"
    transcript_file.write_text(
        "[10:00:00] Собеседник: Когда релиз? Скоро релиз в пятницу, все готово. "
        "Артём, нужно сделать отчёт до пятницы.",
        encoding="utf-8",
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        mock_extract.return_value = [
            {
                "who": "Артём",
                "what": "сделать отчёт до пятницы",
                "quote": "нужно сделать отчёт до пятницы",
            }
        ]
        mock_extract_qa.return_value = [
            {"question": "Когда релиз?", "answer": "В пятницу", "quote": "релиз в пятницу"}
        ]
        mock_create.return_value = JiraTicketResult(
            success=True, url="https://example.atlassian.net/browse/PROJ-1"
        )

        exit_code = run.run()

    assert exit_code == 0
    mock_create.assert_called_once()
    summary_file = summaries_dir / "2026-08-28_10-00-00.md"
    assert summary_file.exists()
    content = summary_file.read_text(encoding="utf-8")
    assert "Когда релиз?" in content
    assert "В пятницу" in content
    sent_text = mock_send.call_args[0][2]
    assert "саммари сохранено" in sent_text
    assert "PROJ-1" in sent_text
    assert (processed_dir / transcript_file.name).exists()


def test_run_summary_still_saved_when_task_detection_fails(monkeypatch, tmp_path):
    transcripts_dir, processed_dir, summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-28_10-30-00.txt"
    transcript_file.write_text(
        "[10:30:00] Собеседник: Когда релиз? Скоро релиз в пятницу, все готово.",
        encoding="utf-8",
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa:
        from task_extraction import LLMCallError

        mock_extract_qa.return_value = [
            {"question": "Когда релиз?", "answer": "В пятницу", "quote": "релиз в пятницу"}
        ]
        mock_extract.side_effect = LLMCallError("groq is down")

        exit_code = run.run()

    assert exit_code == 1
    summary_file = summaries_dir / "2026-08-28_10-30-00.md"
    assert summary_file.exists()
    assert "Когда релиз?" in summary_file.read_text(encoding="utf-8")
    assert transcript_file.exists()
    assert not (processed_dir / transcript_file.name).exists()


def test_run_summary_failure_does_not_block_ticket_or_move(monkeypatch, tmp_path):
    transcripts_dir, processed_dir, summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-28_11-00-00.txt"
    transcript_file.write_text(
        "[11:00:00] Собеседник: Артём, нужно сделать отчёт до пятницы.", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.create_ticket") as mock_create, \
         patch("run.send_telegram_message") as mock_send:
        from task_extraction import LLMCallError

        mock_extract_qa.side_effect = LLMCallError("groq is down")
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
    assert not (summaries_dir / "2026-08-28_11-00-00.md").exists()
    sent_text = mock_send.call_args[0][2]
    assert "не удалось сгенерировать саммари" in sent_text
    assert "PROJ-1" in sent_text
    assert not transcript_file.exists()
    assert (processed_dir / transcript_file.name).exists()


def test_run_summary_with_empty_items_creates_placeholder_file(monkeypatch, tmp_path):
    transcripts_dir, processed_dir, summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-28_12-00-00.txt"
    transcript_file.write_text(
        "[12:00:00] Собеседник: Привет, как выходные?", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.send_telegram_message"):
        mock_extract.return_value = []
        mock_extract_qa.return_value = []

        exit_code = run.run()

    assert exit_code == 0
    summary_file = summaries_dir / "2026-08-28_12-00-00.md"
    assert summary_file.exists()
    assert "Ничего существенного не обсуждалось" in summary_file.read_text(encoding="utf-8")


def test_run_summary_with_unverified_quote_goes_to_needs_review_section(monkeypatch, tmp_path):
    transcripts_dir, processed_dir, summaries_dir = _setup_run_paths(monkeypatch, tmp_path)
    transcript_file = transcripts_dir / "2026-08-28_13-00-00.txt"
    transcript_file.write_text(
        "[13:00:00] Собеседник: Привет, как выходные прошли?", encoding="utf-8"
    )

    with patch("run.extract_tasks") as mock_extract, \
         patch("run.extract_qa_pairs") as mock_extract_qa, \
         patch("run.send_telegram_message"):
        mock_extract.return_value = []
        mock_extract_qa.return_value = [
            {
                "question": "Когда релиз?",
                "answer": "В пятницу",
                "quote": "этой фразы нет в транскрипте",
            }
        ]

        exit_code = run.run()

    assert exit_code == 0
    summary_file = summaries_dir / "2026-08-28_13-00-00.md"
    content = summary_file.read_text(encoding="utf-8")
    assert "Требует проверки" in content
    assert "Когда релиз?" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_run_end_to_end.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_qa_pairs' from 'run'` (or `AttributeError` when patching `run.extract_qa_pairs`/`run.SUMMARIES_DIR`, since `run.py` doesn't import or define them yet)

- [ ] **Step 3: Write the implementation**

Replace the full content of `~/Desktop/meeting_copilot/run.py`:
```python
import sys

from config import (
    MIN_TRANSCRIPT_CHARS,
    NAME_MAPPING_PATH,
    PROCESSED_DIR,
    SUMMARIES_DIR,
    TRANSCRIPTS_DIR,
)
from credentials import load_credential
from jira_client import create_ticket
from name_mapping import load_name_mapping, resolve_name
from quote_verification import verify_quote
from report import build_report
from summary_extraction import extract_qa_pairs
from summary_markdown import build_summary_markdown, derive_meeting_label
from task_extraction import LLMCallError, LLMResponseParseError, extract_tasks
from telegram_notify import TelegramSendError, send_telegram_message
from transcript_source import find_latest_unprocessed, mark_processed, read_transcript

GROQ_API_KEY_PATH = "~/.credentials/groq_api_key.env"
JIRA_CREDENTIALS_PATH = "~/.credentials/jira_credentials.env"
TELEGRAM_CREDENTIALS_PATH = "~/.credentials/meeting_copilot_telegram.env"

TELEGRAM_MESSAGE_LIMIT = 4000
TELEGRAM_TRUNCATION_NOTE = "\n\n[отчёт обрезан, полный текст в терминале]"


def _generate_and_save_summary(transcript, transcript_path, api_key) -> str:
    try:
        qa_pairs = extract_qa_pairs(transcript, api_key=api_key)
    except (LLMCallError, LLMResponseParseError) as e:
        print(f"Не удалось сгенерировать саммари: {e}")
        return "не удалось сгенерировать саммари"

    confirmed, needs_review_qa = [], []
    for item in qa_pairs:
        if verify_quote(item["quote"], transcript):
            confirmed.append(item)
        else:
            needs_review_qa.append(item)

    try:
        meeting_label = derive_meeting_label(transcript_path.stem)
        summary_text = build_summary_markdown(meeting_label, confirmed, needs_review_qa)

        SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
        summary_path = SUMMARIES_DIR / f"{transcript_path.stem}.md"
        summary_path.write_text(summary_text, encoding="utf-8")
    except OSError as e:
        print(f"Не удалось сохранить саммари: {e}")
        return "не удалось сгенерировать саммари"

    return f"саммари сохранено: {summary_path}"


def run() -> int:
    transcript_path = find_latest_unprocessed(TRANSCRIPTS_DIR, PROCESSED_DIR)
    if transcript_path is None:
        print("Нет необработанных транскриптов.")
        return 0

    transcript = read_transcript(transcript_path)
    if len(transcript.strip()) < MIN_TRANSCRIPT_CHARS:
        print(f"Транскрипт {transcript_path.name} слишком короткий, пропущен.")
        return 0

    try:
        name_mapping = load_name_mapping(NAME_MAPPING_PATH)
    except (FileNotFoundError, ValueError) as e:
        print(f"Таблица имён недоступна: {e}")
        return 1

    try:
        groq_api_key = load_credential(GROQ_API_KEY_PATH, "GROQ_API_KEY")
    except (FileNotFoundError, ValueError) as e:
        print(f"Не удалось обработать транскрипт: {e}")
        return 1

    summary_note = _generate_and_save_summary(transcript, transcript_path, groq_api_key)

    try:
        tasks = extract_tasks(transcript, name_mapping, api_key=groq_api_key)
    except (LLMCallError, LLMResponseParseError) as e:
        print(f"Не удалось обработать транскрипт: {e}")
        return 1

    created, needs_review, skipped, jira_errors = [], [], [], []

    if tasks:
        try:
            jira_base_url = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_BASE_URL")
            jira_email = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_EMAIL")
            jira_api_token = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_API_TOKEN")
            jira_project_key = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_PROJECT_KEY")
        except (FileNotFoundError, ValueError) as e:
            print(f"Не удалось загрузить Jira credentials: {e}")
            return 1

        for task in tasks:
            if not verify_quote(task["quote"], transcript):
                needs_review.append(task)
                continue

            jira_username = resolve_name(task["who"], name_mapping)
            if jira_username is None:
                skipped.append(task)
                continue

            result = create_ticket(
                base_url=jira_base_url,
                email=jira_email,
                api_token=jira_api_token,
                project_key=jira_project_key,
                assignee_username=jira_username,
                summary=task["what"],
                description=f"Автосоздано из созвона. Цитата: «{task['quote']}»",
            )
            if result.success:
                created.append({**task, "url": result.url})
            else:
                jira_errors.append({**task, "error": result.error})

    report_text = build_report(
        created, needs_review, skipped, jira_errors, summary_note=summary_note
    )
    print(report_text)

    telegram_text = report_text
    if len(telegram_text) > TELEGRAM_MESSAGE_LIMIT:
        cutoff = TELEGRAM_MESSAGE_LIMIT - len(TELEGRAM_TRUNCATION_NOTE)
        telegram_text = telegram_text[:cutoff] + TELEGRAM_TRUNCATION_NOTE

    try:
        bot_token = load_credential(TELEGRAM_CREDENTIALS_PATH, "TELEGRAM_BOT_TOKEN")
        chat_id = load_credential(TELEGRAM_CREDENTIALS_PATH, "TELEGRAM_CHAT_ID")
        send_telegram_message(bot_token, chat_id, telegram_text)
    except (TelegramSendError, FileNotFoundError, ValueError) as e:
        print(f"Не удалось отправить отчёт в Telegram: {e}")
        return 1

    mark_processed(transcript_path, PROCESSED_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_run_end_to_end.py -v`
Expected: PASS (14 tests — 9 pre-existing plus 5 new)

- [ ] **Step 5: Run the full test suite**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest -v`
Expected: PASS (all tests from Tasks 1–4 plus every pre-existing test — no failures)

- [ ] **Step 6: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add config.py .gitignore run.py tests/test_run_end_to_end.py
git commit -m "Wire independent meeting-summary generation into the pipeline"
```

---

### Task 5: README — document the new archive and manual delivery step

**Files:**
- Modify: `~/Desktop/meeting_copilot/README.md`

**Interfaces:**
- Consumes: nothing (documentation only).

- [ ] **Step 1: Write the README addition**

Add a new section to `~/Desktop/meeting_copilot/README.md`, right after the existing "## Запуск" section and before "## Быстрый тест без live_copilot_poc" (keep all existing content — this is an addition, not a rewrite):

```markdown
## Саммари прошлых созвонов

Помимо задач для Jira, каждый прогон `run.py` дополнительно сохраняет
структурированное саммари звонка — не общий пересказ, а список реально
обсуждённых вопросов/тем и кратких ответов/решений по каждому — в
`summaries/<имя файла транскрипта>.md`. Эта папка не в git (личный рабочий
контент, не пример для репозитория).

Генерация саммари — независимый шаг: если он упадёт (сеть, лимит Groq),
это никак не повлияет на уже созданные тикеты в Jira и не помешает
переносу транскрипта в `processed/` — просто в Telegram-отчёте будет
пометка «не удалось сгенерировать саммари».

Если в записи попалась цитата, которую модель не смогла дословно
подтвердить в транскрипте, соответствующий вопрос/ответ не отбрасывается —
он попадает в отдельную секцию «Требует проверки» в том же файле.

**Как этим пользоваться:** перед следующим созвоном, где это актуально,
открой `live_copilot_poc`, перетащи нужный файл(ы) из `summaries/` в поле
«База знаний» и спроси текстом «что обсуждали по X в прошлый раз» — код
`meeting_copilot` для этого специально ничего не делает автоматически,
загрузка в базу знаний `live_copilot_poc` — ручной шаг.
```

- [ ] **Step 2: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add README.md
git commit -m "Document the meeting-summary archive and manual delivery step"
```
