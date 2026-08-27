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
