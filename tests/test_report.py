from report import build_report


def test_build_report_lists_created_tickets_with_links():
    created = [{"who": "Артём", "what": "сделать отчёт", "url": "https://x/browse/PROJ-1"}]

    text = build_report(created, [], [], [])

    assert "Артём" in text
    assert "сделать отчёт" in text
    assert "https://x/browse/PROJ-1" in text


def test_build_report_lists_needs_review_with_quote():
    needs_review = [{"who": "Артём", "what": "сделать отчёт", "quote": "выдуманная цитата"}]

    text = build_report([], needs_review, [], [])

    assert "требует проверки" in text.lower() or "требуют проверки" in text.lower()
    assert "выдуманная цитата" in text


def test_build_report_lists_skipped_unmatched_names():
    skipped = [{"who": "Незнакомец", "what": "что-то сделать", "quote": "цитата"}]

    text = build_report([], [], skipped, [])

    assert "Незнакомец" in text
    assert "пропущен" in text.lower()


def test_build_report_lists_jira_errors():
    jira_errors = [{"who": "Артём", "what": "сделать отчёт", "error": "403 Forbidden"}]

    text = build_report([], [], [], jira_errors)

    assert "403 Forbidden" in text


def test_build_report_says_no_tasks_when_all_empty():
    text = build_report([], [], [], [])

    assert "не найдено" in text.lower()
