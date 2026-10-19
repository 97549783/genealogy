"""Подготовка нумерованного списка источников школ по источникам."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

def _sources(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_sources = document.get("источники", []) if isinstance(document, Mapping) else []
    sources = [source for source in raw_sources if isinstance(source, Mapping)]
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
    if doi and not _contains(description, doi):
        parts.append(f"DOI: {doi}")
    for access in source.get("доступы", []):
        url = access["url"]
        access_date = _format_access_date(access.get("дата_обращения"))
        text = f"URL ({access['назначение'].replace('_', ' ')}): {url}"
        if access_date:
            text += f" (дата обращения: {access_date})"
        if not _contains(description, url):
            parts.append(text)
    return ". ".join(parts).strip()


def build_numbered_bibliography(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Формирует нумерованный список источников для UI и экспорта."""
    rows: list[dict[str, Any]] = []
    for number, source in enumerate(_sources(document), start=1):
        accesses = source.get("доступы", [])
        rows.append({"№": number, "id": source.get("id"), "описание": format_bibliographic_reference(source),
                     "url": accesses[0]["url"] if accesses else "", "доступы": list(accesses)})
    return rows


def build_bibliography_text(document: Mapping[str, Any]) -> str:
    """Формирует текстовый нумерованный список источников."""
    return "\n".join(f"{row['№']}. {row['описание']}" for row in build_numbered_bibliography(document))
