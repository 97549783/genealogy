"""Пакетный семантический поиск по разделам характеристик диссертаций."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import streamlit as st

from core.db.dissertation_sections import get_dissertation_matrix_signature


def get_search_batch_size() -> int:
    """Возвращает размер пакета поиска из окружения."""
    try:
        return max(1, int(os.getenv("DISS_SECTION_SEARCH_BATCH_SIZE", "20000")))
    except ValueError:
        return 20000


@st.cache_resource(show_spinner=False)
def load_dissertation_embedding_matrix(matrix_signature: tuple[str, float, int]) -> np.ndarray:
    """Открывает матрицу векторов через отображение файла в память."""
    _ = matrix_signature[1:]
    return np.load(matrix_signature[0], mmap_mode="r")


def load_current_dissertation_matrix() -> np.ndarray | None:
    """Открывает текущую матрицу, если файл доступен."""
    signature = get_dissertation_matrix_signature()
    if signature is None:
        return None
    return load_dissertation_embedding_matrix(signature)


def _normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=-1, keepdims=True)
    return vecs / np.where(norms == 0, 1.0, norms)


def _valid_targets(target_df: pd.DataFrame, matrix: np.ndarray) -> pd.DataFrame:
    df = target_df.copy()
    df["matrix_row"] = pd.to_numeric(df["matrix_row"], errors="coerce")
    df = df.dropna(subset=["matrix_row"])
    df["matrix_row"] = df["matrix_row"].astype(int)
    return df[(df["matrix_row"] >= 0) & (df["matrix_row"] < int(matrix.shape[0]))].reset_index(drop=True)


def search_similar_dissertation_sections(source_matrix_row: int, matrix: np.ndarray, target_df: pd.DataFrame, top_n: int, batch_size: int = 20000, normalized: bool = True) -> pd.DataFrame:
    """Ищет ближайшие разделы без загрузки всей матрицы в оперативную память."""
    if matrix is None or len(matrix.shape) != 2 or target_df.empty or top_n <= 0:
        return target_df.iloc[0:0].copy()
    source_matrix_row = int(source_matrix_row)
    if source_matrix_row < 0 or source_matrix_row >= int(matrix.shape[0]):
        return target_df.iloc[0:0].copy()
    targets = _valid_targets(target_df, matrix)
    if targets.empty:
        return targets
    source_vec = np.array(matrix[source_matrix_row], dtype=np.float32, copy=True)
    if not normalized:
        source_vec = _normalize(source_vec.reshape(1, -1))[0]
    candidates: list[tuple[float, int]] = []
    keep = min(int(top_n), len(targets))
    for start in range(0, len(targets), int(batch_size)):
        part = targets.iloc[start : start + int(batch_size)]
        rows = part["matrix_row"].to_numpy(dtype=int)
        vectors = np.array(matrix[rows], dtype=np.float32, copy=True)
        if not normalized:
            vectors = _normalize(vectors)
        sims = vectors @ source_vec
        take = min(keep, len(sims))
        idx = np.argpartition(-sims, take - 1)[:take]
        candidates.extend((float(sims[i]), int(part.index[i])) for i in idx)
        candidates = sorted(candidates, key=lambda x: x[0], reverse=True)[:keep]
    out = targets.loc[[idx for _, idx in candidates]].copy().reset_index(drop=True)
    out["similarity"] = [score for score, _ in candidates]
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def filter_targets_for_similar_search(index_df: pd.DataFrame, source_code: str, section_keys: list[str]) -> pd.DataFrame:
    """Ограничивает цели поиска выбранными типами разделов и исключает исходную диссертацию."""
    result = index_df[index_df["section_key"].isin(section_keys)].copy()
    return result[result["Code"].astype(str) != str(source_code)].reset_index(drop=True)
