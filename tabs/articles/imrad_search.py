"""Вспомогательные функции семантического поиска по IMRAD-зонам."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from core.db.connection import get_db_signature


def resolve_matrix_path(file_path: str) -> Path:
    """Преобразует путь к матрице в абсолютный путь относительно SQLite-файла."""
    path = Path(str(file_path or "")).expanduser()
    if path.is_absolute():
        return path
    db_path = Path(get_db_signature()[0])
    return (db_path.parent / path).resolve()


@st.cache_resource(show_spinner=False)
def load_embedding_matrix(matrix_path: str | Path) -> np.ndarray:
    """Загружает матрицу эмбеддингов из .npy/.npz файла."""
    path = Path(matrix_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл матрицы не найден: {path}")
    if path.suffix.lower() == ".npz":
        data = np.load(path)
        key = list(data.files)[0]
        return np.asarray(data[key])
    return np.asarray(np.load(path))


def filter_imrad_index(df: pd.DataFrame, unit_levels: list[str] | None = None, imrad_blocks: list[str] | None = None, imrad_subblocks: list[str] | None = None, include_weak: bool = True, include_inferred: bool = True, min_confidence: float | None = None, exclude_article_id: str | None = None) -> pd.DataFrame:
    """Фильтрует индекс IMRAD по выбранным ограничениям."""
    result = df.copy()
    if unit_levels:
        result = result[result["unit_level"].isin(unit_levels)]
    if imrad_blocks:
        result = result[result["imrad_block"].isin(imrad_blocks)]
    if imrad_subblocks:
        result = result[result["imrad_subblock"].isin(imrad_subblocks)]
    if not include_weak and "is_weak" in result.columns:
        result = result[~result["is_weak"].fillna(0).astype(bool)]
    if not include_inferred and "is_inferred" in result.columns:
        result = result[~result["is_inferred"].fillna(0).astype(bool)]
    if min_confidence is not None and "confidence" in result.columns:
        result = result[pd.to_numeric(result["confidence"], errors="coerce").fillna(0) >= float(min_confidence)]
    if exclude_article_id is not None:
        result = result[result["article_id"].astype(str) != str(exclude_article_id)]
    return result


def search_similar_units(source_row: int, matrix: np.ndarray, index_df: pd.DataFrame, target_df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Ищет наиболее похожие зоны по скалярному произведению/косинусу."""
    if source_row < 0 or source_row >= len(matrix):
        raise IndexError("Индекс исходной строки матрицы вне диапазона")
    _ = index_df
    source_vec = matrix[source_row]
    rows = target_df["matrix_row"].astype(int).to_numpy()
    if np.any(rows < 0) or np.any(rows >= len(matrix)):
        raise IndexError("Одна или несколько строк матрицы вне диапазона")
    target_vecs = matrix[rows]

    normalized_flag = str(target_df.get("normalized", pd.Series([1])).iloc[0]).lower()
    normalized = normalized_flag in {"1", "true", "yes"}
    if not normalized:
        source_norm = np.linalg.norm(source_vec)
        target_norms = np.linalg.norm(target_vecs, axis=1)
        source_vec = source_vec / (source_norm if source_norm else 1.0)
        target_vecs = target_vecs / np.where(target_norms == 0, 1.0, target_norms)[:, None]

    sims = target_vecs @ source_vec
    out = target_df.copy()
    out["similarity"] = sims
    out = out.sort_values("similarity", ascending=False).head(int(top_n)).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out
