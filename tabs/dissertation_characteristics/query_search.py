"""Нейросетевой поиск по текстовым запросам к разделам диссертаций."""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pandas as pd
import streamlit as st

from tabs.dissertation_characteristics.search import _normalize, _valid_targets

QUERY_CONTRIBUTION_TEMPERATURE = 0.1


def is_query_encoder_available() -> bool:
    """Проверяет наличие библиотеки энкодера запросов."""
    return importlib.util.find_spec("sentence_transformers") is not None


@st.cache_resource(show_spinner=False)
def load_query_encoder(model_name: str, device: str):
    """Лениво загружает модель кодирования пользовательских запросов."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, device=device)


def get_query_encoder_device() -> str:
    """Возвращает устройство энкодера запросов из переменной окружения."""
    return str(os.getenv("DISS_QUERY_ENCODER_DEVICE", "cpu") or "cpu").strip() or "cpu"


def collect_non_empty_queries(values: list[str], max_queries: int = 5) -> list[str]:
    """Собирает непустые запросы пользователя."""
    return [str(v).strip() for v in values[:max_queries] if str(v).strip()]


def encode_user_queries(queries: list[str], model_name: str, normalize_embeddings: bool, device: str = "cpu") -> np.ndarray:
    """Кодирует запросы, добавляя префикс query: для моделей E5."""
    is_e5 = "e5" in str(model_name).casefold()
    prepared = [(f"query: {q}" if is_e5 else q) for q in queries]
    if not prepared:
        return np.zeros((0, 0), dtype=np.float32)
    encoder = load_query_encoder(model_name, device)
    return np.asarray(encoder.encode(prepared, normalize_embeddings=normalize_embeddings), dtype=np.float32)


def average_query_vectors(query_vectors: np.ndarray) -> np.ndarray:
    """Усредняет векторы запросов и нормализует результат."""
    return _normalize(np.asarray(query_vectors, dtype=np.float32).mean(axis=0).reshape(1, -1))[0]


def softmax_percentages(values: np.ndarray, temperature: float = QUERY_CONTRIBUTION_TEMPERATURE) -> np.ndarray:
    """Переводит сходства отдельных запросов в процентные вклады."""
    vals = np.asarray(values, dtype=np.float32)
    z = vals / max(float(temperature), 1e-12)
    z -= np.max(z)
    weights = np.exp(z)
    return weights / max(float(weights.sum()), 1e-12) * 100.0


def search_dissertation_sections_by_query_vector(query_vectors: np.ndarray, matrix: np.ndarray, target_df: pd.DataFrame, top_n: int, batch_size: int = 20000, normalized: bool = True) -> pd.DataFrame:
    """Ищет разделы по среднему вектору запросов пакетами."""
    if matrix is None or target_df.empty or query_vectors.size == 0 or top_n <= 0:
        return target_df.iloc[0:0].copy()
    targets = _valid_targets(target_df, matrix)
    mean_query = average_query_vectors(query_vectors)
    qv = np.asarray(query_vectors, dtype=np.float32)
    if not normalized:
        qv = _normalize(qv)
    keep = min(int(top_n), len(targets))
    candidates: list[tuple[float, int, np.ndarray]] = []
    for start in range(0, len(targets), int(batch_size)):
        part = targets.iloc[start : start + int(batch_size)]
        rows = part["matrix_row"].to_numpy(dtype=int)
        vectors = np.array(matrix[rows], dtype=np.float32, copy=True)
        if not normalized:
            vectors = _normalize(vectors)
        sims = vectors @ mean_query
        query_sims = vectors @ qv.T
        take = min(keep, len(sims))
        idx = np.argpartition(-sims, take - 1)[:take]
        candidates.extend((float(sims[i]), int(part.index[i]), query_sims[i].copy()) for i in idx)
        candidates = sorted(candidates, key=lambda x: x[0], reverse=True)[:keep]
    out = targets.loc[[idx for _, idx, _ in candidates]].copy().reset_index(drop=True)
    out["similarity"] = [score for score, _, _ in candidates]
    if qv.shape[0] > 1:
        for n in range(qv.shape[0]):
            vals = np.array([qs[n] for _, _, qs in candidates], dtype=np.float32)
            out[f"query_similarity_{n + 1}"] = vals
        weights = np.vstack([softmax_percentages(qs) for _, _, qs in candidates])
        for n in range(qv.shape[0]):
            out[f"query_weight_{n + 1}"] = weights[:, n]
    out["rank"] = np.arange(1, len(out) + 1)
    return out
