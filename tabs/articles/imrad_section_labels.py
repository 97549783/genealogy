"""Вспомогательные функции отображения разделов статьи на русском языке."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

IMRAD_BLOCK_LABELS_RU = {
    "INTRODUCTION": "Введение",
    "METHOD_OR_APPROACH": "Методы",
    "RESULTS_OR_DEMONSTRATION": "Результаты",
    "DISCUSSION_OR_CONCLUSION": "Обсуждение и выводы",
    "SUPPLEMENTARY_OR_TEXTUAL": "Дополнительные сведения",
}

IMRAD_SUBBLOCK_LABELS_RU = {
    "aim": "Цель",
    "aim_or_research_question": "Цель и исследовательский вопрос",
    "problem_gap": "Проблема и дефицит",
    "context": "Контекст",
    "own_method": "Метод авторов",
    "own_method_or_approach": "Метод авторов",
    "data_or_material": "Данные и материалы",
    "findings": "Результаты",
    "own_results_or_findings": "Результаты авторов",
    "interpretation": "Интерпретация",
    "limitations": "Ограничения",
    "conclusion": "Выводы",
    "future_work": "Перспективы",
    "OWN_RESULTS_OR_FINDINGS": "Результаты авторов",
}

IMRAD_BLOCK_ORDER = [
    "INTRODUCTION",
    "METHOD_OR_APPROACH",
    "RESULTS_OR_DEMONSTRATION",
    "DISCUSSION_OR_CONCLUSION",
    "SUPPLEMENTARY_OR_TEXTUAL",
]


def is_empty_value(value: Any) -> bool:
    """Проверяет, что значение пустое/невалидное для отображения."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() == "nan"


def format_article_label_ru(row: pd.Series) -> str:
    """Формирует русскую метку статьи без технического идентификатора."""
    parts: list[str] = []
    title = str(row.get("Title", "") or "").strip()
    authors = str(row.get("Authors", "") or "").strip()
    year = str(row.get("Year", "") or "").strip()
    issue = str(row.get("Issue", "") or "").strip()
    if title:
        parts.append(title)
    if authors and authors.lower() != "nan":
        parts.append(authors)
    if year and year.lower() != "nan":
        parts.append(f"{year}.")
    if issue and issue.lower() != "nan":
        parts.append(f"№ {issue}")
    return " — ".join(parts) or "Статья без названия"


def format_keywords_ru(value: object) -> str:
    """Преобразует список ключевых слов в строку с русской пунктуацией."""
    if is_empty_value(value):
        return ""
    data = value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return ""
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            data = [s]
    if isinstance(data, list):
        items = [str(x).strip() for x in data if not is_empty_value(x)]
        return f"{', '.join(items)}." if items else ""
    text = str(data).strip()
    return f"{text}." if text else ""


def _map_label(value: object, mapping: dict[str, str]) -> str:
    if is_empty_value(value):
        return ""
    raw = str(value).strip()
    return mapping.get(raw) or mapping.get(raw.lower()) or mapping.get(raw.upper()) or raw.replace("_", " ").title()


def section_label_ru(row: pd.Series) -> str:
    """Возвращает русский заголовок раздела/подраздела."""
    subblock = _map_label(row.get("imrad_subblock"), IMRAD_SUBBLOCK_LABELS_RU)
    block = _map_label(row.get("imrad_block"), IMRAD_BLOCK_LABELS_RU)
    if subblock:
        return f"Раздел: {block} / подраздел: {subblock}" if block else f"Подраздел: {subblock}"
    return f"Раздел: {block}" if block else "Раздел"


def section_filter_key(row: pd.Series) -> str:
    """Формирует ключ фильтра раздела для внутренних сопоставлений."""
    block = str(row.get("imrad_block", "") or "").strip()
    sub = str(row.get("imrad_subblock", "") or "").strip()
    return f"{block}::{sub}"
