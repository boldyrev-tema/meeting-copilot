from summary_markdown import build_summary_markdown, derive_meeting_label


def test_derive_meeting_label_formats_date_and_time():
    assert derive_meeting_label("2026-08-28_10-00-00") == "2026-08-28 10:00"


def test_build_summary_markdown_lists_qa_pairs():
    qa_pairs = [
        {"question": "Когда релиз?", "answer": "В пятницу", "quote": "релиз в пятницу"}
    ]

    text = build_summary_markdown("2026-08-28 10:00", qa_pairs, [])

    assert "2026-08-28 10:00" in text
    assert "Когда релиз?" in text
    assert "В пятницу" in text


def test_build_summary_markdown_includes_needs_review_section():
    needs_review = [
        {
            "question": "Кто ответственный?",
            "answer": "Непонятно",
            "quote": "выдуманная цитата",
        }
    ]

    text = build_summary_markdown("2026-08-28 10:00", [], needs_review)

    assert "Требует проверки" in text
    assert "Кто ответственный?" in text


def test_build_summary_markdown_says_nothing_substantive_when_both_empty():
    text = build_summary_markdown("2026-08-28 10:00", [], [])

    assert "Ничего существенного не обсуждалось" in text
