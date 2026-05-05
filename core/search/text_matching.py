from __future__ import annotations

import re

import pandas as pd

FUZZY_THRESHOLD = 75

SEARCH_MODE_FAST = "fast"
SEARCH_MODE_FUZZY = "fuzzy"

TEXT_SEARCH_MODE_LABELS = {
    SEARCH_MODE_FAST: "Быстрый поиск (строгое соответствие текста запроса написанию в автореферате)",
    SEARCH_MODE_FUZZY: "Нечёткий поиск (поиск, учитывающий различные варианты написания; требует существенно больше времени)",
}


def normalize_text(value: object) -> str:
    """Нормализует строку для текстового поиска."""
    if value is None:
        return ""
    s = str(value).strip().casefold().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"([а-яеa-z])\. ([а-яеa-z]\.)", r"\1.\2", s)
    return s


def strict_match_series(values: pd.Series, query: str) -> pd.Series:
    """Возвращает маску строгого подстрочного совпадения значений с запросом."""
    q = normalize_text(query)
    if not q:
        return pd.Series(False, index=values.index)
    prepared = values.map(normalize_text)
    return prepared.str.contains(q, regex=False, na=False)


def fuzzy_match_series(values: pd.Series, query: str, *, threshold: int = FUZZY_THRESHOLD) -> pd.Series:
    """Возвращает маску нечёткого совпадения значений с запросом."""
    q = normalize_text(query)
    if not q:
        return pd.Series(False, index=values.index)

    prepared = values.map(normalize_text)
    contains_mask = prepared.str.contains(q, regex=False, na=False)
    try:
        from rapidfuzz import fuzz  # type: ignore
    except Exception:
        return contains_mask

    fuzzy_mask = prepared.map(lambda v: bool(v) and fuzz.partial_ratio(q, v) >= threshold)
    return contains_mask | fuzzy_mask


def strict_match_value(value: object, query: str) -> bool:
    """Проверяет одно значение через строгий подстрочный поиск."""
    q = normalize_text(query)
    return bool(q) and q in normalize_text(value)


def fuzzy_match_value(value: object, query: str, *, threshold: int = FUZZY_THRESHOLD) -> bool:
    """Проверяет одно значение через нечёткий поиск."""
    if strict_match_value(value, query):
        return True
    q = normalize_text(query)
    v = normalize_text(value)
    if not q or not v:
        return False
    try:
        from rapidfuzz import fuzz  # type: ignore
    except Exception:
        return False
    return fuzz.partial_ratio(q, v) >= threshold
