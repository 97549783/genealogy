"""Расстояния и описательные показатели семантического анализа."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_samples, silhouette_score

from core.semantic.models import SectionSelection, SemanticAnalysisLimits
from core.semantic.section_vectors import composite_similarity

DISTANCE_CATEGORY_CAPTION_RU = (
    "Удалённые работы могут отражать новые, междисциплинарные или слабо представленные направления."
)


def _positive_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def get_semantic_analysis_limits() -> SemanticAnalysisLimits:
    """Читает безопасные ограничения анализа из переменных окружения."""
    return SemanticAnalysisLimits(
        _positive_env("SEMANTIC_DISTANCE_BATCH_SIZE", 512),
        _positive_env("SEMANTIC_SCHOOL_BATCH_SIZE", 250),
        _positive_env("SEMANTIC_MAX_PAIRWISE_ITEMS", 2500),
    )


def distance_to_profile(
    dissertation: Mapping[str, np.ndarray], profile: Mapping[str, np.ndarray], selection: SectionSelection
) -> float | None:
    """Возвращает семантическое расстояние до профиля по общим разделам."""
    similarity = composite_similarity(dissertation, profile, selection)
    return None if similarity is None else float(np.clip(1.0 - similarity, 0.0, 2.0))


def find_medoid(codes: Sequence[str], distance_matrix: np.ndarray) -> tuple[str, float]:
    """Находит код объекта с наименьшим средним расстоянием."""
    matrix = np.array(distance_matrix, dtype=np.float64, copy=True)
    if matrix.shape != (len(codes), len(codes)) or not codes or not np.all(np.isfinite(matrix)):
        raise ValueError("Матрица расстояний не соответствует списку диссертаций.")
    means = matrix.mean(axis=1)
    index = int(np.argmin(means))
    return str(codes[index]), float(means[index])


def summarize_heterogeneity(distances: Sequence[float]) -> dict[str, float]:
    """Суммирует распределение конечных семантических расстояний."""
    values = np.asarray(distances, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not values.size:
        raise ValueError("Для расчёта неоднородности нет допустимых расстояний.")
    median = float(np.median(values))
    return {
        "mean_distance": float(np.mean(values)), "median_distance": median,
        "percentile_90_distance": float(np.percentile(values, 90)), "core_radius": median,
        "minimum_distance": float(np.min(values)), "maximum_distance": float(np.max(values)),
    }


def categorize_distances(codes: Sequence[str], distances: Sequence[float]) -> pd.DataFrame:
    """Ранжирует расстояния и присваивает нейтральные категории для крупных наборов."""
    if len(codes) != len(distances):
        raise ValueError("Число кодов и расстояний должно совпадать.")
    frame = pd.DataFrame({"Code": [str(code) for code in codes], "distance": np.asarray(distances, dtype=float)})
    if not np.all(np.isfinite(frame["distance"])):
        raise ValueError("Все расстояния должны быть конечными числами.")
    frame["rank"] = frame["distance"].rank(method="first", ascending=True).astype(int)
    frame["category"] = pd.Series([None] * len(frame), dtype="object")
    if len(frame) >= 5:
        q25, q75, q90 = np.percentile(frame["distance"], [25, 75, 90])
        frame.loc[frame["distance"] <= q25, "category"] = "Тематическое ядро"
        frame.loc[(frame["distance"] > q25) & (frame["distance"] <= q75), "category"] = "Типичные работы"
        frame.loc[(frame["distance"] > q75) & (frame["distance"] <= q90), "category"] = "Периферийные направления"
        frame.loc[frame["distance"] > q90, "category"] = "Наиболее удалённые работы"
    return frame.sort_values(["distance", "Code"], kind="stable").reset_index(drop=True)


def compute_precomputed_silhouette(
    distance_matrix: np.ndarray, labels: Sequence[int]
) -> tuple[float, np.ndarray]:
    """Вычисляет общий и пообъектный силуэт для готовых расстояний."""
    matrix = np.asarray(distance_matrix, dtype=np.float64)
    label_values = np.asarray(labels)
    if matrix.shape != (len(label_values), len(label_values)) or not np.all(np.isfinite(matrix)):
        raise ValueError("Матрица расстояний имеет неверный размер или содержит недопустимые значения.")
    matrix = np.clip(matrix, 0.0, 2.0)
    np.fill_diagonal(matrix, 0.0)
    samples = silhouette_samples(matrix, label_values, metric="precomputed")
    score = silhouette_score(matrix, label_values, metric="precomputed")
    return float(score), np.asarray(samples, dtype=np.float64)
