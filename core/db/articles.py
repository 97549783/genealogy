"""Загрузка метаданных и тематических профилей статей из SQLite."""

from __future__ import annotations

import sqlite3

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


def load_available_article_journals() -> pd.DataFrame:
    """Загружает список журналов, доступных в таблице статей."""
    return _load_available_article_journals_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_available_article_journals_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает агрегированный список журналов с кэшированием."""
    _ = db_signature
    with get_sqlite_connection() as conn:
        metadata = pd.read_sql_query("SELECT * FROM articles_metadata", conn)

    columns = ["ISSN", "Journal", "article_count", "first_year", "last_year"]
    if metadata.empty:
        return pd.DataFrame(columns=columns)
    for column in ["ISSN", "Journal", "Year", "Article_id"]:
        if column not in metadata.columns:
            metadata[column] = ""

    work = metadata.copy()
    work["ISSN"] = work["ISSN"].fillna("").astype(str).str.strip()
    work["Journal"] = work["Journal"].fillna("").astype(str).str.strip()
    work = work[(work["ISSN"] != "") | (work["Journal"] != "")]
    if work.empty:
        return pd.DataFrame(columns=columns)

    work["_group_key"] = work["ISSN"].where(work["ISSN"] != "", "journal:" + work["Journal"].str.lower())
    work["_year"] = pd.to_numeric(work["Year"], errors="coerce")
    rows = []
    for _, group in work.groupby("_group_key", sort=True):
        issn_values = [value for value in group["ISSN"].astype(str) if value.strip()]
        journal_values = [value for value in group["Journal"].astype(str) if value.strip()]
        years = group["_year"].dropna()
        rows.append({
            "ISSN": issn_values[0] if issn_values else "",
            "Journal": journal_values[0] if journal_values else (issn_values[0] if issn_values else ""),
            "article_count": int(group["Article_id"].nunique()) if "Article_id" in group.columns else int(len(group)),
            "first_year": int(years.min()) if not years.empty else pd.NA,
            "last_year": int(years.max()) if not years.empty else pd.NA,
        })
    return pd.DataFrame(rows, columns=columns).sort_values(["Journal", "ISSN"], kind="stable").reset_index(drop=True)


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
    """Загружает нормализованные тематические профили статей с кэшированием."""
    _ = db_signature
    scores = load_article_scores()
    return _prepare_articles_scores(scores)


def load_articles_scores_raw() -> pd.DataFrame:
    """Загружает тематические профили статей без замены пропусков нулями."""
    return _load_articles_scores_raw_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_articles_scores_raw_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает сырые тематические профили статей с кэшированием."""
    _ = db_signature
    with get_sqlite_connection() as conn:
        scores = pd.read_sql_query('SELECT * FROM "articles_scores_inf_edu"', conn)
    return _prepare_articles_scores(scores)


def _prepare_articles_scores(scores: pd.DataFrame) -> pd.DataFrame:
    """Проверяет и приводит таблицу тематических профилей статей."""
    if "Article_id" not in scores.columns:
        raise KeyError("В таблице articles_scores_inf_edu отсутствует столбец 'Article_id'")

    scores = scores.dropna(subset=["Article_id"]).copy()
    scores["Article_id"] = scores["Article_id"].astype(str).str.strip().astype(object)
    scores = scores[scores["Article_id"].str.len() > 0]
    scores = scores.drop_duplicates(subset=["Article_id"], keep="first")

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
    """Возвращает статьи с метаданными и, при наличии, тематическими профилями."""
    _ = db_signature
    metadata = load_articles_metadata()
    scores = load_articles_scores_raw()

    score_columns = [col for col in scores.columns if col != "Article_id"]
    scores = scores.copy()
    scores["_score_row_exists"] = True
    if score_columns:
        scores["_score_value_count"] = scores[score_columns].notna().sum(axis=1)
    else:
        scores["_score_value_count"] = 0

    data = metadata.merge(scores, on="Article_id", how="left", validate="one_to_one")
    data["Has_thematic_scores"] = (
        data["_score_row_exists"].fillna(False).astype(bool)
        & pd.to_numeric(data["_score_value_count"], errors="coerce").fillna(0).gt(0)
    )
    return data.drop(columns=["_score_row_exists", "_score_value_count"], errors="ignore")


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
    except (sqlite3.OperationalError, pd.errors.DatabaseError) as exc:
        if "no such table" in str(exc).lower():
            return _empty_article_authors()
        raise


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
    except (sqlite3.OperationalError, pd.errors.DatabaseError) as exc:
        if "no such table" in str(exc).lower():
            return _empty_article_keywords()
        raise
