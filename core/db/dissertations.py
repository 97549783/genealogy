"""Загрузка диссертационных метаданных и профилей из SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from .connection import get_db_signature, get_sqlite_connection
from .scores import load_dissertation_scores

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS: List[str] = ["supervisors_1.name", "supervisors_2.name"]
FEEDBACK_FILE = Path("/app/data-nonsynchronized/feedback.csv")

SINGLE_COLUMN_CRITERIA = {
    "title": "title",
    "candidate_name": "candidate_name",
    "institution_prepared": "institution_prepared",
    "leading_organization": "leading_organization",
    "defense_location": "defense_location",
    "city": "city",
    "year": "year",
}
MULTI_COLUMN_CRITERIA = {
    "supervisors": ["supervisors_1.name", "supervisors_2.name"],
    "opponents": ["opponents_1.name", "opponents_2.name", "opponents_3.name"],
    "specialties": ["specialties_1.code", "specialties_1.name", "specialties_2.code", "specialties_2.name"],
}


def _quote_identifier(identifier: str) -> str:
    """Экранирует имя столбца SQLite."""
    return '"' + identifier.replace('"', '""') + '"'


def _existing_columns() -> set[str]:
    with get_sqlite_connection() as conn:
        rows = conn.execute("PRAGMA table_info(diss_metadata)").fetchall()
    return {row[1] for row in rows}


def _like_expr(column: str) -> str:
    return f"CASEFOLD(COALESCE(CAST({_quote_identifier(column)} AS TEXT), '')) LIKE CASEFOLD(?)"


def load_dissertation_metadata() -> pd.DataFrame:
    """Загружает метаданные диссертаций из таблицы diss_metadata."""
    return _load_dissertation_metadata_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_dissertation_metadata_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает метаданные диссертаций из SQLite с кэшированием."""
    _ = db_signature
    with get_sqlite_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM diss_metadata", conn)

    if df.empty:
        raise ValueError("Таблица diss_metadata пуста")
    if "Code" not in df.columns:
        raise KeyError("В таблице diss_metadata отсутствует столбец 'Code'")
    if AUTHOR_COLUMN not in df.columns:
        raise KeyError(f"В таблице diss_metadata отсутствует столбец '{AUTHOR_COLUMN}'")

    df = df.dropna(subset=["Code"]).copy()
    df["Code"] = df["Code"].astype(str).str.strip()
    df = df[df["Code"] != ""]
    df = df.drop_duplicates(subset=["Code"], keep="first")
    return df


def search_dissertation_metadata(search_params: dict[str, str]) -> pd.DataFrame:
    """Ищет диссертации в таблице diss_metadata по формальным критериям."""
    existing = _existing_columns()
    where_clauses: list[str] = []
    params: list[str] = []

    for criterion, raw_value in search_params.items():
        value = str(raw_value).strip()
        if not value or value == "Все":
            continue
        like_value = f"%{value}%"

        if criterion in SINGLE_COLUMN_CRITERIA:
            column = SINGLE_COLUMN_CRITERIA[criterion]
            if column not in existing:
                raise ValueError(f"В таблице diss_metadata отсутствуют столбцы для критерия: {criterion}")
            where_clauses.append(_like_expr(column))
            params.append(like_value)
            continue

        if criterion in MULTI_COLUMN_CRITERIA:
            cols = [col for col in MULTI_COLUMN_CRITERIA[criterion] if col in existing]
            if not cols:
                raise ValueError(f"В таблице diss_metadata отсутствуют столбцы для критерия: {criterion}")
            where_clauses.append("(" + " OR ".join(_like_expr(col) for col in cols) + ")")
            params.extend([like_value] * len(cols))

    query = "SELECT * FROM diss_metadata"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    if "year" in existing and "candidate_name" in existing:
        query += f" ORDER BY CAST({_quote_identifier('year')} AS INTEGER) DESC, {_quote_identifier('candidate_name')} ASC"
    elif "Code" in existing:
        query += f" ORDER BY {_quote_identifier('Code')}"

    with get_sqlite_connection() as conn:
        conn.create_function("CASEFOLD", 1, lambda value: str(value).casefold())
        return pd.read_sql_query(query, conn, params=params)


def load_dissertation_filter_options() -> dict[str, list[str]]:
    """Загружает значения для выпадающих фильтров поиска диссертаций."""
    return _load_dissertation_filter_options_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_dissertation_filter_options_cached(db_signature: tuple[str, float, int]) -> dict[str, list[str]]:
    """Загружает значения фильтров диссертаций из SQLite с кэшированием."""
    _ = db_signature
    existing = _existing_columns()
    with get_sqlite_connection() as conn:
        years = []
        if "year" in existing:
            years = [str(r[0]).strip() for r in conn.execute('SELECT DISTINCT "year" FROM diss_metadata WHERE "year" IS NOT NULL AND TRIM(CAST("year" AS TEXT)) != "" ORDER BY CAST("year" AS INTEGER) DESC').fetchall()]

        cities = []
        if "city" in existing:
            cities = [str(r[0]).strip() for r in conn.execute('SELECT DISTINCT "city" FROM diss_metadata WHERE "city" IS NOT NULL AND TRIM(CAST("city" AS TEXT)) != "" ORDER BY "city" COLLATE NOCASE').fetchall()]

        specialty_cols = [c for c in ["specialties_1.code", "specialties_1.name", "specialties_2.code", "specialties_2.name"] if c in existing]
        specialties: list[str] = []
        if specialty_cols:
            union_query = " UNION ".join([f"SELECT {_quote_identifier(col)} AS value FROM diss_metadata" for col in specialty_cols])
            spec_query = f"SELECT DISTINCT value FROM ({union_query}) WHERE value IS NOT NULL AND TRIM(CAST(value AS TEXT)) != '' ORDER BY value COLLATE NOCASE"
            specialties = [str(r[0]).strip() for r in conn.execute(spec_query).fetchall()]

    return {"year": years, "city": cities, "specialties": specialties}


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    """Совместимая обёртка для существующего кода."""
    return load_dissertation_metadata()


@st.cache_data(show_spinner=False)
def load_basic_scores() -> pd.DataFrame:
    """Совместимая обёртка для загрузки профилей диссертаций из SQLite."""
    return load_dissertation_scores()
