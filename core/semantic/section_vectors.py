"""Чистые операции над векторами разделов характеристик диссертаций."""

from __future__ import annotations

import os
from collections.abc import Collection, Mapping, Sequence

import numpy as np
import pandas as pd

from core.semantic.models import PairwiseDistanceDiagnostics, SectionSelection

SCORE_COLUMNS = [
    "Code", "semantic_score", "coverage", "available_section_count",
    "selected_section_count", "best_section_key", "best_section_similarity",
    "best_text_id", "section_scores",
]


def _normalize(vector: np.ndarray) -> np.ndarray | None:
    value = np.asarray(vector, dtype=np.float32)
    if value.ndim != 1 or not np.all(np.isfinite(value)):
        return None
    norm = float(np.linalg.norm(value))
    return value / norm if norm > 0.0 else None


def validate_matrix_and_index(
    matrix: np.ndarray, section_index: pd.DataFrame, expected_dimensions: int | None = None
) -> pd.DataFrame:
    """Проверяет структуру индекса без чтения строк матрицы."""
    required = {"Code", "section_key", "matrix_row"}
    if matrix is None or getattr(matrix, "ndim", 0) != 2:
        raise ValueError("Матрица векторов недоступна или имеет неверный формат.")
    if expected_dimensions is not None and int(matrix.shape[1]) != int(expected_dimensions):
        raise ValueError("Размерность матрицы не совпадает с метаданными.")
    if not required.issubset(section_index.columns):
        raise ValueError("Индекс разделов не содержит обязательных столбцов.")
    result = section_index.copy()
    numeric = pd.to_numeric(result["matrix_row"], errors="coerce")
    integral = numeric.notna() & np.isfinite(numeric) & (numeric == np.floor(numeric))
    result = result.loc[integral].copy()
    result["matrix_row"] = numeric.loc[integral].astype(int)
    result = result[(result["matrix_row"] >= 0) & (result["matrix_row"] < matrix.shape[0])]
    return result.reset_index(drop=True)


def _structural_invalid_counts(matrix: np.ndarray, section_index: pd.DataFrame) -> dict[str, int]:
    """Считает структурно неверные ссылки с привязкой к исходному Code."""
    numeric = pd.to_numeric(section_index["matrix_row"], errors="coerce")
    valid = numeric.notna() & np.isfinite(numeric) & (numeric == np.floor(numeric))
    valid &= (numeric >= 0) & (numeric < matrix.shape[0])
    invalid = section_index.loc[~valid, "Code"].astype(str)
    return invalid.value_counts().astype(int).to_dict()


def aggregate_duplicate_section_vectors(
    matrix: np.ndarray, section_index: pd.DataFrame, normalized: bool
) -> dict[str, dict[str, np.ndarray]]:
    """Усредняет дубликаты разделов и нормализует каждый итоговый центр."""
    result, _ = _aggregate_duplicate_section_vectors_with_diagnostics(matrix, section_index, normalized)
    return result


def _aggregate_duplicate_section_vectors_with_diagnostics(
    matrix: np.ndarray, section_index: pd.DataFrame, normalized: bool,
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, int]]:
    """Агрегирует векторы и считает недопустимые строки по диссертациям."""
    valid = validate_matrix_and_index(matrix, section_index)
    buckets: dict[tuple[str, str], list[np.ndarray]] = {}
    invalid_by_code: dict[str, int] = {}
    structural_by_code = _structural_invalid_counts(matrix, section_index)
    for start in range(0, len(valid), 512):
        part = valid.iloc[start:start + 512]
        values = np.asarray(matrix[part["matrix_row"].to_numpy(dtype=int)], dtype=np.float32).copy()
        norms = np.linalg.norm(values, axis=1)
        usable = np.all(np.isfinite(values), axis=1) & np.isfinite(norms) & (norms > 0)
        values[usable] /= norms[usable, None]
        for position, row in enumerate(part.itertuples(index=False)):
            if usable[position]:
                buckets.setdefault((str(row.Code), str(row.section_key)), []).append(values[position])
            else:
                code = str(row.Code)
                invalid_by_code[code] = invalid_by_code.get(code, 0) + 1
    result: dict[str, dict[str, np.ndarray]] = {}
    for (code, key), vectors in buckets.items():
        centroid = _normalize(np.mean(vectors, axis=0, dtype=np.float32))
        if centroid is not None:
            result.setdefault(code, {})[key] = centroid.astype(np.float32, copy=False)
    for code, count in structural_by_code.items():
        invalid_by_code[code] = invalid_by_code.get(code, 0) + count
    return result, invalid_by_code


