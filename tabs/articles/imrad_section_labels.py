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
    "aim": "Цель и исследовательский вопрос",
    "aim_or_research_question": "Цель и исследовательский вопрос",
    "research_question": "Исследовательский вопрос",
    "problem_gap": "Проблема и ограничения",
    "problem_or_gap": "Проблема и ограничения",
    "research_gap": "Проблема и ограничения",
    "context": "Контекст",
    "background": "Контекст",
    "own_method": "Метод авторов",
    "own_method_or_approach": "Метод авторов",
    "method": "Метод",
    "data_or_material": "Данные и материалы",
    "materials": "Данные и материалы",
    "sample": "Выборка",
    "findings": "Результаты авторов",
    "own_results_or_findings": "Результаты авторов",
    "results": "Результаты",
    "interpretation": "Интерпретация результатов",
    "limitations": "Ограничения исследования",
    "conclusion": "Выводы",
    "future_work": "Перспективы исследования",
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


def _map_label(value: object, mapping: dict[str, str], fallback: str = "") -> str:
    if is_empty_value(value):
        return ""
    raw = str(value).strip()
    return mapping.get(raw) or mapping.get(raw.lower()) or fallback


def section_identity_key(row: pd.Series) -> str:
    """Возвращает стабильный ключ пользовательского раздела."""
    unit_level = _map_label(row.get("unit_level"), {"article": "article", "imrad_block": "imrad_block", "imrad_subblock": "imrad_subblock"})
    block = "" if is_empty_value(row.get("imrad_block")) else str(row.get("imrad_block")).strip()
    subblock = "" if is_empty_value(row.get("imrad_subblock")) else str(row.get("imrad_subblock")).strip()
    if unit_level == "article":
        return "article"
    if unit_level == "imrad_block" and block:
        return f"block::{block}"
    if unit_level == "imrad_subblock" and block and subblock:
        return f"subblock::{block}::{subblock.lower()}"
    return ""


def section_sort_key(row: pd.Series) -> tuple[int, str, str]:
    """Возвращает ключ сортировки разделов для отображения: блок перед подразделами."""
    unit_level = "" if is_empty_value(row.get("unit_level")) else str(row.get("unit_level")).strip()
    block = "" if is_empty_value(row.get("imrad_block")) else str(row.get("imrad_block")).strip()
    block_order = {
        "INTRODUCTION": 10,
        "METHOD_OR_APPROACH": 20,
        "RESULTS_OR_DEMONSTRATION": 30,
        "DISCUSSION_OR_CONCLUSION": 40,
        "SUPPLEMENTARY_OR_TEXTUAL": 50,
    }
    if unit_level == "article":
        order = 0
    elif unit_level == "imrad_block":
        order = block_order.get(block, 90)
    elif unit_level == "imrad_subblock":
        order = block_order.get(block, 90) + 1
    else:
        order = 999
    return (order, str(row.get("section_label", "")), str(row.get("unit_id", "")))


def section_label_ru(row: pd.Series) -> str:
    """Возвращает русский заголовок раздела/подраздела."""
    unit_level = "" if is_empty_value(row.get("unit_level")) else str(row.get("unit_level")).strip()
    if unit_level == "article":
        return "Статья в целом"
    block = _map_label(row.get("imrad_block"), IMRAD_BLOCK_LABELS_RU)
    if unit_level == "imrad_block":
        return f"Раздел: {block}" if block else ""
    if unit_level == "imrad_subblock":
        subblock = _map_label(row.get("imrad_subblock"), IMRAD_SUBBLOCK_LABELS_RU)
        if block and subblock:
            return f"Раздел: {block} / подраздел: {subblock}"
        return ""
    return ""


def section_filter_key(row: pd.Series) -> str:
    """Формирует ключ фильтра раздела для внутренних сопоставлений."""
    return section_identity_key(row)
