"""Вспомогательные функции нейросетевого поиска по разделам статьи."""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pandas as pd
import streamlit as st


QUERY_CONTRIBUTION_TEMPERATURE = 0.1


def is_query_encoder_enabled() -> bool:
    """Проверяет доступность энкодера пользовательских запросов."""
    return importlib.util.find_spec("sentence_transformers") is not None


@st.cache_resource(show_spinner=False)
def load_query_encoder(model_name: str, device: str):
    """Ленивая загрузка модели энкодера запросов."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


def encode_user_queries(
    queries: list[str],
    model_name: str,
    normalize_embeddings: bool,
    device: str = "cpu",
) -> np.ndarray:
    """Кодирует пользовательские запросы в векторы с префиксом query:."""
    prepared = [f"query: {str(q).strip()}" for q in queries if str(q).strip()]
    if not prepared:
        return np.zeros((0, 0), dtype=np.float32)
    encoder = load_query_encoder(model_name=model_name, device=device)
    vectors = encoder.encode(prepared, normalize_embeddings=normalize_embeddings)
    return np.asarray(vectors, dtype=np.float32)


def collect_non_empty_queries(values: list[str], max_queries: int = 5) -> list[str]:
    """Возвращает непустые пользовательские запросы, не больше заданного числа."""
    cleaned: list[str] = []
    for value in values[:max_queries]:
        text = str(value or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


def average_query_vectors(query_vectors: np.ndarray) -> np.ndarray:
    """Усредняет векторы запросов и нормализует итоговый вектор."""
    mean_query = np.asarray(query_vectors, dtype=np.float32).mean(axis=0)
    norm = float(np.linalg.norm(mean_query))
    return mean_query / max(norm, 1e-12)


def softmax_percentages(values: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Возвращает процентные вклады запросов через softmax."""
    vals = np.asarray(values, dtype=np.float32)
    z = vals / max(float(temperature), 1e-12)
    z = z - np.max(z)
    weights = np.exp(z)
    denom = np.sum(weights)
    if denom <= 0:
        return np.zeros_like(vals)
    return (weights / denom) * 100.0


def search_sections_by_query_vector(
    query_vectors: np.ndarray,
    matrix: np.ndarray,
    target_df: pd.DataFrame,
    top_n: int,
    normalized: bool = True,
) -> pd.DataFrame:
    """Ищет статьи по среднему вектору запросов и добавляет вклады отдельных запросов."""
    if target_df.empty:
        return target_df.copy()
    rows = target_df["matrix_row"].astype(int).to_numpy()
    target_vectors = np.asarray(matrix[rows], dtype=np.float32)
    if not normalized:
        norms = np.linalg.norm(target_vectors, axis=1)
        target_vectors = target_vectors / np.where(norms == 0, 1.0, norms)[:, None]

    mean_query = average_query_vectors(query_vectors)
    sims = target_vectors @ mean_query
    out = target_df.copy()
    out["similarity"] = sims

    if query_vectors.shape[0] > 1:
        query_sims = target_vectors @ query_vectors.T
        for i in range(query_vectors.shape[0]):
            out[f"query_similarity_{i + 1}"] = query_sims[:, i]
        weights = np.vstack([
            softmax_percentages(row, temperature=QUERY_CONTRIBUTION_TEMPERATURE)
            for row in query_sims
        ])
        for i in range(query_vectors.shape[0]):
            out[f"query_weight_{i + 1}"] = weights[:, i]

    out = out.sort_values("similarity", ascending=False).head(int(top_n)).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def get_query_encoder_device() -> str:
    """Возвращает устройство энкодера из переменной окружения."""
    return str(os.getenv("IMRAD_QUERY_ENCODER_DEVICE", "cpu") or "cpu").strip() or "cpu"
