"""Временная совместимая обёртка поверх модуля core.db."""

from __future__ import annotations

from core.db import AUTHOR_COLUMN, FEEDBACK_FILE, SUPERVISOR_COLUMNS, load_data, load_scores_from_folder


def load_basic_scores():
    """Совместимая функция загрузки тематических профилей."""
    return load_scores_from_folder("basic_scores")
