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
    except (OSError, ValueError) as e:
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
