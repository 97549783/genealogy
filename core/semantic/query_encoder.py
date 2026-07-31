"""Ленивое кодирование текстовых запросов в семантические векторы."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Sequence

import numpy as np
import streamlit as st


def is_query_encoder_available() -> bool:
    """Проверяет доступность библиотеки кодирования запросов."""
    return importlib.util.find_spec("sentence_transformers") is not None


def get_query_encoder_device() -> str:
    """Возвращает настроенное устройство для модели запросов."""
    return str(os.getenv("DISS_QUERY_ENCODER_DEVICE", "cpu") or "cpu").strip() or "cpu"


@st.cache_resource(show_spinner=False)
def load_query_encoder(model_name: str, device: str):
    """Загружает модель только при первом явном кодировании запроса."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


def prepare_queries(queries: Sequence[str], model_name: str) -> list[str]:
    """Очищает до пяти запросов и добавляет обязательный префикс E5."""
    cleaned = [str(value).strip() for value in queries if str(value).strip()][:5]
    if "e5" in str(model_name).casefold():
        return [f"query: {value}" for value in cleaned]
    return cleaned


def encode_queries(
    queries: Sequence[str], model_name: str, normalize_embeddings: bool, device: str
) -> np.ndarray:
    """Кодирует подготовленные запросы в матрицу ``float32``."""
    prepared = prepare_queries(queries, model_name)
    if not prepared:
        return np.zeros((0, 0), dtype=np.float32)
    encoder = load_query_encoder(model_name, device)
    return np.asarray(
        encoder.encode(prepared, normalize_embeddings=normalize_embeddings), dtype=np.float32
    )


def combine_query_vectors(query_vectors: np.ndarray) -> np.ndarray:
    """Усредняет векторы запросов и нормализует полученный центр."""
    vectors = np.asarray(query_vectors, dtype=np.float32)
    if vectors.ndim != 2 or not vectors.shape[0] or not vectors.shape[1]:
        return np.zeros((0,), dtype=np.float32)
    mean = vectors.mean(axis=0, dtype=np.float32)
    norm = float(np.linalg.norm(mean))
    return mean / norm if norm > 0.0 else np.zeros_like(mean)
