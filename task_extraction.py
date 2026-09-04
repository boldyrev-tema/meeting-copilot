import json

import requests

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
# Same free-tier fallback idea as daily_standup_matcher/hints.py (a bad
# minute on one provider is common, a different one recovers more often
# than retrying the same one) but a DIFFERENT order: hints.py runs live,
# during the daily, so it puts the fastest model (nano-omni) first. This
# runs postfactum, once per call — latency doesn't matter, quality does.
# Empirically (real run, sample_transcripts/example_with_task.txt, 4 сен
# 2026): nano-omni returned a validly-empty {"tasks": []} and MISSED the
# one real task in the transcript, while minimax-m3 and nemotron-3-super
# both found it correctly — so nano-omni is demoted to last-resort here,
# not the primary choice.
MODEL_CHAIN: list[tuple[str, dict]] = [
    ("minimax/minimax-m3:free", {}),
    ("nvidia/nemotron-3-super-120b-a12b:free", {"reasoning": {"enabled": False}}),
    ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", {"reasoning": {"enabled": False}}),
]

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
    base_payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(transcript, name_mapping)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    # Every stage (network call, response envelope, our own schema
    # validation) is retried across the whole model chain, not just the
    # network call — OpenRouter can return HTTP 200 with an error body
    # (e.g. {"error": {"message": "Upstream idle timeout exceeded"}}) when a
    # free model's backend is struggling, which raise_for_status() doesn't
    # catch, so "choices" is simply missing. Same reasoning as
    # daily_standup_matcher/hints.py's _request_hints.
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
            tasks = parsed["tasks"]

            if not isinstance(tasks, list):
                raise TypeError(f"tasks must be a list, got {type(tasks).__name__}")

            for task in tasks:
                if not isinstance(task, dict):
                    raise TypeError(f"task must be a dict, got {type(task).__name__}")
                if not all(k in task for k in ("who", "what", "quote")):
                    raise KeyError(f"task missing required keys: {task}")
                for k in ("who", "what", "quote"):
                    if not isinstance(task[k], str) or not task[k]:
                        raise TypeError(
                            f"task field {k!r} must be a non-empty string, got {task[k]!r}"
                        )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            last_error = LLMResponseParseError(f"{e} — raw response: {content!r}")
            continue

        return tasks

    raise last_error
