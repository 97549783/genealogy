"""Загрузка диссертационных данных и связанных констант."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from .scores import DEFAULT_SCORES_FOLDER, load_scores_from_folder

DATA_DIR = "db_lineages"
CSV_GLOB = "*.csv"

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS: List[str] = ["supervisors_1.name", "supervisors_2.name"]

BASIC_SCORES_DIR = DEFAULT_SCORES_FOLDER

FEEDBACK_FILE = Path("/app/data-nonsynchronized/feedback.csv")


def _load_from_csv() -> pd.DataFrame:
    """Читает все CSV из папки с диссертациями и объединяет их."""
    base = Path(DATA_DIR).expanduser().resolve()
    files = sorted(base.glob(CSV_GLOB))
    if not files:
        raise FileNotFoundError(f"В {base} не найдено CSV по маске '{CSV_GLOB}'")

    try:
        sample = pd.read_csv(files[0], nrows=5, dtype=str)
        sep = ";" if sample.shape[1] == 1 else ","
    except Exception:
        sep = ","

    frames = [
        pd.read_csv(file_path, dtype=str, keep_default_na=False, sep=sep)
        for file_path in files
    ]
    return pd.concat(frames, ignore_index=True)


# Чтобы включить SQLite, установите переменную окружения USE_SQLITE=true.
_USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() == "true"


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    """Возвращает таблицу диссертаций из выбранного источника данных."""
    if _USE_SQLITE:
        raise NotImplementedError("SQLite-загрузчик ещё не реализован")
    return _load_from_csv()


@st.cache_data(show_spinner=False)
def load_basic_scores() -> pd.DataFrame:
    """Совместимая обёртка для загрузки тематических профилей."""
    if _USE_SQLITE:
        raise NotImplementedError("SQLite-загрузчик ещё не реализован")
    return load_scores_from_folder(BASIC_SCORES_DIR)
