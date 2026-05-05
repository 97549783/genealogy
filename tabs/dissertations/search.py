from __future__ import annotations

from typing import Dict, List

import pandas as pd

from core.db import load_dissertation_filter_options, search_dissertation_metadata


def get_available_criteria() -> Dict[str, str]:
    return {
        "title": "Название диссертации",
        "candidate_name": "ФИО автора",
        "supervisors": "ФИО научного руководителя",
        "opponents": "ФИО оппонента",
        "institution_prepared": "Организация выполнения",
        "leading_organization": "Ведущая организация",
        "defense_location": "Место защиты",
        "city": "Город защиты",
        "year": "Год защиты",
        "specialties": "Специальность",
    }


def build_filter_options(df: pd.DataFrame | None = None) -> Dict[str, List[str]]:
    """Возвращает значения выпадающих фильтров из SQLite."""
    _ = df
    return load_dissertation_filter_options()


def filter_dissertations(
    df: pd.DataFrame | None,
    search_params: Dict[str, str],
    *,
    use_fuzzy: bool = False,
) -> pd.DataFrame:
    """Ищет диссертации через SQLite."""
    _ = df
    return search_dissertation_metadata(search_params, use_fuzzy=use_fuzzy)
