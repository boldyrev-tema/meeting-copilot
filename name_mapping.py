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
