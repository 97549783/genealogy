"""Общие функции загрузки и нормализации тематических профилей."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

DEFAULT_SCORES_FOLDER = "basic_scores"


def _resolve_scores_base(folder_path: str) -> Path:
    """Возвращает путь к папке с профилями с резервным разрешением."""
    base = Path(folder_path).expanduser()
    if base.is_absolute():
        return base.resolve()

    resolved_cwd = base.resolve()
    if resolved_cwd.exists():
        return resolved_cwd

    repo_root = Path(__file__).resolve().parents[2]
    resolved_repo = (repo_root / base).resolve()
    if resolved_repo.exists():
        return resolved_repo

    return resolved_cwd


def load_scores_from_folder(
    folder_path: str = DEFAULT_SCORES_FOLDER,
    specific_files: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Загружает CSV профилей и приводит их к единому формату."""
    base = _resolve_scores_base(folder_path)

    if specific_files:
        files = [base / name for name in specific_files if (base / name).exists()]
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
    """Возвращает все тематические признаки (кроме кода работы)."""
    return [column for column in scores_df.columns if column != "Code"]


def get_numeric_code_feature_columns(scores_df: pd.DataFrame) -> list[str]:
    """Возвращает признаки-коды классификатора, начинающиеся с цифры."""
    return [
        column
        for column in scores_df.columns
        if column != "Code" and len(column) > 0 and column[0].isdigit()
    ]
