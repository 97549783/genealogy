"""Безопасное чтение числовых параметров адресной строки."""

from __future__ import annotations

from typing import Any


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
