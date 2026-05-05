import pandas as pd

from core.search.text_matching import fuzzy_match_series, normalize_text, strict_match_series


def test_normalize_text_initials_and_yo() -> None:
    assert normalize_text("Е. А.") == normalize_text("Е.А.")
    assert normalize_text("Пётр") == normalize_text("Петр")


def test_strict_match_series_contains_after_normalization() -> None:
    s = pd.Series(["МГУ имени М.В. Ломоносова", "СПбГУ"])
    mask = strict_match_series(s, "мгу")
    assert mask.tolist() == [True, False]


def test_fuzzy_match_series_contains_and_empty_query() -> None:
    s = pd.Series(["Московский государственный университет", "КФУ"])
    mask = fuzzy_match_series(s, "московский")
    assert mask.tolist() == [True, False]
    empty_mask = fuzzy_match_series(s, "")
    assert empty_mask.tolist() == [False, False]
