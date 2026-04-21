"""
utils/db.py — загрузка данных из БД.

Изолирует весь ввод-вывод данных в одном месте.
При переходе с CSV на SQLite достаточно изменить только этот файл —
все вкладки и алгоритмы останутся нетронутыми.

Публичный API:
    load_data()          -> pd.DataFrame   — диссертации из db_lineages/
    load_basic_scores()  -> pd.DataFrame   — тематические профили из basic_scores/

Константы:
    DATA_DIR, CSV_GLOB
    AUTHOR_COLUMN, SUPERVISOR_COLUMNS
    BASIC_SCORES_DIR
    FEEDBACK_FILE
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st
from core.db import load_scores_from_folder

# ---------------------------------------------------------------------------
# Константы путей и колонок
# ---------------------------------------------------------------------------

DATA_DIR = "db_lineages"       # папка с CSV внутри репозитория
CSV_GLOB = "*.csv"             # маска файлов

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS: List[str] = ["supervisors_1.name", "supervisors_2.name"]

BASIC_SCORES_DIR = "basic_scores"   # тематические профили диссертаций

FEEDBACK_FILE = Path("/app/data-nonsynchronized/feedback.csv")

# ---------------------------------------------------------------------------
# Внутренние загрузчики (CSV-реализация)
# ---------------------------------------------------------------------------

def _load_from_csv() -> pd.DataFrame:
    """Читает все CSV из DATA_DIR и объединяет в один DataFrame."""
    base = Path(DATA_DIR).expanduser().resolve()
    files = sorted(base.glob(CSV_GLOB))
    if not files:
        raise FileNotFoundError(
            f"В {base} не найдено CSV по маске '{CSV_GLOB}'"
        )
    # Авто-детекция разделителя по первому файлу
    try:
        sample = pd.read_csv(files[0], nrows=5, dtype=str)
        sep = ";" if sample.shape[1] == 1 else ","
    except Exception:
        sep = ","
    frames = [
        pd.read_csv(f, dtype=str, keep_default_na=False, sep=sep)
        for f in files
    ]
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# SQLite-загрузчики (будут активированы при переходе на SQLite)
# ---------------------------------------------------------------------------
# Раскомментировать и доработать при миграции БД.
#
# DB_PATH = os.environ.get("SQLITE_DB_PATH", "genealogy.db")
#
# def _load_from_sqlite() -> pd.DataFrame:
#     import sqlite3
#     conn = sqlite3.connect(DB_PATH)
#     df = pd.read_sql("SELECT * FROM dissertations", conn)
#     conn.close()
#     return df
#
# def _load_basic_scores_from_sqlite() -> pd.DataFrame:
#     import sqlite3
#     conn = sqlite3.connect(DB_PATH)
#     df = pd.read_sql("SELECT * FROM basic_scores", conn)
#     conn.close()
#     # ... нормализация аналогично CSV-версии ...
#     return df


# ---------------------------------------------------------------------------
# Переключатель CSV ↔ SQLite
# ---------------------------------------------------------------------------

# Чтобы включить SQLite, установить переменную окружения USE_SQLITE=true
_USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    """
    Возвращает DataFrame со всеми диссертациями.
    Источник определяется переменной окружения USE_SQLITE.
    """
    if _USE_SQLITE:
        # return _load_from_sqlite()  # раскомментировать после миграции
        raise NotImplementedError("SQLite-загрузчик ещё не реализован")
    return _load_from_csv()


@st.cache_data(show_spinner=False)
def load_basic_scores() -> pd.DataFrame:
    """
    Возвращает DataFrame с тематическими профилями диссертаций.
    Источник определяется переменной окружения USE_SQLITE.
    """
    if _USE_SQLITE:
        # return _load_basic_scores_from_sqlite()  # раскомментировать после миграции
        raise NotImplementedError("SQLite-загрузчик ещё не реализован")
    return load_scores_from_folder(BASIC_SCORES_DIR)
