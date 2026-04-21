"""Компоненты верхнего уровня для композиции Streamlit-приложения."""

from .admin import maybe_render_admin_page_and_stop
from .bootstrap import build_app_context
from .context import AppContext
from .header import render_app_header
