import json

import requests

from task_extraction import LLMCallError, LLMResponseParseError

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
# Same fallback chain and order as task_extraction.py — see that file's
# comment for why nano-omni is last here (postfactum, quality over speed;
# it empirically missed a task minimax-m3/nemotron-3-super both found).
MODEL_CHAIN: list[tuple[str, dict]] = [
    ("minimax/minimax-m3:free", {}),
    ("nvidia/nemotron-3-super-120b-a12b:free", {"reasoning": {"enabled": False}}),
    ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", {"reasoning": {"enabled": False}}),
]

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
    "- Поле quote НЕ должно включать метку времени и имя говорящего в начале "
    "строки (например, «[10:03:02] Собеседник:») — только сами произнесённые "
    "слова.\n"
    "- Если содержательного обсуждения не было — верни {\"items\": []}.\n"
    "- Не придумывай вопросы или решения, которых нет в тексте."
)


def extract_qa_pairs(transcript: str, api_key: str) -> list:
    base_payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Транскрипт созвона:\n{transcript}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    # Every stage (network call, response envelope, our own schema
    # validation) is retried across the whole model chain, not just the
    # network call — see task_extraction.py's extract_tasks for why.
    last_error: Exception = LLMCallError("no models in MODEL_CHAIN")
    for model, extra in MODEL_CHAIN:
        payload = {**base_payload, "model": model, **extra}
        try:
            resp = requests.post(
                OPENROUTER_ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            last_error = LLMCallError(str(e))
            continue

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            last_error = LLMResponseParseError(str(e))
            continue

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
            last_error = LLMResponseParseError(f"{e} — raw response: {content!r}")
            continue

        return items

    raise last_error
