"""Контекст инициализации приложения."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

import pandas as pd


@dataclass(frozen=True)
class AppContext:
    """Контейнер общих данных для всех вкладок приложения."""

    df: pd.DataFrame
    idx: Dict[str, Set[int]]
    all_supervisor_names: Set[str]
    valid_shared_roots: List[str]
    classifier_labels: Dict[str, str]