def build_dissertation_section_vectors(
    codes: Collection[str], section_index: pd.DataFrame, matrix: np.ndarray,
    selection: SectionSelection, normalized: bool,
) -> tuple[dict[str, dict[str, np.ndarray]], pd.DataFrame]:
    """Строит векторы разделов и таблицу взвешенного покрытия диссертаций."""
    wanted = {str(code) for code in codes}
    subset = section_index[
        section_index["Code"].astype(str).isin(wanted)
        & section_index["section_key"].isin(selection.section_keys)
    ]
    vectors, invalid_by_code = _aggregate_duplicate_section_vectors_with_diagnostics(matrix, subset, normalized)
    weights = dict(selection.weights)
    total = sum(weights.values())
    rows = []
    for code in sorted(wanted):
        available = vectors.get(code, {})
        coverage = sum(weights[key] for key in available if key in weights) / total
        rows.append({
            "Code": code, "coverage": coverage,
            "available_section_count": len(available),
            "selected_section_count": len(selection.section_keys),
            "eligible": bool(available) and coverage >= selection.min_coverage,
            "invalid_vector_row_count": invalid_by_code.get(code, 0),
        })
    coverage_df = pd.DataFrame(rows, columns=["Code", "coverage", "available_section_count", "selected_section_count", "eligible", "invalid_vector_row_count"])
    coverage_df.attrs["invalid_vector_row_count"] = sum(invalid_by_code.values())
    eligible = set(coverage_df.loc[coverage_df["eligible"], "Code"])
    return {code: value for code, value in vectors.items() if code in eligible}, coverage_df


def score_dissertations_against_query(
    query_vector: np.ndarray, section_index: pd.DataFrame, matrix: np.ndarray,
    selection: SectionSelection, normalized: bool, batch_size: int,
) -> pd.DataFrame:
    """Оценивает все подходящие разделы пакетами без загрузки полной матрицы."""
    query = _normalize(np.asarray(query_vector, dtype=np.float32).reshape(-1))
    if query is None or matrix is None or getattr(matrix, "ndim", 0) != 2 or query.shape[0] != matrix.shape[1]:
        raise ValueError("Вектор запроса или матрица векторов имеют неверный формат.")
    subset = section_index[section_index["section_key"].isin(selection.section_keys)]
    valid = validate_matrix_and_index(matrix, subset)
    if valid.empty:
        result = pd.DataFrame(columns=SCORE_COLUMNS)
        result.attrs["invalid_vector_row_count"] = len(subset)
        return result
    best: dict[tuple[str, str], tuple[float, object]] = {}
    invalid_vector_row_count = len(subset) - len(valid)
    size = max(1, int(batch_size))
    for start in range(0, len(valid), size):
        part = valid.iloc[start:start + size]
        rows = part["matrix_row"].to_numpy(dtype=int)
        vectors = np.asarray(matrix[rows], dtype=np.float32).copy()
        norms = np.linalg.norm(vectors, axis=1)
        usable = np.all(np.isfinite(vectors), axis=1) & np.isfinite(norms) & (norms > 0)
        invalid_vector_row_count += int((~usable).sum())
        if not normalized:
            vectors[usable] /= norms[usable, None]
        scores = np.clip(vectors @ query, -1.0, 1.0)
        for pos, (_, row) in enumerate(part.iterrows()):
            if not usable[pos]:
                continue
            key = (str(row["Code"]), str(row["section_key"]))
            candidate = (float(scores[pos]), row.get("text_id"))
            previous = best.get(key)
            if previous is None or candidate[0] > previous[0]:
                best[key] = candidate
    weights = dict(selection.weights)
    total_weight = sum(weights.values())
    output = []
    for code in sorted({key[0] for key in best}):
        section_scores = {key: best[(code, key)][0] for key in selection.section_keys if (code, key) in best}
        coverage = sum(weights[key] for key in section_scores) / total_weight
        if coverage < selection.min_coverage:
            continue
        semantic_score = sum(weights[key] * value for key, value in section_scores.items()) / sum(weights[key] for key in section_scores)
        best_key = max(section_scores, key=lambda key: (section_scores[key], -selection.section_keys.index(key)))
        output.append({
            "Code": code, "semantic_score": float(np.clip(semantic_score, -1.0, 1.0)),
            "coverage": coverage, "available_section_count": len(section_scores),
            "selected_section_count": len(selection.section_keys), "best_section_key": best_key,
            "best_section_similarity": section_scores[best_key], "best_text_id": best[(code, best_key)][1],
            "section_scores": section_scores,
        })
    result = pd.DataFrame(output, columns=SCORE_COLUMNS)
    result.attrs["invalid_vector_row_count"] = invalid_vector_row_count
    return result


