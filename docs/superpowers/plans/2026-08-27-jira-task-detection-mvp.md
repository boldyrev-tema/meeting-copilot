# Jira Task-Detection MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a work call, read the transcript that `live_copilot_poc` already recorded, use one LLM pass to detect verbally-assigned tasks, auto-create Jira tickets for the ones that pass a hallucination-guard and a name-mapping check, and report the outcome (created / needs-review / skipped / errors) as a single Telegram message.

**Architecture:** A standalone CLI script (`run.py`) in `~/Desktop/meeting_copilot/`, built from small single-purpose modules (transcript lookup, name mapping, quote verification, LLM call, Jira client, report builder, Telegram sender) wired together by one orchestrator function. It only *reads* files that `live_copilot_poc` writes — no shared code, no shared process.

**Tech Stack:** Python 3, `requests` (raw HTTP calls — same pattern as `live_copilot_poc`, no SDKs), `pytest` + `unittest.mock` for tests. Groq API (`openai/gpt-oss-120b`) for the single LLM pass, direct Jira REST API v3 calls, direct Telegram Bot API `sendMessage` calls.

**Spec:** `/Users/tema/Desktop/meeting_copilot/docs/superpowers/specs/2026-08-27-jira-task-detection-mvp-design.md`

## Global Constraints

