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

        # Validate tasks is a list
        if not isinstance(tasks, list):
            raise TypeError(f"tasks must be a list, got {type(tasks).__name__}")

        # Validate each task has required keys
        for task in tasks:
            if not isinstance(task, dict):
                raise TypeError(f"task must be a dict, got {type(task).__name__}")
            if not all(k in task for k in ("who", "what", "quote")):
                raise KeyError(f"task missing required keys: {task}")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise LLMResponseParseError(str(e)) from e

    return tasks
