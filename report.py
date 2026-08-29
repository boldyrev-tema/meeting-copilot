def build_report(created, needs_review, skipped, jira_errors, summary_note=None):
    lines = ["Отчёт по обработке транскрипта:"]

    if created:
        lines.append("\n✅ Созданы тикеты:")
        for item in created:
            lines.append(f"- {item['who']}: {item['what']} — {item['url']}")

    if needs_review:
        lines.append("\n⚠️ Требуют проверки (цитата не найдена дословно):")
        for item in needs_review:
            lines.append(f"- {item['who']}: {item['what']} (цитата: «{item['quote']}»)")

    if skipped:
        lines.append("\n⏭ Пропущено (имя не сопоставлено):")
        for item in skipped:
            lines.append(f"- {item['who']}: {item['what']} (цитата: «{item['quote']}»)")

    if jira_errors:
        lines.append("\n❌ Ошибки создания тикета в Jira:")
        for item in jira_errors:
            lines.append(f"- {item['who']}: {item['what']} — {item['error']}")

    if not (created or needs_review or skipped or jira_errors):
        lines.append("\nЗадач не найдено.")

    if summary_note:
        lines.append(f"\n📝 {summary_note}")

    return "\n".join(lines)
