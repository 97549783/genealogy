"""Общие функции загрузки тематических профилей диссертаций."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .connection import get_db_signature, get_sqlite_connection

NON_SCORE_COLUMNS = {
    "Code",
    "Article_id",
    "title",
    "supervisor",
    "institution_prepared",
    "year",
}

_ALLOWED_SCORE_TABLES = {
    "diss_scores_5_8",
    "articles_scores_inf_edu",
}


def _validate_table_name(table_name: str) -> str:
    """Проверяет имя таблицы перед подстановкой в SQL-запрос."""
    if table_name not in _ALLOWED_SCORE_TABLES:
        raise ValueError(f"Недопустимое имя таблицы профилей: {table_name}")
    return table_name


def load_scores_from_sqlite(table_name: str, key_column: str = "Code") -> pd.DataFrame:
    """Загружает и нормализует профили из таблицы SQLite."""
    return _load_scores_from_sqlite_cached(table_name, key_column, get_db_signature())


@st.cache_data(show_spinner=False)
def _load_scores_from_sqlite_cached(
    table_name: str,
    key_column: str,
    db_signature: tuple[str, float, int],
) -> pd.DataFrame:
    """Загружает и нормализует профили из таблицы SQLite с кэшированием."""
    _ = db_signature
    safe_table = _validate_table_name(table_name)
    with get_sqlite_connection() as conn:
        scores = pd.read_sql_query(f'SELECT * FROM "{safe_table}"', conn)

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
