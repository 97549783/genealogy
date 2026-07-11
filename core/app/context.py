"""Контекст инициализации приложения.

DataFrame и индексы в BaseAppData являются общими ресурсами процесса
Streamlit. Их нельзя изменять на месте: вкладки должны рассматривать эти
объекты как доступные только для чтения.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

import pandas as pd

DbSignature = tuple[str, float, int]
LineageContextKey = tuple[DbSignature, tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class BaseAppData:
    db_signature: DbSignature
    df: pd.DataFrame
    idx: Dict[str, Set[int]]
    all_supervisor_names: frozenset[str]


@dataclass(frozen=True)
class AppContext:
    """Контейнер общих данных для всех вкладок приложения."""

    db_signature: DbSignature
    df: pd.DataFrame
    idx: Dict[str, Set[int]]
    all_supervisor_names: frozenset[str]
    valid_shared_roots: List[str]
    classifier_labels: Dict[str, str]