- Reuse `~/Desktop/live_copilot_poc/live_copilot_poc.py` **unmodified** — this project never edits or imports that file. The only contract between the two is the transcript file format: `[HH:MM:SS] <Ты|Собеседник>: текст`, one file per call in `~/Desktop/live_copilot_poc/transcripts/`.
- Postfactum only: pipeline runs manually, once, after the call ends. No file watcher, no auto-trigger.
- Single LLM pass per transcript, no chunking. Model: Groq `openai/gpt-oss-120b`, endpoint `https://api.groq.com/openai/v1/chat/completions` (same model already used by `live_copilot_poc`, per spec's default candidate).
- Every task from the LLM must pass **two independent filters before a Jira ticket is created**: (1) its `quote` must appear as a normalized substring of the transcript (hallucination guard), (2) its `who` must resolve to a Jira username via the manual name table. Either filter failing routes the task into the report instead of creating a ticket — it never blocks other tasks in the same run.
- All external calls (LLM, Jira, Telegram) are mocked in the automated test suite. Real calls happen only via the manual runbook in Task 9, never in `pytest`.
- Credentials follow the exact convention already used in `live_copilot_poc`: plain-text `KEY=value` line(s) in a file under `~/.credentials/`, read by a small manual parser — no `.env` library, no secrets committed to git.
- The transcript file moves to `~/Desktop/live_copilot_poc/transcripts/processed/` **only** if the entire run (LLM call, all per-task handling, Telegram send) completed without an aborting error. A run that aborts early (bad name table, LLM/network failure, invalid LLM JSON, Telegram send failure) leaves the file in place so it can be retried.
- `MIN_TRANSCRIPT_CHARS = 200` — plan-level default for "transcript too short to bother calling the LLM" (`live_copilot_poc` used 60 chars for a single-speaker check; 200 accounts for this checking the combined two-channel transcript).

---

### Task 1: Project setup — config, credential loader, transcript source

**Files:**
- Create: `~/Desktop/meeting_copilot/config.py`
- Create: `~/Desktop/meeting_copilot/credentials.py`
- Create: `~/Desktop/meeting_copilot/transcript_source.py`
- Create: `~/Desktop/meeting_copilot/requirements.txt`
- Create: `~/Desktop/meeting_copilot/conftest.py`
- Test: `~/Desktop/meeting_copilot/tests/test_credentials.py`
- Test: `~/Desktop/meeting_copilot/tests/test_transcript_source.py`

**Interfaces:**
- Produces: `config.TRANSCRIPTS_DIR: Path`, `config.PROCESSED_DIR: Path`, `config.NAME_MAPPING_PATH: Path`, `config.MIN_TRANSCRIPT_CHARS: int`, `config.GROQ_MODEL: str`
- Produces: `credentials.load_credential(path: str, key: str) -> str` — raises `ValueError` if `key` isn't found in the file, propagates `FileNotFoundError` if the file is missing.
- Produces: `transcript_source.find_latest_unprocessed(transcripts_dir: Path, processed_dir: Path) -> Path | None`
- Produces: `transcript_source.read_transcript(path: Path) -> str`
- Produces: `transcript_source.mark_processed(path: Path, processed_dir: Path) -> None`

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_credentials.py`:
```python
import pytest
from credentials import load_credential


def test_load_credential_reads_matching_key(tmp_path):
    p = tmp_path / "creds.env"
    p.write_text("FOO=bar\nBAZ=qux\n")
    assert load_credential(str(p), "BAZ") == "qux"


def test_load_credential_missing_key_raises_value_error(tmp_path):
    p = tmp_path / "creds.env"
    p.write_text("FOO=bar\n")
    with pytest.raises(ValueError):
        load_credential(str(p), "MISSING")


def test_load_credential_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_credential(str(tmp_path / "missing.env"), "FOO")
```

`~/Desktop/meeting_copilot/tests/test_transcript_source.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_credentials.py tests/test_transcript_source.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'credentials'` and `'transcript_source'` (files don't exist yet).

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/conftest.py`:
```python
# Empty on purpose: its presence tells pytest to add this directory's
# path to sys.path so tests can `import config`, `import run`, etc.
# directly, matching the flat (non-package) layout used by live_copilot_poc.
```

`~/Desktop/meeting_copilot/config.py`:
```python
import os
from pathlib import Path

TRANSCRIPTS_DIR = Path(os.path.expanduser("~/Desktop/live_copilot_poc/transcripts"))
PROCESSED_DIR = TRANSCRIPTS_DIR / "processed"
NAME_MAPPING_PATH = Path(__file__).parent / "name_mapping.json"
MIN_TRANSCRIPT_CHARS = 200
GROQ_MODEL = "openai/gpt-oss-120b"
```

`~/Desktop/meeting_copilot/credentials.py`:
```python
import os


def load_credential(path: str, key: str) -> str:
    full_path = os.path.expanduser(path)
    with open(full_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.strip().split("=", 1)[1]
    raise ValueError(f"{key} not found in {full_path}")
```

`~/Desktop/meeting_copilot/transcript_source.py`:
```python
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
```

`~/Desktop/meeting_copilot/requirements.txt`:
```
requests
pytest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_credentials.py tests/test_transcript_source.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add config.py credentials.py transcript_source.py requirements.txt conftest.py tests/test_credentials.py tests/test_transcript_source.py
git commit -m "Add project config, credential loader, and transcript source lookup"
```

---

### Task 2: Name mapping module

**Files:**
- Create: `~/Desktop/meeting_copilot/name_mapping.py`
- Create: `~/Desktop/meeting_copilot/name_mapping.json`
- Test: `~/Desktop/meeting_copilot/tests/test_name_mapping.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `name_mapping.load_name_mapping(path: Path) -> dict[str, str]` — propagates `FileNotFoundError` / `json.JSONDecodeError` on missing/malformed file (run.py will catch these directly, see Task 8).
- Produces: `name_mapping.resolve_name(name: str, mapping: dict[str, str]) -> str | None` — case-insensitive exact match, `None` if not found.

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_name_mapping.py`:
```python
import json

import pytest

from name_mapping import load_name_mapping, resolve_name


def test_load_name_mapping_reads_json_file(tmp_path):
    p = tmp_path / "names.json"
    p.write_text(json.dumps({"Артём": "artem.boldyrev"}), encoding="utf-8")

    assert load_name_mapping(p) == {"Артём": "artem.boldyrev"}


def test_load_name_mapping_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_name_mapping(tmp_path / "missing.json")


def test_load_name_mapping_malformed_json_raises(tmp_path):
    p = tmp_path / "names.json"
    p.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_name_mapping(p)


def test_resolve_name_exact_match():
    mapping = {"Артём": "artem.boldyrev"}
    assert resolve_name("Артём", mapping) == "artem.boldyrev"


def test_resolve_name_case_insensitive():
    mapping = {"Артём": "artem.boldyrev"}
    assert resolve_name("артём", mapping) == "artem.boldyrev"


def test_resolve_name_not_found_returns_none():
    mapping = {"Артём": "artem.boldyrev"}
    assert resolve_name("Пётр", mapping) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_name_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'name_mapping'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/name_mapping.py`:
```python
import json
from pathlib import Path
from typing import Optional


def load_name_mapping(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_name(name: str, mapping: dict) -> Optional[str]:
    normalized = name.strip().lower()
    for known_name, jira_username in mapping.items():
        if known_name.strip().lower() == normalized:
            return jira_username
    return None
```

`~/Desktop/meeting_copilot/name_mapping.json` (real table — edit by hand as the team changes):
```json
{
  "Артём": "artem.boldyrev"
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_name_mapping.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add name_mapping.py name_mapping.json tests/test_name_mapping.py
git commit -m "Add name-to-Jira-username mapping table and resolver"
```

---

### Task 3: Quote verification (hallucination guard)

**Files:**
- Create: `~/Desktop/meeting_copilot/quote_verification.py`
- Test: `~/Desktop/meeting_copilot/tests/test_quote_verification.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `quote_verification.verify_quote(quote: str, transcript: str) -> bool`

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_quote_verification.py`:
```python
from quote_verification import verify_quote


def test_verify_quote_exact_match():
    transcript = "[10:00:00] Собеседник: Нужно сделать отчёт до пятницы."
    assert verify_quote("Нужно сделать отчёт до пятницы.", transcript) is True


def test_verify_quote_tolerates_case_punctuation_and_yo_e_variation():
    transcript = "[10:00:00] Собеседник: Нужно сделать ОТЧЁТ до пятницы!"
    assert verify_quote("нужно сделать отчет до пятницы", transcript) is True


def test_verify_quote_false_for_paraphrase():
    transcript = "[10:00:00] Собеседник: Нужно сделать отчёт до пятницы."
    assert verify_quote("Подготовь, пожалуйста, финансовый отчёт", transcript) is False


def test_verify_quote_false_when_fabricated():
    transcript = "[10:00:00] Собеседник: Привет, как дела?"
    assert verify_quote("Нужно сделать отчёт до пятницы.", transcript) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_quote_verification.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quote_verification'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/quote_verification.py`:
```python
import re


def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def verify_quote(quote: str, transcript: str) -> bool:
    return _normalize(quote) in _normalize(transcript)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_quote_verification.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add quote_verification.py tests/test_quote_verification.py
git commit -m "Add substring-based quote verification against LLM hallucination"
```

---

### Task 4: Task extraction (single Groq LLM pass)

**Files:**
- Create: `~/Desktop/meeting_copilot/task_extraction.py`
- Test: `~/Desktop/meeting_copilot/tests/test_task_extraction.py`

**Interfaces:**
- Consumes: `config.GROQ_MODEL: str` (Task 1)
- Produces: `task_extraction.extract_tasks(transcript: str, name_mapping: dict, api_key: str) -> list[dict]` — each dict has keys `"who"`, `"what"`, `"quote"` (all `str`).
- Produces: `task_extraction.LLMCallError(Exception)`, `task_extraction.LLMResponseParseError(Exception)`

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_task_extraction.py`:
```python
import json
from unittest.mock import Mock, patch

import pytest
import requests

from task_extraction import LLMCallError, LLMResponseParseError, extract_tasks


def _mock_groq_response(content_dict):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(content_dict)}}]
    }
    return mock_resp


