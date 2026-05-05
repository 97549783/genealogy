"""Инструменты текстового поиска."""

from .text_matching import (
    FUZZY_THRESHOLD,
    SEARCH_MODE_FAST,
    SEARCH_MODE_FUZZY,
    TEXT_SEARCH_MODE_LABELS,
    fuzzy_match_series,
    fuzzy_match_value,
    normalize_text,
    strict_match_series,
    strict_match_value,
)

__all__ = [
    "FUZZY_THRESHOLD",
    "SEARCH_MODE_FAST",
    "SEARCH_MODE_FUZZY",
    "TEXT_SEARCH_MODE_LABELS",
    "normalize_text",
    "strict_match_series",
    "strict_match_value",
    "fuzzy_match_series",
    "fuzzy_match_value",
]
