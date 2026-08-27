import re

_LINE_PREFIX_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*[^:]+:\s*", flags=re.MULTILINE)


def _strip_line_prefixes(transcript: str) -> str:
    lines = transcript.splitlines()
    stripped_lines = [_LINE_PREFIX_RE.sub("", line) for line in lines]
    return " ".join(stripped_lines)


def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s.!?]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def verify_quote(quote: str, transcript: str) -> bool:
    return _normalize(quote) in _normalize(_strip_line_prefixes(transcript))
