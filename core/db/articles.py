"""Загрузка метаданных и тематических профилей статей из SQLite."""

from __future__ import annotations

import pandas as pd

from .connection import get_sqlite_connection
from .scores import load_article_scores

REQUIRED_ARTICLE_METADATA_COLUMNS = {
    "Article_id",
    "Authors",
    "Title",
    "Journal",
    "Volume",
    "Issue",
    "Year",
}


def load_articles_metadata() -> pd.DataFrame:
    """Загружает метаданные статей и проверяет обязательные поля."""
    with get_sqlite_connection() as conn:
        metadata = pd.read_sql_query("SELECT * FROM articles_metadata", conn)

    if "Article_id" not in metadata.columns:
        raise KeyError("В таблице articles_metadata отсутствует столбец 'Article_id'")

    missing = sorted(REQUIRED_ARTICLE_METADATA_COLUMNS - set(metadata.columns))
    if missing:
        raise KeyError(f"В таблице articles_metadata отсутствуют обязательные поля: {', '.join(missing)}")

    metadata = metadata.dropna(subset=["Article_id"]).copy()
    metadata["Article_id"] = metadata["Article_id"].astype(str).str.strip()
    metadata = metadata[metadata["Article_id"].str.len() > 0]
    return metadata


def load_articles_scores() -> pd.DataFrame:
    """Загружает тематические профили статей из SQLite."""
    scores = load_article_scores()
    if "Article_id" not in scores.columns:
        raise KeyError("В таблице articles_scores_inf_edu отсутствует столбец 'Article_id'")

    scores = scores.dropna(subset=["Article_id"]).copy()
    scores["Article_id"] = scores["Article_id"].astype(str).str.strip()
    scores = scores[scores["Article_id"].str.len() > 0]

    feature_columns = [col for col in scores.columns if col != "Article_id"]
    if not feature_columns:
        raise ValueError("Не найдены столбцы с тематическими компонентами статей")

    scores[feature_columns] = scores[feature_columns].apply(pd.to_numeric, errors="coerce")
    return scores


def load_articles_data() -> pd.DataFrame:
    """Возвращает объединённый датафрейм статей для аналитики вкладки."""
    metadata = load_articles_metadata()
    scores = load_articles_scores()

    merged = metadata.merge(scores, on="Article_id", how="inner", validate="one_to_one")
    return merged