def composite_similarity(
    left: Mapping[str, np.ndarray], right: Mapping[str, np.ndarray], selection: SectionSelection
) -> float | None:
    """Вычисляет взвешенное сходство только по общим разделам."""
    weights = dict(selection.weights)
    values = []
    for key in selection.section_keys:
        if key in left and key in right:
            left_vector, right_vector = _normalize(left[key]), _normalize(right[key])
            if left_vector is not None and right_vector is not None:
                values.append((weights[key], float(np.clip(left_vector @ right_vector, -1.0, 1.0))))
    if not values:
        return None
    return float(np.clip(sum(weight * value for weight, value in values) / sum(weight for weight, _ in values), -1.0, 1.0))


def _maximum_pairwise_items() -> int:
    try:
        return max(1, int(os.getenv("SEMANTIC_MAX_PAIRWISE_ITEMS", "2500")))
    except ValueError:
        return 2500


def composite_distance_matrix(
    items: Sequence[Mapping[str, np.ndarray]], selection: SectionSelection, batch_size: int
) -> tuple[np.ndarray | None, PairwiseDistanceDiagnostics]:
    """Строит полную матрицу расстояний или возвращает диагностику неопределённости."""
    count = len(items)
    maximum = _maximum_pairwise_items()
    diagnostics = PairwiseDistanceDiagnostics(count, 0, len(selection.section_keys), selection.min_coverage, "ok", maximum)
    if count > maximum:
        diagnostics = PairwiseDistanceDiagnostics(count, 0, len(selection.section_keys), selection.min_coverage, "item_limit", maximum)
        return None, diagnostics
    numerator = np.zeros((count, count), dtype=np.float32)
    denominator = np.zeros((count, count), dtype=np.float32)
    size = max(1, int(batch_size))
    dimensions = next((np.asarray(vector).size for item in items for vector in item.values()), 0)
    for section_key, weight in selection.weights:
        presence = np.zeros(count, dtype=bool)
        aligned = np.zeros((count, dimensions), dtype=np.float32)
        for index, item in enumerate(items):
            vector = _normalize(item[section_key]) if section_key in item else None
            if vector is not None and vector.size == dimensions:
                presence[index] = True
                aligned[index] = vector
        for row_start in range(0, count, size):
            row_stop = min(count, row_start + size)
            for col_start in range(0, count, size):
                col_stop = min(count, col_start + size)
                common = presence[row_start:row_stop, None] & presence[None, col_start:col_stop]
                similarities = aligned[row_start:row_stop] @ aligned[col_start:col_stop].T
                numerator[row_start:row_stop, col_start:col_stop] += np.where(common, weight * similarities, 0.0)
                denominator[row_start:row_stop, col_start:col_stop] += common.astype(np.float32) * weight
    upper = np.triu(np.ones((count, count), dtype=bool), 1)
    undefined = int(np.count_nonzero((denominator == 0) & upper))
    distances = np.zeros((count, count), dtype=np.float32)
    defined = denominator > 0
    distances[defined] = np.clip(1.0 - numerator[defined] / denominator[defined], 0.0, 2.0)
    np.fill_diagonal(distances, 0.0)
    reason = "undefined_pairs" if undefined else "ok"
    diagnostics = PairwiseDistanceDiagnostics(count, undefined, len(selection.section_keys), selection.min_coverage, reason, maximum)
    return (None if undefined else distances), diagnostics
