import re


def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s.!?]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def verify_quote(quote: str, transcript: str) -> bool:
    return _normalize(quote) in _normalize(transcript)
