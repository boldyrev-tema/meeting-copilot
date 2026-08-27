from quote_verification import verify_quote


def test_verify_quote_exact_match():
    transcript = "[10:00:00] Собеседник: Нужно сделать отчёт до пятницы."
    assert verify_quote("Нужно сделать отчёт до пятницы.", transcript) is True


def test_verify_quote_tolerates_case_punctuation_and_yo_e_variation():
    transcript = "[10:00:00] Собеседник: Нужно сделать ОТЧЁТ до пятницы!"
    assert verify_quote("нужно сделать отчет до пятницы", transcript) is True


def test_verify_quote_false_for_paraphrase():
    transcript = "[10:00:00] Собеседник: Нужно сделать отчёт до пятницы."
    assert verify_quote("Подготовь, пожалуйста, финансовый отчёт", transcript) is False


def test_verify_quote_false_when_fabricated():
    transcript = "[10:00:00] Собеседник: Привет, как дела?"
    assert verify_quote("Нужно сделать отчёт до пятницы.", transcript) is False


def test_verify_quote_false_when_splicing_across_sentence_boundary():
    transcript = "[10:00:00] Собеседник: Нужно сделать отчёт. До пятницы был другой разговор."
    assert verify_quote("нужно сделать отчёт до пятницы", transcript) is False


def test_verify_quote_true_when_quote_spans_two_stt_chunk_lines():
    # Speechmatics emits one transcript line per finalized speech chunk, so a
    # single spoken assignment can be split across two lines. The timestamp
    # and speaker prefix must not survive normalization and interrupt the
    # otherwise-continuous quote.
    transcript = (
        "[10:00:12] Собеседник: Артём, нужно сделать отчёт\n"
        "[10:00:15] Собеседник: до пятницы обязательно."
    )
    assert verify_quote("нужно сделать отчёт до пятницы обязательно", transcript) is True
