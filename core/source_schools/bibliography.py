"""Подготовка нумерованного списка источников школ по источникам."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

from .presentation import get_first_field


def _sources(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    school = document.get("школа", {}) if isinstance(document, Mapping) else {}
    raw_sources = school.get("источники", []) if isinstance(school, Mapping) else []
    sources = [source for source in raw_sources if isinstance(source, Mapping)]
    if sources and all(isinstance(source.get("порядок"), (int, float)) for source in sources):
        return sorted(sources, key=lambda source: (source.get("порядок"), str(source.get("id", ""))))
    return sources


def _normalise_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).rstrip(" .;,")


def _contains(text: str, value: Any) -> bool:
    return bool(value) and str(value).strip().lower() in text.lower()


def _format_access_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).strftime("%d.%m.%Y")
    except ValueError:
        return text


def build_source_number_index(document: Mapping[str, Any]) -> dict[str, int]:
    """Возвращает стабильную нумерацию источников по порядку JSON."""
    return {str(source.get("id")): index for index, source in enumerate(_sources(document), start=1)}


def format_bibliographic_reference(source: Mapping[str, Any]) -> str:
    """Формирует описание источника в формате, близком к ГОСТ."""
    description = _normalise_sentence(str(source.get("библиографическое_описание", "")))
    parts = [description] if description else []
    doi = str(source.get("doi") or "").strip()
    url = str(source.get("url") or "").strip()
    access_date = _format_access_date(source.get("дата_обращения"))
    if doi and not _contains(description, doi):
        parts.append(f"DOI: {doi}")
    if url and not _contains(description, url):
        parts.append(f"URL: {url}")
    result = ". ".join(parts).strip()
    if access_date:
        result = f"{result} (дата обращения: {access_date})" if result else f"(дата обращения: {access_date})"
    return result


def build_numbered_bibliography(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Формирует нумерованный список источников для UI и экспорта."""
    rows: list[dict[str, Any]] = []
    for number, source in enumerate(_sources(document), start=1):
        rows.append({"№": number, "id": source.get("id"), "описание": format_bibliographic_reference(source), "url": source.get("url", "")})
    return rows


def build_bibliography_text(document: Mapping[str, Any]) -> str:
    """Формирует текстовый нумерованный список источников."""
    return "\n".join(f"{row['№']}. {row['описание']}" for row in build_numbered_bibliography(document))
