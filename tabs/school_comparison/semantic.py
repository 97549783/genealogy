"""Чистая подготовка сравнения школ по векторам характеристик."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.semantic.distances import compute_precomputed_silhouette
from core.semantic.models import PairwiseDistanceDiagnostics, SectionSelection, build_section_selection
from core.semantic.section_vectors import (
    aggregate_duplicate_section_vectors, build_dissertation_section_vectors, composite_distance_matrix,
)
from tabs.dissertation_characteristics.labels import SECTION_LABELS_RU
from core.perf import perf_timer

PER_SECTION_COLUMNS = [
    "Раздел характеристики", "Коэффициент силуэта", "Число школ",
    "Число диссертаций", "Полнота данных, %", "Статус",
]


@dataclass(frozen=True)
class SemanticSchoolDataset:
    """Хранит векторы и метаданные диссертаций одной школы."""

    root: str
    all_section_vectors: dict[str, dict[str, np.ndarray]]
    eligible_dissertation_vectors: dict[str, dict[str, np.ndarray]]
    metadata: pd.DataFrame
    coverage: pd.DataFrame
    excluded: pd.DataFrame
    total_member_count: int

    @property
    def dissertation_vectors(self) -> dict[str, dict[str, np.ndarray]]:
        """Сохраняет совместимое имя покрытых векторов."""
        return self.eligible_dissertation_vectors


@dataclass(frozen=True)
class SemanticSchoolComparisonResult:
    """Хранит полный результат семантического сравнения школ."""

    overall_silhouette: float | None
    dissertation_silhouettes: pd.DataFrame
    school_summary: pd.DataFrame
    per_section_silhouette: pd.DataFrame
    excluded_dissertations: pd.DataFrame
    diagnostics: tuple[str, ...]
    pairwise_diagnostics: PairwiseDistanceDiagnostics
    distance_matrix: np.ndarray | None


def gather_semantic_school_dataset(
    *, root: str, member_codes: Collection[str], section_index: pd.DataFrame,
    matrix: np.ndarray, selection: SectionSelection, normalized: bool,
    metadata_df: pd.DataFrame,
) -> SemanticSchoolDataset:
    """Собирает покрытые векторные представления одной школы."""
    members = {str(code).strip() for code in member_codes if str(code).strip()}
    vectors, coverage = build_dissertation_section_vectors(
        members, section_index, matrix, selection, normalized,
    )
    subset_index = section_index[
        section_index["Code"].astype(str).isin(members)
        & section_index["section_key"].isin(selection.section_keys)
    ]
    all_vectors = aggregate_duplicate_section_vectors(matrix, subset_index, normalized)
    source_metadata = metadata_df.copy()
    if "Code" not in source_metadata.columns:
        source_metadata = pd.DataFrame(columns=["Code"])
    source_metadata["Code"] = source_metadata["Code"].astype(str).str.strip()
    source_metadata = source_metadata.drop_duplicates("Code", keep="first")
    metadata = pd.DataFrame({"Code": sorted(members)}).merge(source_metadata, on="Code", how="left")
    included_codes = set(vectors)
    included = metadata[metadata["Code"].isin(included_codes)].copy()
    included["Школа"] = root
    included = included.merge(coverage.drop(columns=["eligible"], errors="ignore"), on="Code", how="left")
    excluded = metadata[~metadata["Code"].isin(included_codes)].copy()
    excluded["Школа"] = root
    excluded = excluded.merge(coverage, on="Code", how="left")
    excluded["Причина исключения"] = np.where(
        excluded.get("invalid_vector_row_count", 0).fillna(0) > 0,
        "Недопустимые или нулевые строки векторной матрицы",
        "Недостаточное покрытие выбранных разделов",
    )
    return SemanticSchoolDataset(root, all_vectors, vectors, included.reset_index(drop=True), coverage,
                                 excluded.reset_index(drop=True), len(members))


def _empty_diagnostics(datasets: Mapping[str, SemanticSchoolDataset], selection: SectionSelection) -> PairwiseDistanceDiagnostics:
    return PairwiseDistanceDiagnostics(
        sum(len(dataset.dissertation_vectors) for dataset in datasets.values()), 0,
        len(selection.section_keys), selection.min_coverage, "insufficient_samples",
    )


def _school_count_summary(datasets: Mapping[str, SemanticSchoolDataset]) -> pd.DataFrame:
    """Возвращает доступные счётчики независимо от результата силуэта."""
    return pd.DataFrame([{
        "Научная школа": root,
        "Включено диссертаций": len(dataset.eligible_dissertation_vectors),
        "Исключено диссертаций": len(dataset.excluded),
        "Средний коэффициент силуэта": None,
        "Медианный коэффициент силуэта": None,
        "Доля отрицательных значений, %": None,
    } for root, dataset in datasets.items()])


def compute_semantic_school_comparison(
    *, datasets: Mapping[str, SemanticSchoolDataset], selection: SectionSelection,
    distance_batch_size: int,
) -> SemanticSchoolComparisonResult:
    """Вычисляет общий силуэт, сохраняя повторные членства между школами."""
    codes: list[str] = []
    items: list[Mapping[str, np.ndarray]] = []
    labels: list[int] = []
    roots = list(datasets)
    metadata_rows: list[dict[str, object]] = []
    for label, root in enumerate(roots):
        dataset = datasets[root]
        metadata = dataset.metadata.set_index("Code", drop=False) if not dataset.metadata.empty else pd.DataFrame()
        for code in sorted(dataset.dissertation_vectors):
            codes.append(code)
            items.append(dataset.dissertation_vectors[code])
            labels.append(label)
            row = metadata.loc[code].to_dict() if not metadata.empty and code in metadata.index else {"Code": code}
            row["Школа"] = root
            metadata_rows.append(row)
    diagnostics = _empty_diagnostics(datasets, selection)
    excluded = pd.concat([value.excluded for value in datasets.values()], ignore_index=True) if datasets else pd.DataFrame()
    counts = _school_count_summary(datasets)
    per_section = compute_per_section_silhouette(datasets=datasets, selection=selection)
    if len({label for label in labels}) < 2 or any(labels.count(label) < 2 for label in set(labels)):
        return SemanticSchoolComparisonResult(
            None, pd.DataFrame(), counts, per_section,
            excluded, ("Для расчёта силуэта нужны минимум две школы и две диссертации в каждой.",), diagnostics, None,
        )
    with perf_timer("semantic.comparison.build_distance_matrix"):
        distance_matrix, diagnostics = composite_distance_matrix(items, selection, distance_batch_size)
    if distance_matrix is None:
        message = (f"Попарный анализ превышает настроенный предел: {diagnostics.maximum_pairwise_items}. Сузьте состав школ или набор разделов."
                   if diagnostics.reason == "item_limit"
                   else "Для части пар не определено расстояние: у диссертаций нет общих выбранных разделов.")
        return SemanticSchoolComparisonResult(
            None, pd.DataFrame(), counts, per_section,
            excluded, (message,), diagnostics, None,
        )
    overall, samples = compute_precomputed_silhouette(distance_matrix, labels)
    dissertation_table = pd.DataFrame(metadata_rows)
    dissertation_table["Коэффициент силуэта"] = samples
    summaries = []
    for root in roots:
        values = dissertation_table.loc[dissertation_table["Школа"] == root, "Коэффициент силуэта"]
        dataset = datasets[root]
        summaries.append({
            "Научная школа": root, "Включено диссертаций": len(values),
            "Исключено диссертаций": len(dataset.excluded),
            "Средний коэффициент силуэта": float(values.mean()),
            "Медианный коэффициент силуэта": float(values.median()),
            "Доля отрицательных значений, %": float((values < 0).mean() * 100),
        })
    return SemanticSchoolComparisonResult(
        overall, dissertation_table.reset_index(drop=True), pd.DataFrame(summaries),
        per_section, excluded, (), diagnostics, distance_matrix,
    )


def compute_per_section_silhouette(
    *, datasets: Mapping[str, SemanticSchoolDataset], selection: SectionSelection,
) -> pd.DataFrame:
    """Оценивает различимость школ отдельно по каждому доступному разделу."""
    if len(selection.section_keys) <= 1:
        return pd.DataFrame(columns=PER_SECTION_COLUMNS)
    rows: list[dict[str, object]] = []
    for section_key in selection.section_keys:
        eligible = {
            root: dataset for root, dataset in datasets.items()
            if sum(section_key in vectors for vectors in dataset.all_section_vectors.values()) >= 2
        }
        if len(eligible) < 2:
            continue
        items, labels = [], []
        available = 0
        total = sum(dataset.total_member_count for dataset in eligible.values())
        for label, dataset in enumerate(eligible.values()):
            section_items = [vectors[section_key] for vectors in dataset.all_section_vectors.values() if section_key in vectors]
            items.extend({section_key: vector} for vector in section_items)
            labels.extend([label] * len(section_items))
            available += len(section_items)
        section_selection = build_section_selection("selected", [section_key], min_coverage=0.0)
        matrix, diagnostics = composite_distance_matrix(items, section_selection, max(1, len(items)))
        if matrix is None:
            status = (f"Превышен предел: {diagnostics.maximum_pairwise_items}"
                      if diagnostics.reason == "item_limit" else "Не определены попарные расстояния")
            score = None
        else:
            score, _ = compute_precomputed_silhouette(matrix, labels)
            status = "Рассчитано"
        rows.append({
            "Раздел характеристики": SECTION_LABELS_RU[section_key],
            "Коэффициент силуэта": score, "Число школ": len(eligible),
            "Число диссертаций": len(items),
            "Полнота данных, %": available / total * 100 if total else 0.0,
            "Статус": status,
        })
    return pd.DataFrame(rows, columns=PER_SECTION_COLUMNS)
