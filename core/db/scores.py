"""Общие функции загрузки тематических профилей диссертаций."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .connection import get_sqlite_connection

NON_SCORE_COLUMNS = {
    "Code",
    "Article_id",
    "title",
    "supervisor",
    "institution_prepared",
    "year",
}


def load_scores_from_sqlite(table_name: str, key_column: str = "Code") -> pd.DataFrame:
    """Загружает и нормализует профили из таблицы SQLite."""
    with get_sqlite_connection() as conn:
        scores = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

    if key_column not in scores.columns:
        raise KeyError(f"В таблице профилей отсутствует столбец '{key_column}'")

    scores = scores.dropna(subset=[key_column])
    scores[key_column] = scores[key_column].astype(str).str.strip()
    scores = scores[scores[key_column].str.len() > 0]
    scores = scores.drop_duplicates(subset=[key_column], keep="first")

    feature_columns = get_all_feature_columns(scores, key_column=key_column)
    if not feature_columns:
        raise ValueError("Не найдены столбцы с тематическими компонентами")

    scores[feature_columns] = scores[feature_columns].apply(pd.to_numeric, errors="coerce")
    scores[feature_columns] = scores[feature_columns].fillna(0.0)
    return scores


def load_dissertation_scores() -> pd.DataFrame:
    """Загружает профили диссертаций из SQLite."""
    return load_scores_from_sqlite("diss_scores_5_8", key_column="Code")


def load_article_scores() -> pd.DataFrame:
    """Загружает профили статей из SQLite."""
    return load_scores_from_sqlite("articles_scores_inf_edu", key_column="Article_id")


def get_all_feature_columns(scores_df: pd.DataFrame, key_column: str = "Code") -> list[str]:
    """Возвращает все столбцы признаков, кроме служебного Code."""
    excluded = set(NON_SCORE_COLUMNS)
    excluded.add(key_column)
    return [column for column in scores_df.columns if column not in excluded]


def get_numeric_code_feature_columns(scores_df: pd.DataFrame) -> list[str]:
    """Возвращает признаки-коды классификатора, начинающиеся с цифры."""
    return [
        column
        for column in scores_df.columns
        if column != "Code" and len(column) > 0 and column[0].isdigit()
    ]
