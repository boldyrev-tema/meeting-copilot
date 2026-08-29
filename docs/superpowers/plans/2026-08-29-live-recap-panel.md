# Live Recap Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Closing the `live_copilot_poc` suflyor window automatically triggers `meeting_copilot/run.py` in the background, and a new collapsible panel in the suflyor's own window shows the most recent past-call summary the moment the window opens, so the person never has to manually run a script or ask what was discussed last time.

**Architecture:** All new code lives in `~/Desktop/live_copilot_poc/live_copilot_poc.py` — `meeting_copilot` itself is not modified. A new background-subprocess trigger is appended to the existing `on_closed()` lifecycle hook. Two new read-only `Api` methods expose `meeting_copilot/summaries/*.md` to a new HTML/JS panel that reuses the codebase's existing collapsible-section pattern, just defaulting to open instead of closed.

**Tech Stack:** Python 3 (stdlib only: `os`, `subprocess`), vanilla JS (no framework, matching the existing `live_copilot_poc.py` HTML/JS), the project's existing flat-script test runner (`test_poc.py` — no pytest, no mocking library; Part 1 is plain assertions via a `check()` helper, Part 2 drives real Chromium via Playwright against the extracted HTML with `pywebview.api` stubbed).

**Spec:** `/Users/tema/Desktop/meeting_copilot/docs/superpowers/specs/2026-08-29-live-recap-panel-design.md`

## Global Constants

- `MEETING_COPILOT_DIR = os.path.expanduser("~/Desktop/meeting_copilot")` — hardcoded sibling-project path, same style as the existing `TRANSCRIPTS_DIR` constant (no env-var override; `live_copilot_poc.py` has no precedent for that pattern).
- The auto-trigger subprocess uses `meeting_copilot`'s own venv Python (`MEETING_COPILOT_DIR/venv/bin/python3`) and runs with `cwd=MEETING_COPILOT_DIR` — never imports `meeting_copilot` code into the `live_copilot_poc` process (different venvs, different dependencies).
- `_trigger_meeting_copilot_run()` must never raise out of `on_closed()` — a failure there must not block window shutdown. Wrap in `try/except Exception`.
- `read_summary(filename)` must reject any `filename` that resolves outside `MEETING_COPILOT_SUMMARIES_DIR` (path traversal guard) — return an error string, never raise.
- New JS functions (`renderPastSummaries`, `renderSummaryContent`) must be plain, synchronous, callable directly with test data — matching the existing `addKbFile()`/`renderBattlecards()` pattern that `test_poc.py`'s Playwright suite already exercises directly, not only via the mocked async `pywebview.api` round-trip.
- `auto_run.log` and `meeting_copilot`'s own `summaries/` are personal runtime data, not example content — `auto_run.log` must be added to `live_copilot_poc/.gitignore`.

---

### Task 1: Auto-trigger `meeting_copilot/run.py` when the suflyor window closes

**Files:**
- Modify: `~/Desktop/live_copilot_poc/live_copilot_poc.py` (constants near `TRANSCRIPTS_DIR` at line 302; new functions near line 305; `on_closed()` at line 1357)
- Modify: `~/Desktop/live_copilot_poc/.gitignore`
- Test: `~/Desktop/live_copilot_poc/test_poc.py` (append to Part 1, before the `backend_passed, backend_failed = ...` line)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `MEETING_COPILOT_DIR` (str, absolute path), `MEETING_COPILOT_AUTO_RUN_LOG` (str, absolute path) — module-level constants Task 2 also uses. `_build_auto_run_command() -> list[str]` and `_trigger_meeting_copilot_run() -> None` — used only within this task and by `on_closed()`.

- [ ] **Step 1: Write the failing test**

First, add two new imports at the top of `~/Desktop/live_copilot_poc/test_poc.py`, alongside the existing `import` block (around line 22-28):

```python
import http.server
import json
import os
import shutil
import socketserver
import sys
import tempfile
import threading
import time
```

