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
