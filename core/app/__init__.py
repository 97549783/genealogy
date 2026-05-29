"""Компоненты верхнего уровня для композиции Streamlit-приложения."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AppContext",
    "build_app_context",
    "maybe_render_admin_page_and_stop",
    "render_app_header",
]


def __getattr__(name: str) -> Any:
    """Lazily expose app composition helpers without creating import cycles."""
    if name == "AppContext":
        from .context import AppContext

        return AppContext
    if name == "build_app_context":
        from .bootstrap import build_app_context

        return build_app_context
    if name == "maybe_render_admin_page_and_stop":
        from .admin import maybe_render_admin_page_and_stop

        return maybe_render_admin_page_and_stop
    if name == "render_app_header":
        from .header import render_app_header

        return render_app_header
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
