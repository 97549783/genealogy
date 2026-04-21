"""Общие функции работы с научными руководителями."""

from __future__ import annotations

from typing import Optional

import pandas as pd

DEFAULT_SUPERVISOR_COLUMNS = ["supervisors_1.name", "supervisors_2.name"]


def get_unique_supervisors(
    df: pd.DataFrame,
    supervisor_columns: Optional[list[str]] = None,
) -> list[str]:
    """Возвращает отсортированный список уникальных руководителей."""
    columns = supervisor_columns or DEFAULT_SUPERVISOR_COLUMNS
    unique_supervisors: set[str] = set()

    for column in columns:
        if column not in df.columns:
            continue

        for value in df[column].dropna().tolist():
            clean_value = str(value).strip()
            if not clean_value:
                continue
            if clean_value.lower() in {"nan", "none"}:
                continue
            unique_supervisors.add(clean_value)

    return sorted(unique_supervisors)