@patch("task_extraction.requests.post")
def test_extract_tasks_returns_parsed_tasks(mock_post):
    mock_post.return_value = _mock_groq_response(
        {"tasks": [{"who": "Артём", "what": "сделать отчёт", "quote": "нужно сделать отчёт"}]}
    )

    tasks = extract_tasks("транскрипт...", {"Артём": "artem.boldyrev"}, api_key="fake")

    assert tasks == [{"who": "Артём", "what": "сделать отчёт", "quote": "нужно сделать отчёт"}]


@patch("task_extraction.requests.post")
def test_extract_tasks_returns_empty_list_when_no_tasks_found(mock_post):
    mock_post.return_value = _mock_groq_response({"tasks": []})

    tasks = extract_tasks("привет, как дела", {}, api_key="fake")

    assert tasks == []


@patch("task_extraction.requests.post")
def test_extract_tasks_raises_llm_call_error_on_network_failure(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")

    with pytest.raises(LLMCallError):
        extract_tasks("транскрипт", {}, api_key="fake")


@patch("task_extraction.requests.post")
def test_extract_tasks_raises_parse_error_on_invalid_json_content(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "не json"}}]}
    mock_post.return_value = mock_resp

    with pytest.raises(LLMResponseParseError):
        extract_tasks("транскрипт", {}, api_key="fake")


