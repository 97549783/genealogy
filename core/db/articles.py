"""Загрузка метаданных и тематических профилей статей из SQLite."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .connection import get_db_signature, get_sqlite_connection
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

ARTICLE_AUTHORS_COLUMNS = ["id", "Article_id", "ISSN", "Author_order", "Name", "Affiliation", "Country", "City", "Details"]
ARTICLE_KEYWORDS_COLUMNS = ["id", "Article_id", "ISSN", "Keyword_order", "Keyword"]


def _empty_article_authors() -> pd.DataFrame:
    """Возвращает пустую таблицу авторов статей с ожидаемыми столбцами."""
    return pd.DataFrame(columns=ARTICLE_AUTHORS_COLUMNS)


def _empty_article_keywords() -> pd.DataFrame:
    """Возвращает пустую таблицу ключевых слов статей с ожидаемыми столбцами."""
    return pd.DataFrame(columns=ARTICLE_KEYWORDS_COLUMNS)


def load_articles_metadata() -> pd.DataFrame:
    """Загружает метаданные статей и проверяет обязательные поля."""
    return _load_articles_metadata_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_articles_metadata_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает метаданные статей из SQLite с кэшированием."""
    _ = db_signature
    with get_sqlite_connection() as conn:
        metadata = pd.read_sql_query("SELECT * FROM articles_metadata", conn)

    if "Article_id" not in metadata.columns:
        raise KeyError("В таблице articles_metadata отсутствует столбец 'Article_id'")

    missing = sorted(REQUIRED_ARTICLE_METADATA_COLUMNS - set(metadata.columns))
    if missing:
        raise KeyError(f"В таблице articles_metadata отсутствуют обязательные поля: {', '.join(missing)}")

    metadata = metadata.dropna(subset=["Article_id"]).copy()
    metadata["Article_id"] = metadata["Article_id"].astype(str).str.strip().astype(object)
    metadata = metadata[metadata["Article_id"].str.len() > 0]
    return metadata


def load_articles_scores() -> pd.DataFrame:
    """Загружает тематические профили статей из SQLite."""
    return _load_articles_scores_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_articles_scores_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает тематические профили статей с кэшированием."""
    _ = db_signature
    scores = load_article_scores()
    if "Article_id" not in scores.columns:
        raise KeyError("В таблице articles_scores_inf_edu отсутствует столбец 'Article_id'")

    scores = scores.dropna(subset=["Article_id"]).copy()
    scores["Article_id"] = scores["Article_id"].astype(str).str.strip().astype(object)
    scores = scores[scores["Article_id"].str.len() > 0]

    feature_columns = [col for col in scores.columns if col != "Article_id"]
    if not feature_columns:
        raise ValueError("Не найдены столбцы с тематическими компонентами статей")

    scores[feature_columns] = scores[feature_columns].apply(pd.to_numeric, errors="coerce")
    return scores


def load_articles_data() -> pd.DataFrame:
    """Возвращает объединённый датафрейм статей для аналитики вкладки."""
    return _load_articles_data_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_articles_data_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Возвращает объединённые данные статей с кэшированием."""
    _ = db_signature
    metadata = load_articles_metadata()
    scores = load_articles_scores()
    return metadata.merge(scores, on="Article_id", how="inner", validate="one_to_one")


def load_article_authors() -> pd.DataFrame:
    """Загружает расширенные сведения об авторах статей из SQLite."""
    return _load_article_authors_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_article_authors_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает авторов статей с кэшированием и мягким отсутствием таблицы."""
    _ = db_signature
    try:
        with get_sqlite_connection() as conn:
            return pd.read_sql_query("SELECT * FROM article_authors", conn)
    except Exception:
        return _empty_article_authors()


def load_article_keywords() -> pd.DataFrame:
    """Загружает ключевые слова статей из SQLite."""
    return _load_article_keywords_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_article_keywords_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает ключевые слова статей с кэшированием и мягким отсутствием таблицы."""
    _ = db_signature
    try:
        with get_sqlite_connection() as conn:
            return pd.read_sql_query("SELECT * FROM article_keywords", conn)
    except Exception:
        return _empty_article_keywords()
