"""Общие функции загрузки тематических профилей диссертаций."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

DEFAULT_SCORES_FOLDER = "basic_scores"
DB_PATH = os.environ.get("SQLITE_DB_PATH", "genealogy.db")


def _connect_sqlite() -> sqlite3.Connection:
    """Создаёт подключение к SQLite базе с профилями."""
    return sqlite3.connect(DB_PATH)


def load_scores_from_sqlite(table_name: str, key_column: str = "Code") -> pd.DataFrame:
    """Загружает и нормализует профили из таблицы SQLite."""
    with _connect_sqlite() as conn:
        scores = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

    if key_column not in scores.columns:
        raise KeyError(f"В таблице профилей отсутствует столбец '{key_column}'")

    scores = scores.dropna(subset=[key_column])
    scores[key_column] = scores[key_column].astype(str).str.strip()
    scores = scores[scores[key_column].str.len() > 0]
    scores = scores.drop_duplicates(subset=[key_column], keep="first")

    feature_columns = get_all_feature_columns(scores)
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


def _resolve_scores_base(folder_path: str) -> Path:
    """Возвращает устойчиво разрешённый путь к папке с CSV-профилями."""
    base = Path(folder_path).expanduser()
    if base.is_absolute():
        return base.resolve()

    cwd_candidate = base.resolve()
    if cwd_candidate.exists():
        return cwd_candidate

    repo_candidate = Path(__file__).resolve().parents[2] / folder_path
    return repo_candidate.resolve()


def load_scores_from_folder(
    folder_path: str = DEFAULT_SCORES_FOLDER,
    specific_files: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Загружает и нормализует тематические профили из CSV-файлов."""
    base = _resolve_scores_base(folder_path)

    if specific_files:
        files = [base / file_name for file_name in specific_files if (base / file_name).exists()]
    else:
        files = sorted(base.glob("*.csv"))

    if not files:
        raise FileNotFoundError(f"CSV файлы не найдены в {base}")

    frames: list[pd.DataFrame] = []
    for file in files:
        frame = pd.read_csv(file)
        if "Code" not in frame.columns:
            raise KeyError(f"Файл {file.name} не содержит колонку 'Code'")
        frames.append(frame)

    scores = pd.concat(frames, ignore_index=True)
    scores = scores.dropna(subset=["Code"])
    scores["Code"] = scores["Code"].astype(str).str.strip()
    scores = scores[scores["Code"].str.len() > 0]
    scores = scores.drop_duplicates(subset=["Code"], keep="first")

    feature_columns = get_all_feature_columns(scores)
    if not feature_columns:
        raise ValueError("Не найдены столбцы с тематическими компонентами")

    scores[feature_columns] = scores[feature_columns].apply(pd.to_numeric, errors="coerce")
    scores[feature_columns] = scores[feature_columns].fillna(0.0)
    return scores


def get_all_feature_columns(scores_df: pd.DataFrame) -> list[str]:
    """Возвращает все столбцы признаков, кроме служебного Code."""
    return [column for column in scores_df.columns if column != "Code"]


def get_numeric_code_feature_columns(scores_df: pd.DataFrame) -> list[str]:
    """Возвращает признаки-коды классификатора, начинающиеся с цифры."""
    return [
        column
        for column in scores_df.columns
        if column != "Code" and len(column) > 0 and column[0].isdigit()
    ]