@patch("task_extraction.requests.post")
def test_extract_tasks_raises_parse_error_on_missing_keys(mock_post):
    mock_post.return_value = _mock_groq_response({"tasks": [{"who": "Артём"}]})

    with pytest.raises(LLMResponseParseError):
        extract_tasks("транскрипт", {}, api_key="fake")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_task_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'task_extraction'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/task_extraction.py`:
```python
import json

import requests

from config import GROQ_MODEL

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "Ты анализируешь транскрипт рабочего созвона между коллегами. "
    "Твоя задача — найти моменты, где кто-то устно поручил задачу конкретному "
    "человеку.\n\n"
    "Верни СТРОГО JSON-объект вида:\n"
    '{"tasks": [{"who": "имя исполнителя", "what": "краткая формулировка задачи", '
    '"quote": "дословная цитата из транскрипта"}]}\n\n'
    "Правила:\n"
    "- Поле quote ОБЯЗАНО быть дословной выпиской из транскрипта, "
    "без перефразирования и без исправления опечаток распознавания речи.\n"
    "- Если поручений не было — верни {\"tasks\": []}.\n"
    "- Не придумывай задачи, которых нет в тексте."
)


class LLMCallError(Exception):
    pass


class LLMResponseParseError(Exception):
    pass


def _build_user_message(transcript: str, name_mapping: dict) -> str:
    known_names = ", ".join(name_mapping.keys()) if name_mapping else "(таблица пуста)"
    return (
        f"Известные участники команды: {known_names}\n\n"
        f"Транскрипт созвона:\n{transcript}"
    )


