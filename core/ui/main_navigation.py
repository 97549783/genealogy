"""Навигация между основными разделами приложения."""

from __future__ import annotations

from html import escape
from typing import Mapping
from urllib.parse import urlencode

import streamlit as st

from tabs.registry import DEFAULT_TAB_ID, TAB_ID_TO_LABEL, TAB_SPECS


def resolve_main_section_id(raw_value: object) -> str:
    """Возвращает допустимый идентификатор раздела или раздел по умолчанию."""
    value = str(raw_value).strip() if raw_value is not None else ""
    return value if value in TAB_ID_TO_LABEL else DEFAULT_TAB_ID


def build_main_navigation_html(
    active_section_id: str,
    query_params: Mapping[str, object] | None = None,
) -> str:
    """Формирует безопасную HTML-разметку основной навигации."""
    active_section_id = resolve_main_section_id(active_section_id)
    # Ссылки намеренно очищают параметры раздела, чтобы данные одного раздела не попадали в другой.
    links = []
    for section_id, label in TAB_SPECS:
        href = "?" + urlencode({"tab": section_id})
        active = section_id == active_section_id
        attributes = [
            'class="main-navigation__link' + (" main-navigation__link--active" if active else "") + '"',
            f'href="{escape(href, quote=True)}"',
            'target="_self"',
        ]
        if active:
            attributes.append('aria-current="page"')
        links.append(f"<a {' '.join(attributes)}>{escape(label)}</a>")

    return (
        '<nav class="main-navigation" aria-label="Основные разделы">'
        + "".join(links)
        + "</nav>"
    )


def render_main_navigation(
    active_section_id: str,
    query_params: Mapping[str, object] | None = None,
) -> None:
    """Отображает основную навигацию с доступными состояниями ссылок."""
    markup = build_main_navigation_html(active_section_id, query_params)
    st.markdown(
        f"""
<style>
.main-navigation {{
  display: flex;
  gap: 0.25rem;
  overflow-x: auto;
  max-width: 100%;
  margin: 0 0 1rem;
  padding: 0.25rem 0 0;
  border-bottom: 1px solid color-mix(in srgb, currentColor 25%, transparent);
  scrollbar-width: thin;
}}
.main-navigation__link {{
  flex: 0 0 auto;
  padding: 0.55rem 0.75rem;
  color: inherit !important;
  text-decoration: none !important;
  white-space: nowrap;
  border: 2px solid transparent;
  border-radius: 0.4rem 0.4rem 0 0;
}}
.main-navigation__link:hover {{
  background: color-mix(in srgb, currentColor 9%, transparent);
  text-decoration: underline !important;
}}
.main-navigation__link:focus-visible {{
  outline: 3px solid currentColor;
  outline-offset: -3px;
}}
.main-navigation__link--active {{
  font-weight: 700;
  border-bottom-color: currentColor;
  background: color-mix(in srgb, currentColor 13%, transparent);
}}
</style>
{markup}
""",
        unsafe_allow_html=True,
    )
