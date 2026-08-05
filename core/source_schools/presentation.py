"""Адаптеры отображения документов школ по источникам."""
from __future__ import annotations

from typing import Any, Mapping

_TECHNICAL_PREFIXES = ("ev_", "src_", "p_")
_TECHNICAL_KEYS = {
    "id",
    "подтверждение",
    "подтверждения",
    "идентификатор_источника",
    "источники",
    "source_id",
}


def as_list(value: Any) -> list[Any]:
    """Возвращает значение как список без изменения вложенных объектов."""
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def get_first_field(mapping: Mapping[str, Any], *names: str, default: Any = "") -> Any:
    """Возвращает первое найденное поле из набора русских вариантов схемы."""
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def looks_technical_id(value: Any) -> bool:
    """Определяет технические идентификаторы, которые нельзя показывать как текст раздела."""
    return isinstance(value, str) and value.startswith(_TECHNICAL_PREFIXES)


def as_display_text(value: Any) -> str:
    """Преобразует вложенное значение JSON в пользовательский текст без технических ID."""
    if value is None:
        return ""
    if isinstance(value, str):
        return "" if looks_technical_id(value) else value
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [as_display_text(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, Mapping):
        for preferred_key in (
            "название",
            "название_направления",
            "название_периода",
            "значение",
            "описание",
            "формулировка",
            "позиция",
            "текст",
        ):
            text = value.get(preferred_key)
            if isinstance(text, str) and text and not looks_technical_id(text):
                return text
        parts: list[str] = []
        for key, item in value.items():
            if key in _TECHNICAL_KEYS:
                continue
            text = as_display_text(item)
            if text:
                parts.append(text)
        return "; ".join(parts)
    return str(value)