(`shutil` was previously only imported inline inside the Playwright `finally` block — this makes it a normal top-level import used by multiple parts of the file; `tempfile` is new. Both are needed by this task's own test below, and Task 2 reuses them too.)

Then find this line (around line 274-276):

```python
m.ask_for_suggestion = orig_ask
m.HOTWORD = orig_hotword
m.transcript_lines.clear()

backend_passed, backend_failed = len(passed), len(failed)
```

Insert this block immediately **before** the `backend_passed, backend_failed = ...` line:

```python
print()
print("=== Авто-запуск meeting_copilot/run.py при закрытии окна ===")
check(
    "_build_auto_run_command: венв-python meeting_copilot + run.py",
    m._build_auto_run_command() == [m.MEETING_COPILOT_VENV_PYTHON, "run.py"],
    m._build_auto_run_command(),
)
check(
    "MEETING_COPILOT_DIR: указывает на сестринский проект",
    m.MEETING_COPILOT_DIR.endswith("meeting_copilot"),
    m.MEETING_COPILOT_DIR,
)

# _trigger_meeting_copilot_run() не должно падать, даже если сам venv не существует —
# подменяем путь на заведомо отсутствующий, и лог-файл на временный (чтобы не писать
# в реальный ~/Desktop/meeting_copilot/auto_run.log при прогоне тестов), и проверяем,
# что вызов не бросает исключение.
orig_venv_python = m.MEETING_COPILOT_VENV_PYTHON
orig_auto_run_log = m.MEETING_COPILOT_AUTO_RUN_LOG
trigger_test_dir = tempfile.mkdtemp()
m.MEETING_COPILOT_VENV_PYTHON = "/nonexistent/path/python3"
m.MEETING_COPILOT_AUTO_RUN_LOG = os.path.join(trigger_test_dir, "auto_run.log")
try:
    m._trigger_meeting_copilot_run()
    trigger_did_not_raise = True
except Exception as e:
    trigger_did_not_raise = False
    trigger_exception = e
check(
    "_trigger_meeting_copilot_run: не бросает исключение даже при отсутствующем venv",
    trigger_did_not_raise,
    None if trigger_did_not_raise else trigger_exception,
)
m.MEETING_COPILOT_VENV_PYTHON = orig_venv_python
m.MEETING_COPILOT_AUTO_RUN_LOG = orig_auto_run_log
shutil.rmtree(trigger_test_dir, ignore_errors=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/live_copilot_poc && venv/bin/python3 test_poc.py`
Expected: FAIL — `AttributeError: module 'live_copilot_poc' has no attribute '_build_auto_run_command'` (or `MEETING_COPILOT_VENV_PYTHON`), since none of this exists yet.

- [ ] **Step 3: Write the implementation**

In `~/Desktop/live_copilot_poc/live_copilot_poc.py`, find this block (around line 302-303):

```python
TRANSCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "transcripts")
transcript_file = None  # открывается в after_start(), одна сессия — один файл
```

Replace it with:

```python
TRANSCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "transcripts")
transcript_file = None  # открывается в after_start(), одна сессия — один файл

# meeting_copilot — сестринский проект, свой venv и свои зависимости (Groq/Jira-клиент
# против Speechmatics/pywebview здесь) — поэтому запускается отдельным процессом, а не
# импортируется. См. docs/superpowers/specs/2026-08-29-live-recap-panel-design.md
# в meeting_copilot.
MEETING_COPILOT_DIR = os.path.expanduser("~/Desktop/meeting_copilot")
MEETING_COPILOT_VENV_PYTHON = os.path.join(MEETING_COPILOT_DIR, "venv", "bin", "python3")
MEETING_COPILOT_AUTO_RUN_LOG = os.path.join(MEETING_COPILOT_DIR, "auto_run.log")


def _build_auto_run_command():
    return [MEETING_COPILOT_VENV_PYTHON, "run.py"]


def _trigger_meeting_copilot_run():
    # Фоновый, неблокирующий запуск: on_closed() не должен ждать LLM-вызовы run.py,
    # и падение здесь (venv не найден и т.п.) не должно мешать закрытию окна суфлёра —
    # поэтому широкий except, а не конкретные типы исключений.
    try:
        with open(MEETING_COPILOT_AUTO_RUN_LOG, "a") as log_file:
            subprocess.Popen(
                _build_auto_run_command(),
                cwd=MEETING_COPILOT_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # не убивается при выходе родительского процесса
            )
    except Exception as e:
        print(f"не удалось запустить meeting_copilot/run.py автоматически: {e}")
```

Then find `on_closed()` (around line 1357):

```python
def on_closed():
    global running
    running = False
    if hotkey_listener:
        try:
            hotkey_listener.stop()
        except Exception as e:
            print(f"hotkey listener stop failed: {e}")
    if speechmatics_loop:
        if mic_audio_queue is not None:
            speechmatics_loop.call_soon_threadsafe(mic_audio_queue.put_nowait, None)
        if system_audio_queue is not None:
            speechmatics_loop.call_soon_threadsafe(system_audio_queue.put_nowait, None)
    if transcript_file:
        transcript_file.close()
```

Add one line at the end, after `transcript_file.close()` (so the transcript is already flushed to disk before `run.py` looks for it):

```python
def on_closed():
    global running
    running = False
    if hotkey_listener:
        try:
            hotkey_listener.stop()
        except Exception as e:
            print(f"hotkey listener stop failed: {e}")
    if speechmatics_loop:
        if mic_audio_queue is not None:
            speechmatics_loop.call_soon_threadsafe(mic_audio_queue.put_nowait, None)
        if system_audio_queue is not None:
            speechmatics_loop.call_soon_threadsafe(system_audio_queue.put_nowait, None)
    if transcript_file:
        transcript_file.close()
    _trigger_meeting_copilot_run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/live_copilot_poc && venv/bin/python3 test_poc.py`
Expected: the three new checks under "Авто-запуск meeting_copilot/run.py при закрытии окна" PASS. (Other backend/UI checks continue to run — don't worry about pre-existing unrelated failures if the environment lacks Playwright/API keys; the task is done when the new checks pass and no new failures appear that weren't there before Step 1.)

- [ ] **Step 5: Update `.gitignore`**

Open `~/Desktop/live_copilot_poc/.gitignore`. Current content:

```
venv/
__pycache__/
*.pyc
transcripts/
*.png
_screenshot.png
```

Append one line:

```
venv/
__pycache__/
*.pyc
transcripts/
*.png
_screenshot.png
auto_run.log
```

- [ ] **Step 6: Commit**

```bash
cd ~/Desktop/live_copilot_poc
git add live_copilot_poc.py test_poc.py .gitignore
git commit -m "Auto-trigger meeting_copilot/run.py when the suflyor window closes"
```

---

### Task 2: Read-only access to `meeting_copilot`'s past summaries

**Files:**
- Modify: `~/Desktop/live_copilot_poc/live_copilot_poc.py` (constants near `MEETING_COPILOT_AUTO_RUN_LOG` from Task 1; new module functions near line 305; new `Api` methods after `clear_knowledge_base` at line 934)
- Test: `~/Desktop/live_copilot_poc/test_poc.py` (append to Part 1, same insertion point as Task 1's tests — right before `backend_passed, backend_failed = ...`)

**Interfaces:**
- Consumes: `MEETING_COPILOT_DIR` (Task 1).
- Produces: `MEETING_COPILOT_SUMMARIES_DIR` (str) — module constant. `_format_meeting_label(stem: str) -> str`, `list_past_summaries() -> list[dict]` (each dict: `{"filename": str, "label": str}`, newest first), `read_summary(filename: str) -> str` (file content, or a Russian error string — never raises). `Api.list_past_summaries(self) -> list[dict]` and `Api.read_summary(self, filename: str) -> str` — thin delegating methods Task 3's JS calls via `pywebview.api.list_past_summaries()` / `pywebview.api.read_summary(filename)`.

- [ ] **Step 1: Write the failing test**

In `~/Desktop/live_copilot_poc/test_poc.py`, insert this block right after the block Task 1 added (still before `backend_passed, backend_failed = ...`):

```python
print()
print("=== Чтение прошлых саммари из meeting_copilot/summaries ===")
check(
    "_format_meeting_label: дата и время из имени файла-транскрипта",
    m._format_meeting_label("2026-08-28_10-00-00") == "2026-08-28 10:00",
    m._format_meeting_label("2026-08-28_10-00-00"),
)

summaries_test_dir = tempfile.mkdtemp()
orig_summaries_dir = m.MEETING_COPILOT_SUMMARIES_DIR
m.MEETING_COPILOT_SUMMARIES_DIR = summaries_test_dir
try:
    check(
        "list_past_summaries: пустая папка -> пустой список",
        m.list_past_summaries() == [],
    )

    with open(os.path.join(summaries_test_dir, "2026-08-27_09-00-00.md"), "w") as f:
        f.write("# старое саммари")
    with open(os.path.join(summaries_test_dir, "2026-08-28_10-00-00.md"), "w") as f:
        f.write("# новое саммари")
    with open(os.path.join(summaries_test_dir, "not_a_summary.txt"), "w") as f:
        f.write("игнорируется — не .md")

    listing = m.list_past_summaries()
    check(
        "list_past_summaries: только .md-файлы, 2 штуки",
        len(listing) == 2,
        listing,
    )
    check(
        "list_past_summaries: новые сверху",
        listing[0]["filename"] == "2026-08-28_10-00-00.md",
        listing,
    )
    check(
        "list_past_summaries: label читаемый",
        listing[0]["label"] == "2026-08-28 10:00",
        listing,
    )

    # Файл с именем не в ожидаемом формате не должен ронять весь список —
    # тот же класс бага, что уже один раз ловили в meeting_copilot/run.py.
    # Отдельно от проверки сортировки выше: позиция такого файла в списке не
    # гарантируется (лексикографический порядок кривого имени непредсказуем),
    # важно только что список не падает и что-то разумное показывает.
    with open(os.path.join(summaries_test_dir, "bad-name.md"), "w") as f:
        f.write("# файл с именем не по формату транскрипта")
    listing_with_bad_name = m.list_past_summaries()
    check(
        "list_past_summaries: файл с кривым именем не роняет список (теперь 3 штуки)",
        len(listing_with_bad_name) == 3,
        listing_with_bad_name,
    )
    check(
        "list_past_summaries: для кривого имени label = само имя файла (не исключение)",
        any(
            item["filename"] == "bad-name.md" and item["label"] == "bad-name.md"
            for item in listing_with_bad_name
        ),
        listing_with_bad_name,
    )

    check(
        "read_summary: возвращает реальное содержимое файла",
        m.read_summary("2026-08-28_10-00-00.md") == "# новое саммари",
    )
    check(
        "read_summary: несуществующий файл -> понятная ошибка, не исключение",
        "не найден" in m.read_summary("нет_такого.md").lower(),
    )
    check(
        "read_summary: path traversal через ../ отклонён",
        "недопустимое" in m.read_summary("../../etc/passwd").lower(),
    )
    check(
        "read_summary: абсолютный путь отклонён",
        "недопустимое" in m.read_summary("/etc/passwd").lower(),
    )
finally:
    m.MEETING_COPILOT_SUMMARIES_DIR = orig_summaries_dir
    shutil.rmtree(summaries_test_dir, ignore_errors=True)
```

(`os`, `shutil`, and `tempfile` are already imported at the top of `test_poc.py` from Task 1 — nothing new to add here.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/live_copilot_poc && venv/bin/python3 test_poc.py`
Expected: FAIL — `AttributeError: module 'live_copilot_poc' has no attribute '_format_meeting_label'`.

- [ ] **Step 3: Write the implementation**

In `~/Desktop/live_copilot_poc/live_copilot_poc.py`, extend the block Task 1 added (right after `MEETING_COPILOT_AUTO_RUN_LOG`):

```python
MEETING_COPILOT_DIR = os.path.expanduser("~/Desktop/meeting_copilot")
MEETING_COPILOT_VENV_PYTHON = os.path.join(MEETING_COPILOT_DIR, "venv", "bin", "python3")
MEETING_COPILOT_AUTO_RUN_LOG = os.path.join(MEETING_COPILOT_DIR, "auto_run.log")
MEETING_COPILOT_SUMMARIES_DIR = os.path.join(MEETING_COPILOT_DIR, "summaries")


def _build_auto_run_command():
    return [MEETING_COPILOT_VENV_PYTHON, "run.py"]


def _trigger_meeting_copilot_run():
    try:
        with open(MEETING_COPILOT_AUTO_RUN_LOG, "a") as log_file:
            subprocess.Popen(
                _build_auto_run_command(),
                cwd=MEETING_COPILOT_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception as e:
        print(f"не удалось запустить meeting_copilot/run.py автоматически: {e}")


def _format_meeting_label(stem):
    # Тот же формат, что meeting_copilot/summary_markdown.py:derive_meeting_label —
    # дублируется здесь намеренно (2 строки), а не импортируется, чтобы не тянуть
    # meeting_copilot как зависимость (см. комментарий у MEETING_COPILOT_DIR).
    date_part, _, time_part = stem.partition("_")
    hh, mm, _ss = time_part.split("-")
    return f"{date_part} {hh}:{mm}"


def list_past_summaries():
    if not os.path.isdir(MEETING_COPILOT_SUMMARIES_DIR):
        return []
    files = sorted(
        (f for f in os.listdir(MEETING_COPILOT_SUMMARIES_DIR) if f.endswith(".md")),
        reverse=True,  # имена файлов — YYYY-MM-DD_HH-MM-SS.md, лексикографически = по дате
    )
    result = []
    for f in files:
        try:
            label = _format_meeting_label(f[:-len(".md")])
        except ValueError:
            # Имя файла не в ожидаемом формате (кто-то положил сюда что-то руками) —
            # тот же класс бага, что уже один раз ловили в meeting_copilot/run.py на
            # derive_meeting_label. Не роняем весь список из-за одного файла — просто
            # показываем сырое имя вместо распарсенной даты.
            label = f
        result.append({"filename": f, "label": label})
    return result


def read_summary(filename):
    base = os.path.abspath(MEETING_COPILOT_SUMMARIES_DIR)
    target = os.path.abspath(os.path.join(base, filename))
    if not (target == base or target.startswith(base + os.sep)):
        return "Ошибка: недопустимое имя файла."
    if not os.path.isfile(target):
        return "Файл не найден."
    with open(target, encoding="utf-8") as f:
        return f.read()
```

Then, in the `Api` class, find `clear_knowledge_base` (around line 932-934):

```python
    def clear_knowledge_base(self):
        knowledge_base_chunks.clear()
        js("addKbFile(null, 0)")
```

Add two new methods immediately after it (still before `add_battlecard`):

```python
    def clear_knowledge_base(self):
        knowledge_base_chunks.clear()
        js("addKbFile(null, 0)")

    def list_past_summaries(self):
        return list_past_summaries()

    def read_summary(self, filename):
        return read_summary(filename)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/live_copilot_poc && venv/bin/python3 test_poc.py`
Expected: all checks under "Чтение прошлых саммари из meeting_copilot/summaries" PASS, plus Task 1's checks still PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/live_copilot_poc
git add live_copilot_poc.py test_poc.py
git commit -m "Add read-only access to meeting_copilot's past-call summaries"
```

---

### Task 3: «Прошлые созвоны» panel in the suflyor UI

**Files:**
- Modify: `~/Desktop/live_copilot_poc/live_copilot_poc.py` (HTML around line 1149, after the "База знаний" section; CSS in the `<style>` block starting line 996; JS near the other render functions, e.g. after `addKbFile` around line 1249; a top-level call near the end of the `<script>` block before line 1319)
- Test: `~/Desktop/live_copilot_poc/test_poc.py` (append to the Playwright `results` block, inside the `page.evaluate("""...""")` string, before `return results;`)

**Interfaces:**
- Consumes: `Api.list_past_summaries` and `Api.read_summary` (Task 2) via `pywebview.api.list_past_summaries()` / `pywebview.api.read_summary(filename)` — both return Promises in the real webview bridge, resolved with the same shapes Task 2 defined.
- Produces: JS functions `renderPastSummaries(files)`, `renderSummaryContent(text)`, `loadPastSummary(filename)`, `loadPastSummaries()`, `togglePastCalls()` — no other task depends on these.

- [ ] **Step 1: Write the failing test**

In `~/Desktop/live_copilot_poc/test_poc.py`, inside the big `page.evaluate("""() => { ... }""")` string (Part 2), find the end of the script (just before `return results;`, around line 391-393):

```javascript
  addSuggestion('Скидка 20%', 'battlecard');
  check('addSuggestion(battlecard): label корректный', document.getElementById('feed').lastElementChild.querySelector('.who').textContent.includes('Карточка'));

  return results;
```

Insert this block right before `return results;`:

```javascript
  const pastList = [
    {filename: '2026-08-28_10-00-00.md', label: '2026-08-28 10:00'},
    {filename: '2026-08-27_09-00-00.md', label: '2026-08-27 09:00'},
  ];
  renderPastSummaries(pastList);
  const pastListEl = document.getElementById('pastCallsList');
  check('renderPastSummaries: оба файла отрисованы', pastListEl.querySelectorAll('.past-call-item').length === 2, pastListEl.innerHTML);
  check('renderPastSummaries: label первого файла виден', pastListEl.textContent.includes('2026-08-28 10:00'));

  renderPastSummaries([]);
  check('renderPastSummaries: пустой список -> нейтральное сообщение', pastListEl.textContent.includes('нет прошлых созвонов'), pastListEl.textContent);

  renderSummaryContent('# Саммари\n\nТестовое содержимое.');
  check('renderSummaryContent: текст саммари отображён', document.getElementById('pastCallContent').textContent.includes('Тестовое содержимое.'));

  loadPastSummary('2026-08-28_10-00-00.md');
  check('loadPastSummary: api.read_summary вызван с именем файла', window.__calls.some(c => c[0]==='read_summary' && c[1][0]==='2026-08-28_10-00-00.md'));

  const pastSection = document.getElementById('pastCallsSection');
  const wasVisible = pastSection.style.display !== 'none';
  togglePastCalls();
  check('togglePastCalls: переключает видимость секции', (pastSection.style.display !== 'none') !== wasVisible);
  togglePastCalls();

  return results;
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/live_copilot_poc && venv/bin/python3 test_poc.py`
Expected: FAIL with a Playwright/console error like `renderPastSummaries is not defined` (if Playwright isn't installed in this environment, this step is skipped with a printed message — install it first per the message printed by `test_poc.py`, or note the skip and continue; don't treat a Playwright-not-installed skip as this step passing).

- [ ] **Step 3: Write the implementation**

In `~/Desktop/live_copilot_poc/live_copilot_poc.py`, find the CSS `.pill.active` rule (around line 1044) and add one rule for the new list item right after the existing `.file-chip` rules (around line 1063-1069), reusing the existing color variables:

```css
  .past-call-item {
    padding: 6px 8px; border-radius: 8px; cursor: pointer; font-size: 12px; color: var(--text-dim);
    transition: background 0.15s ease, color 0.15s ease;
  }
  .past-call-item:hover { background: rgba(255,255,255,0.06); color: var(--text); }
  .past-call-empty { font-size: 11px; color: var(--text-dim); padding: 4px 0; }
  #pastCallContent {
    font-size: 11px; color: var(--text-dim); white-space: pre-wrap; max-height: 160px;
    overflow-y: auto; margin-top: 6px; padding: 8px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 10px;
    opacity: 0; transition: opacity 0.2s ease;
  }
  #pastCallContent:not(:empty) { opacity: 1; }
```

(`transition` timings and easing match the existing `.pill` rule exactly — same subtle, fast feel, per the Apple-aesthetic direction from the spec. `#pastCallContent`'s opacity fade is the one deliberate bit of motion: empty by default, fades in only once `renderSummaryContent` actually puts text in it.)

Find the "База знаний" section (around line 1143-1149):

```html
  <div class="section">
    <div class="section-label">
      База знаний <span style="text-transform:none; opacity:.6">— по релевантности</span>
      <button class="link-btn" onclick="pywebview.api.pick_knowledge_file()">добавить файл</button>
    </div>
    <div class="file-chip" id="kbChip">📚 <span id="kbChipText"></span> <button onclick="clearKb()">✕</button></div>
  </div>
```

Add a new section right after it, defaulting to visible (`display:block`, unlike "Транскрипт"/"Карточки" which default to `display:none`):

```html
  <div class="section" id="pastCallsSection" style="display:block">
    <div class="section-label">
      Прошлые созвоны
      <button class="link-btn" onclick="togglePastCalls()">свернуть/развернуть</button>
    </div>
    <div id="pastCallsList"></div>
    <div id="pastCallContent"></div>
  </div>
```

Find `addKbFile` in the `<script>` block (around line 1241-1249):

```javascript
function addKbFile(name, totalChunks) {
  const chip = document.getElementById('kbChip');
  if (name) {
    chip.style.display = 'flex';
    document.getElementById('kbChipText').textContent = name + ' (' + totalChunks + ' фрагм. всего)';
  } else {
    chip.style.display = 'none';
  }
}

function clearKb() { pywebview.api.clear_knowledge_base(); }
```

Add the new panel's functions right after `clearKb`:

```javascript
function renderPastSummaries(files) {
  const list = document.getElementById('pastCallsList');
  list.innerHTML = '';
  if (!files.length) {
    const empty = document.createElement('div');
    empty.className = 'past-call-empty';
    empty.textContent = 'пока нет прошлых созвонов';
    list.appendChild(empty);
    return;
  }
  files.forEach(f => {
    const item = document.createElement('div');
    item.className = 'past-call-item';
    item.textContent = f.label;
    item.onclick = () => loadPastSummary(f.filename);
    list.appendChild(item);
  });
}

function renderSummaryContent(text) {
  document.getElementById('pastCallContent').textContent = text;
}

function loadPastSummary(filename) {
  pywebview.api.read_summary(filename).then(renderSummaryContent);
}

function loadPastSummaries() {
  pywebview.api.list_past_summaries().then(renderPastSummaries);
}

function togglePastCalls() {
  const el = document.getElementById('pastCallsSection');
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
```

Finally, find the end of the `<script>` block (just before `</script>` at line 1319 — after `function addBattlecard() { ... }`) and add one top-level call so the panel populates itself as soon as the window loads, without requiring a click:

```javascript
loadPastSummaries();
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/live_copilot_poc && venv/bin/python3 test_poc.py`
Expected: all new Playwright checks PASS (or, if Playwright isn't installed in this environment, the printed skip message appears and every other check still passes — note in your report which case occurred, since a real PASS on this step requires Playwright to actually be present).

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/live_copilot_poc
git add live_copilot_poc.py test_poc.py
git commit -m "Add auto-expanding past-calls recap panel to the suflyor window"
```

---

### Task 4: Document the auto-trigger and recap panel in the README

**Files:**
- Modify: `~/Desktop/live_copilot_poc/README.md`

**Interfaces:**
- Consumes: nothing (documentation only).

- [ ] **Step 1: Write the README addition**

Add a new subsection right after the `## Архитектура` heading (line 94) — insert it as the first thing under that heading, before whatever currently follows it:

```markdown
## Архитектура

### Авто-запуск meeting_copilot и панель «Прошлые созвоны» (29 авг 2026)

При закрытии окна суфлёра (`on_closed()`) в фоне, неблокирующим `subprocess`,
запускается `~/Desktop/meeting_copilot/run.py` — он сам находит только что
закрытый транскрипт, генерирует Jira-тикеты и Q&A-саммари звонка. Раньше это
нужно было запускать руками.

В самом окне суфлёра есть секция «Прошлые созвоны» (развёрнута по
умолчанию) — список файлов из `meeting_copilot/summaries/`, клик показывает
содержимое прямо в этом же окне. Просто чтение файла с диска — без
эмбеддингов, без вызова LLM в момент показа; данные уже проверены цитатами
на этапе генерации в `meeting_copilot`.

Подробный дизайн и разбор альтернатив —
`meeting_copilot/docs/superpowers/specs/2026-08-29-live-recap-panel-design.md`.

Известные ограничения: единственный сигнал «звонок закончился» — закрытие
окна (нет bot-join агента, который бы детектил завершение конференции
напрямую); панель показывает просто самый свежий файл, не «релевантный
именно этому звонку» (нет привязки к календарю/участникам).
```

- [ ] **Step 2: Commit**

```bash
cd ~/Desktop/live_copilot_poc
git add README.md
git commit -m "Document the auto-trigger and past-calls recap panel"
```
