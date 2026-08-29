def derive_meeting_label(transcript_stem: str) -> str:
    date_part, _, time_part = transcript_stem.partition("_")
    hh, mm, _ss = time_part.split("-")
    return f"{date_part} {hh}:{mm}"


def build_summary_markdown(meeting_label: str, qa_pairs: list, needs_review: list) -> str:
    lines = [f"# Саммари созвона — {meeting_label}"]

    if qa_pairs:
        lines.append("\n## Обсуждали")
        for item in qa_pairs:
            lines.append(f"\n### {item['question']}")
            lines.append(item["answer"])

    if needs_review:
        lines.append("\n## Требует проверки (цитата не найдена дословно)")
        for item in needs_review:
            lines.append(f"\n- **Вопрос:** {item['question']}")
            lines.append(f"  **Ответ (не подтверждён):** {item['answer']}")

    if not qa_pairs and not needs_review:
        lines.append("\nНичего существенного не обсуждалось.")

    return "\n".join(lines)
