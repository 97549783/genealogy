"""Общие функции работы со списками научных руководителей."""

from __future__ import annotations

from typing import Optional

import pandas as pd

DEFAULT_SUPERVISOR_COLUMNS = ["supervisors_1.name", "supervisors_2.name"]


def get_unique_supervisors(
    df: pd.DataFrame,
    supervisor_columns: Optional[list[str]] = None,
) -> list[str]:
    """Извлекает отсортированный список уникальных научных руководителей."""
    columns = supervisor_columns or DEFAULT_SUPERVISOR_COLUMNS
    supervisors: set[str] = set()

    for column in columns:
        if column not in df.columns:
            continue
        for value in df[column].dropna().tolist():
            clean = str(value).strip()
            if not clean:
                continue
            if clean.lower() in {"nan", "none"}:
                continue
            supervisors.add(clean)

    return sorted(supervisors)
