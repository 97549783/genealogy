"""Загрузка диссертационных метаданных и профилей из SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from .connection import DB_PATH, get_sqlite_connection
from .scores import load_dissertation_scores

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS: List[str] = ["supervisors_1.name", "supervisors_2.name"]
FEEDBACK_FILE = Path("/app/data-nonsynchronized/feedback.csv")


@st.cache_data(show_spinner=False)
def load_dissertation_metadata() -> pd.DataFrame:
    """Загружает метаданные диссертаций из таблицы diss_metadata."""
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


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    """Совместимая обёртка для существующего кода."""
    return load_dissertation_metadata()


@st.cache_data(show_spinner=False)
def load_basic_scores() -> pd.DataFrame:
    """Совместимая обёртка для загрузки профилей диссертаций из SQLite."""
    return load_dissertation_scores()
