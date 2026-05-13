"""Безопасное чтение числовых параметров адресной строки."""

from __future__ import annotations

from typing import Any

import streamlit as st


def parse_float_param(value: Any, default: float) -> float:
    """Возвращает число с плавающей точкой или значение по умолчанию."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int_param(value: Any, default: int) -> int:
    """Возвращает целое число или значение по умолчанию."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_bool_param(value: Any, default: bool = False) -> bool:
    """Возвращает булево значение из query-параметра или значение по умолчанию."""
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "да"}:
        return True
    if normalized in {"false", "0", "no", "n", "нет"}:
        return False
    return default


def query_params_signature(param_names: list[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Строит устойчивую сигнатуру выбранных query-параметров."""
    signature = []
    for name in param_names:
        values = tuple(str(value).strip() for value in st.query_params.get_all(name))
        signature.append((name, values))
    return tuple(signature)


def should_hydrate_query(state_key: str, signature: tuple) -> bool:
    """Проверяет, изменилась ли сигнатура URL, и сохраняет новое значение."""
    if st.session_state.get(state_key) == signature:
        return False
    st.session_state[state_key] = signature
    return True