def extract_tasks(transcript: str, name_mapping: dict, api_key: str) -> list:
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(transcript, name_mapping)},
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
        parsed = json.loads(content)
        tasks = parsed["tasks"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise LLMResponseParseError(str(e)) from e

    for task in tasks:
        if not all(k in task for k in ("who", "what", "quote")):
            raise LLMResponseParseError(f"task missing required keys: {task}")

    return tasks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_task_extraction.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add task_extraction.py tests/test_task_extraction.py
git commit -m "Add single-pass Groq LLM call for task detection"
```

---

### Task 5: Jira client

**Files:**
- Create: `~/Desktop/meeting_copilot/jira_client.py`
- Test: `~/Desktop/meeting_copilot/tests/test_jira_client.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `jira_client.JiraTicketResult` — attributes `success: bool`, `url: str | None`, `error: str | None`.
- Produces: `jira_client.create_ticket(base_url: str, email: str, api_token: str, project_key: str, assignee_username: str, summary: str, description: str) -> JiraTicketResult` — never raises; failures come back as `success=False`.

**Known unverified detail (flag for the manual test in Task 9):** this uses `{"assignee": {"name": assignee_username}}`, which is the Jira Server/Data Center convention. Jira **Cloud** typically expects `{"assignee": {"accountId": ...}}` instead. Which one Артём's real instance needs has not been checked against a live API call — Task 9's manual runbook must verify this on the first real run and this file may need a one-line fix (swap `"name"` for `"accountId"`, and change what's stored in `name_mapping.json` accordingly) before it works for real.

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_jira_client.py`:
```python
from unittest.mock import Mock, patch

import requests

from jira_client import create_ticket


@patch("jira_client.requests.post")
def test_create_ticket_success_returns_url(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"key": "PROJ-42"}
    mock_post.return_value = mock_resp

    result = create_ticket(
        base_url="https://example.atlassian.net",
        email="a@b.com",
        api_token="tok",
        project_key="PROJ",
        assignee_username="artem.boldyrev",
        summary="Сделать отчёт",
        description="Цитата: «нужно сделать отчёт»",
    )

    assert result.success is True
    assert result.url == "https://example.atlassian.net/browse/PROJ-42"
    assert result.error is None


@patch("jira_client.requests.post")
def test_create_ticket_failure_returns_error_without_raising(mock_post):
    mock_post.side_effect = requests.exceptions.HTTPError("403 Forbidden")

    result = create_ticket(
        base_url="https://example.atlassian.net",
        email="a@b.com",
        api_token="tok",
        project_key="PROJ",
        assignee_username="unknown.user",
        summary="Сделать отчёт",
        description="Цитата: «нужно сделать отчёт»",
    )

    assert result.success is False
    assert result.url is None
    assert "403" in result.error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_jira_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jira_client'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/jira_client.py`:
```python
import requests


class JiraTicketResult:
    def __init__(self, success: bool, url: str = None, error: str = None):
        self.success = success
        self.url = url
        self.error = error


def create_ticket(base_url, email, api_token, project_key, assignee_username, summary, description):
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                ],
            },
            "issuetype": {"name": "Task"},
            # See Task 5's "Known unverified detail" note in the plan:
            # Jira Cloud may require {"accountId": ...} here instead of "name".
            "assignee": {"name": assignee_username},
        }
    }

    try:
        resp = requests.post(
            f"{base_url}/rest/api/3/issue",
            json=payload,
            auth=(email, api_token),
            timeout=30,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return JiraTicketResult(success=False, error=str(e))

    key = resp.json()["key"]
    return JiraTicketResult(success=True, url=f"{base_url}/browse/{key}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_jira_client.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add jira_client.py tests/test_jira_client.py
git commit -m "Add Jira REST API ticket creation client"
```

---

### Task 6: Report builder

**Files:**
- Create: `~/Desktop/meeting_copilot/report.py`
- Test: `~/Desktop/meeting_copilot/tests/test_report.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (plain dicts with keys `who`/`what`/`quote`/`url`/`error`, matching what Task 8's orchestrator will assemble).
- Produces: `report.build_report(created: list[dict], needs_review: list[dict], skipped: list[dict], jira_errors: list[dict]) -> str`

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_report.py`:
```python
from report import build_report


def test_build_report_lists_created_tickets_with_links():
    created = [{"who": "Артём", "what": "сделать отчёт", "url": "https://x/browse/PROJ-1"}]

    text = build_report(created, [], [], [])

    assert "Артём" in text
    assert "сделать отчёт" in text
    assert "https://x/browse/PROJ-1" in text


def test_build_report_lists_needs_review_with_quote():
    needs_review = [{"who": "Артём", "what": "сделать отчёт", "quote": "выдуманная цитата"}]

    text = build_report([], needs_review, [], [])

    assert "требует проверки" in text.lower() or "требуют проверки" in text.lower()
    assert "выдуманная цитата" in text


def test_build_report_lists_skipped_unmatched_names():
    skipped = [{"who": "Незнакомец", "what": "что-то сделать", "quote": "цитата"}]

    text = build_report([], [], skipped, [])

    assert "Незнакомец" in text
    assert "пропущен" in text.lower()


def test_build_report_lists_jira_errors():
    jira_errors = [{"who": "Артём", "what": "сделать отчёт", "error": "403 Forbidden"}]

    text = build_report([], [], [], jira_errors)

    assert "403 Forbidden" in text


def test_build_report_says_no_tasks_when_all_empty():
    text = build_report([], [], [], [])

    assert "не найдено" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'report'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/report.py`:
```python
def build_report(created, needs_review, skipped, jira_errors):
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

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_report.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add report.py tests/test_report.py
git commit -m "Add report builder for created/needs-review/skipped/error tasks"
```

---

### Task 7: Telegram notifier

**Files:**
- Create: `~/Desktop/meeting_copilot/telegram_notify.py`
- Test: `~/Desktop/meeting_copilot/tests/test_telegram_notify.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `telegram_notify.send_telegram_message(bot_token: str, chat_id: str, text: str) -> None` — raises `TelegramSendError` on any failure.
- Produces: `telegram_notify.TelegramSendError(Exception)`

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_telegram_notify.py`:
```python
from unittest.mock import Mock, patch

import pytest
import requests

from telegram_notify import TelegramSendError, send_telegram_message


@patch("telegram_notify.requests.post")
def test_send_telegram_message_posts_to_correct_url_and_payload(mock_post):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_post.return_value = mock_resp

    send_telegram_message("bot-token", "12345", "привет")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/botbot-token/sendMessage"
    assert kwargs["json"] == {"chat_id": "12345", "text": "привет"}


@patch("telegram_notify.requests.post")
def test_send_telegram_message_raises_on_failure(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")

    with pytest.raises(TelegramSendError):
        send_telegram_message("bot-token", "12345", "привет")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_telegram_notify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'telegram_notify'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/telegram_notify.py`:
```python
import requests


class TelegramSendError(Exception):
    pass


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise TelegramSendError(str(e)) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_telegram_notify.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add telegram_notify.py tests/test_telegram_notify.py
git commit -m "Add Telegram Bot API notifier for run reports"
```

---

### Task 8: Orchestrator (`run.py`) and end-to-end tests

**Files:**
- Create: `~/Desktop/meeting_copilot/run.py`
- Test: `~/Desktop/meeting_copilot/tests/test_run_end_to_end.py`

**Interfaces:**
- Consumes: every module from Tasks 1–7 by their exact names above (`config.*`, `credentials.load_credential`, `transcript_source.*`, `name_mapping.*`, `quote_verification.verify_quote`, `task_extraction.extract_tasks` + its two exceptions, `jira_client.create_ticket`, `report.build_report`, `telegram_notify.send_telegram_message` + `TelegramSendError`).
- Produces: `run.run() -> int` (0 = success or nothing-to-do, 1 = aborted with an error message already printed). Also produces module-level constants `run.GROQ_API_KEY_PATH`, `run.JIRA_CREDENTIALS_PATH`, `run.TELEGRAM_CREDENTIALS_PATH` (plain strings, `~/.credentials/...` paths) — tests monkeypatch these to point at temp files instead of real credentials.

- [ ] **Step 1: Write the failing tests**

`~/Desktop/meeting_copilot/tests/test_run_end_to_end.py`:
```python
import json
from unittest.mock import patch

import run


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


class _FakeTicketResult:
    def __init__(self, success, url=None, error=None):
        self.success = success
        self.url = url
        self.error = error


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
        mock_create.return_value = _FakeTicketResult(
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
    assert "требует проверки" in sent_text.lower()
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
            _FakeTicketResult(success=True, url="https://example.atlassian.net/browse/PROJ-1"),
            _FakeTicketResult(success=False, error="403 Forbidden"),
        ]

        exit_code = run.run()

    assert exit_code == 0
    assert mock_create.call_count == 2
    sent_text = mock_send.call_args[0][2]
    assert "PROJ-1" in sent_text
    assert "403 Forbidden" in sent_text
    assert not transcript_file.exists()
    assert (processed_dir / transcript_file.name).exists()


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
        mock_create.return_value = _FakeTicketResult(
            success=True, url="https://example.atlassian.net/browse/PROJ-1"
        )
        from telegram_notify import TelegramSendError

        mock_send.side_effect = TelegramSendError("network down")

        exit_code = run.run()

    assert exit_code == 1
    assert transcript_file.exists()
    assert not (processed_dir / transcript_file.name).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest tests/test_run_end_to_end.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run'`

- [ ] **Step 3: Write the implementation**

`~/Desktop/meeting_copilot/run.py`:
```python
import sys

from config import MIN_TRANSCRIPT_CHARS, NAME_MAPPING_PATH, PROCESSED_DIR, TRANSCRIPTS_DIR
from credentials import load_credential
from jira_client import create_ticket
from name_mapping import load_name_mapping, resolve_name
from quote_verification import verify_quote
from report import build_report
from task_extraction import LLMCallError, LLMResponseParseError, extract_tasks
from telegram_notify import TelegramSendError, send_telegram_message
from transcript_source import find_latest_unprocessed, mark_processed, read_transcript

GROQ_API_KEY_PATH = "~/.credentials/groq_api_key.env"
JIRA_CREDENTIALS_PATH = "~/.credentials/jira_credentials.env"
TELEGRAM_CREDENTIALS_PATH = "~/.credentials/meeting_copilot_telegram.env"


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
        tasks = extract_tasks(transcript, name_mapping, api_key=groq_api_key)
    except (LLMCallError, LLMResponseParseError, FileNotFoundError, ValueError) as e:
        print(f"Не удалось обработать транскрипт: {e}")
        return 1

    created, needs_review, skipped, jira_errors = [], [], [], []

    if tasks:
        jira_base_url = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_BASE_URL")
        jira_email = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_EMAIL")
        jira_api_token = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_API_TOKEN")
        jira_project_key = load_credential(JIRA_CREDENTIALS_PATH, "JIRA_PROJECT_KEY")

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

    report_text = build_report(created, needs_review, skipped, jira_errors)
    print(report_text)

    try:
        bot_token = load_credential(TELEGRAM_CREDENTIALS_PATH, "TELEGRAM_BOT_TOKEN")
        chat_id = load_credential(TELEGRAM_CREDENTIALS_PATH, "TELEGRAM_CHAT_ID")
        send_telegram_message(bot_token, chat_id, report_text)
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
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full test suite**

Run: `cd ~/Desktop/meeting_copilot && python3 -m pytest -v`
Expected: PASS (all tests from Tasks 1–8, no failures)

- [ ] **Step 6: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add run.py tests/test_run_end_to_end.py
git commit -m "Add pipeline orchestrator wiring extraction, guards, Jira, and Telegram"
```

---

### Task 9: Setup docs and manual production-test runbook

**Files:**
- Create: `~/Desktop/meeting_copilot/README.md`

**Interfaces:**
- Consumes: nothing (documentation only, no code interfaces).

- [ ] **Step 1: Write the README**

`~/Desktop/meeting_copilot/README.md`:
```markdown
# Meeting Copilot — Jira Task Detection MVP

После рабочего созвона читает транскрипт, записанный `live_copilot_poc`,
одним проходом LLM находит устно поручённые задачи и заводит тикеты в Jira.
Полный дизайн — `docs/superpowers/specs/2026-08-27-jira-task-detection-mvp-design.md`.

## Установка

```bash
cd ~/Desktop/meeting_copilot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Нужные ключи

Как и в `live_copilot_poc`, ключи лежат в `~/.credentials/`, не в репозитории:

- `~/.credentials/groq_api_key.env` — уже должен существовать, если
  `live_copilot_poc` настроен. Формат: `GROQ_API_KEY=...`
- `~/.credentials/jira_credentials.env` — новый файл, четыре строки:
  ```
  JIRA_BASE_URL=https://ВАШ-ДОМЕН.atlassian.net
  JIRA_EMAIL=твой-email-в-jira
  JIRA_API_TOKEN=токен-из-id.atlassian.com/manage-profile/security/api-tokens
  JIRA_PROJECT_KEY=КЛЮЧ-ПРОЕКТА
  ```
- `~/.credentials/meeting_copilot_telegram.env` — новый бот через BotFather:
  ```
  TELEGRAM_BOT_TOKEN=токен-от-botfather
  TELEGRAM_CHAT_ID=твой-chat-id
  ```
  Chat ID проще всего получить, написав боту любое сообщение и открыв
  `https://api.telegram.org/bot<TOKEN>/getUpdates` — в ответе будет
  `"chat":{"id": ...}`.

## Таблица имён

`name_mapping.json` в корне проекта — редактируется руками, формат:

```json
{
  "Имя, как оно звучит на созвоне": "jira-username"
}
```

## Запуск

```bash
cd ~/Desktop/meeting_copilot
source venv/bin/activate
python3 run.py
```

Скрипт сам берёт самый свежий необработанный файл из
`~/Desktop/live_copilot_poc/transcripts/`. Обработанные файлы переезжают в
`~/Desktop/live_copilot_poc/transcripts/processed/`.

## Тесты

```bash
python3 -m pytest -v
```

Все внешние вызовы (Groq, Jira, Telegram) в тестах замоканы — `pytest`
никогда не делает реальных сетевых запросов.

## Ручная проверка на реальных сервисах (не автоматизирована)

Сделать один раз перед тем, как полагаться на пайплайн по-настоящему:

1. Заполнить все три файла credentials выше реальными значениями.
2. Заполнить `name_mapping.json` реальными именами команды.
3. Провести короткий тестовый созвон 1-на-1 через `live_copilot_poc`, вслух
   поручить себе или собеседнику конкретную задачу.
4. Запустить `python3 run.py`.
5. **Проверить формат поля assignee в Jira.** `jira_client.py` сейчас
   отправляет `{"assignee": {"name": ...}}` (Jira Server/Data Center стиль).
   Если ответ Jira API — ошибка про поле `assignee` или `accountId`, значит
   твой инстанс — Jira Cloud, и в `jira_client.py` нужно заменить
   `{"name": assignee_username}` на `{"accountId": ...}`, а в
   `name_mapping.json` хранить не username, а accountId (его можно достать
   через `GET /rest/api/3/myself` для себя или `GET /rest/api/3/user/search`
   для коллег).
6. Проверить, что тикет реально появился в Jira с правильным исполнителем и
   текстом задачи.
7. Проверить, что в Telegram пришло сообщение с этим тикетом в списке
   «Созданы».
8. Проверить, что обработанный файл переехал в `transcripts/processed/`.
```

- [ ] **Step 2: Commit**

```bash
cd ~/Desktop/meeting_copilot
git add README.md
git commit -m "Add setup instructions and manual production-test runbook"
```
