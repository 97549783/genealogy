"""Чистый семантический анализ структуры одной научной школы."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.semantic.distances import (
    categorize_distances, compute_precomputed_silhouette, distance_to_profile,
    find_medoid, get_semantic_analysis_limits, summarize_heterogeneity,
)
from core.semantic.models import PairwiseDistanceDiagnostics, SectionSelection
from core.semantic.school_profiles import build_school_section_profile
from core.semantic.section_vectors import composite_distance_matrix, composite_similarity, build_dissertation_section_vectors
from tabs.dissertation_characteristics.labels import SECTION_LABELS_RU
from core.perf import perf_timer


@dataclass(frozen=True)
class SchoolSemanticDataset:
    """Хранит покрытые векторы, метаданные и исключения одной школы."""

    root: str
    dissertation_vectors: dict[str, dict[str, np.ndarray]]
    metadata: pd.DataFrame
    coverage: pd.DataFrame
    excluded: pd.DataFrame
    total_member_count: int


@dataclass(frozen=True)
class SchoolHeterogeneityResult:
    """Содержит центр, расстояния, медоид и показатели неоднородности."""

    summary: pd.DataFrame
    dissertation_distances: pd.DataFrame
    medoid_code: str | None
    medoid_mean_distance: float | None
    distance_matrix: np.ndarray | None
    pairwise_diagnostics: PairwiseDistanceDiagnostics
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class GenerationSemanticResult:
    """Содержит динамику поколений и их секционные профили."""

    summary: pd.DataFrame
    profiles: dict[int, dict[str, np.ndarray]]
    dissertation_details: dict[int, pd.DataFrame]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class BranchSemanticResult:
    """Содержит профили ветвей, сходство и силуэт уникальных назначений."""

    summary: pd.DataFrame
    profiles: dict[str, dict[str, np.ndarray]]
    similarity_matrix: pd.DataFrame
    silhouette_overall: float | None
    silhouette_by_branch: pd.DataFrame
    dissertation_silhouettes: pd.DataFrame
    dissertation_details: dict[str, pd.DataFrame]
    ambiguous_dissertations: pd.DataFrame
    diagnostics: tuple[str, ...]


def _metadata_for_members(metadata: pd.DataFrame, members: set[str]) -> pd.DataFrame:
    """Безопасно выбирает по одной строке метаданных для каждого Code."""
    source = metadata.copy()
    if "Code" not in source.columns:
        source = pd.DataFrame(columns=["Code"])
    source["Code"] = source["Code"].astype(str).str.strip()
    source = source.drop_duplicates("Code", keep="first")
    return pd.DataFrame({"Code": sorted(members)}).merge(source, on="Code", how="left")


def build_school_semantic_dataset(
    *, root: str, member_codes: Collection[str], section_index: pd.DataFrame,
    matrix: np.ndarray, selection: SectionSelection, normalized: bool,
    dissertation_metadata: pd.DataFrame,
) -> SchoolSemanticDataset:
    """Строит набор школы с явным покрытием без нулевого заполнения."""
    members = {str(code).strip() for code in member_codes if str(code).strip()}
    vectors, coverage = build_dissertation_section_vectors(
        members, section_index, matrix, selection, normalized,
    )
    metadata = _metadata_for_members(dissertation_metadata, members)
    included = metadata[metadata["Code"].isin(vectors)].merge(
        coverage.drop(columns=["eligible"], errors="ignore"), on="Code", how="left",
    )
    excluded = metadata[~metadata["Code"].isin(vectors)].merge(coverage, on="Code", how="left")
    excluded["Причина исключения"] = "Недостаточное покрытие выбранных разделов"
    return SchoolSemanticDataset(
        root, vectors, included.reset_index(drop=True), coverage,
        excluded.reset_index(drop=True), len(members),
    )


def compute_school_semantic_center(
    dataset: SchoolSemanticDataset, selection: SectionSelection,
) -> dict[str, np.ndarray]:
    """Вычисляет нормализованный центр школы отдельно для каждого раздела."""
    with perf_timer("semantic.analysis.build_center"):
        profile, _ = build_school_section_profile(
            dataset.dissertation_vectors, dataset.dissertation_vectors.keys(), selection,
        )
    return profile


def _section_extremes(
    vectors: Mapping[str, np.ndarray], center: Mapping[str, np.ndarray], selection: SectionSelection,
) -> tuple[str | None, str | None]:
    """Находит наиболее близкий и наиболее отличающийся общие разделы."""
    values = []
    for key in selection.section_keys:
        if key in vectors and key in center:
            similarity = composite_similarity({key: vectors[key]}, {key: center[key]}, selection)
            if similarity is not None:
                values.append((1.0 - similarity, key))
    if not values:
        return None, None
    values.sort(key=lambda item: (item[0], selection.section_keys.index(item[1])))
    return SECTION_LABELS_RU[values[0][1]], SECTION_LABELS_RU[values[-1][1]]


def _display_metadata(dataset: SchoolSemanticDataset, code: str) -> dict[str, object]:
    """Возвращает русскоязычные поля диссертации для итоговой таблицы."""
    rows = dataset.metadata[dataset.metadata["Code"].astype(str) == str(code)]
    row = rows.iloc[0] if not rows.empty else pd.Series(dtype=object)
    return {
        "Автор": row.get("candidate_name", row.get("Автор", "—")),
        "Название": row.get("title", row.get("Название", "—")),
        "Год": row.get("year", row.get("Год", None)),
        "Поколение": row.get("Поколение", row.get("generation", None)),
    }


def _representative_label(dataset: SchoolSemanticDataset, code: str | None) -> str | None:
    """Формирует понятную подпись реальной репрезентативной диссертации."""
    if code is None:
        return None
    metadata = _display_metadata(dataset, code)
    author, title = metadata["Автор"], metadata["Название"]
    return f"{author} — {title}" if title not in (None, "", "—") else str(author)


def compute_school_heterogeneity(
    dataset: SchoolSemanticDataset, center: Mapping[str, np.ndarray],
    selection: SectionSelection,
) -> SchoolHeterogeneityResult:
    """Вычисляет расстояния до центра, неоднородность и реальный медоид."""
    codes, distances = [], []
    rows = []
    coverage = dataset.coverage.set_index("Code") if not dataset.coverage.empty else pd.DataFrame()
    for code in sorted(dataset.dissertation_vectors):
        vectors = dataset.dissertation_vectors[code]
        distance = distance_to_profile(vectors, center, selection)
        if distance is None:
            continue
        codes.append(code)
        distances.append(distance)
        closest, different = _section_extremes(vectors, center, selection)
        coverage_value = float(coverage.loc[code, "coverage"]) if not coverage.empty and code in coverage.index else 0.0
        rows.append({
            **_display_metadata(dataset, code),
            "Тематическое расстояние до центра": distance, "Категория": None,
            "Полнота характеристик, %": coverage_value * 100,
            "Наиболее близкий раздел": closest, "Наиболее отличающийся раздел": different,
            "Code": code,
        })
    distance_columns = [
        "Автор", "Название", "Год", "Поколение", "Тематическое расстояние до центра",
        "Категория", "Полнота характеристик, %", "Наиболее близкий раздел",
        "Наиболее отличающийся раздел", "Code",
    ]
    distance_table = pd.DataFrame(rows, columns=distance_columns)
    if distances:
        categories = categorize_distances(codes, distances).set_index("Code")
        distance_table["Категория"] = distance_table["Code"].map(categories["category"])
        stats = summarize_heterogeneity(distances)
    else:
        stats = {key: float("nan") for key in (
            "mean_distance", "median_distance", "percentile_90_distance", "core_radius",
            "minimum_distance", "maximum_distance",
        )}
    items = [dataset.dissertation_vectors[code] for code in codes]
    matrix, pairwise = composite_distance_matrix(items, selection, get_semantic_analysis_limits().batch_size)
    medoid_code = None
    medoid_mean = None
    diagnostics = []
    if not codes:
        diagnostics.append("Нет диссертаций с достаточным покрытием выбранных разделов.")
    if matrix is not None and codes:
        with perf_timer("semantic.analysis.compute_medoid"):
            medoid_code, medoid_mean = find_medoid(codes, matrix)
    elif pairwise.undefined_pair_count:
        diagnostics.append("Для части диссертаций не определены попарные расстояния по общим разделам.")
    elif items:
        diagnostics.append("Число диссертаций превышает настроенный предел попарного анализа.")
    average_coverage = float(dataset.coverage["coverage"].mean() * 100) if not dataset.coverage.empty else 0.0
    summary = pd.DataFrame([
        {"Показатель": "Диссертаций с достаточным покрытием", "Значение": len(codes)},
        {"Показатель": "Исключено диссертаций", "Значение": len(dataset.excluded)},
        {"Показатель": "Среднее тематическое расстояние", "Значение": stats["mean_distance"]},
        {"Показатель": "Медианное тематическое расстояние", "Значение": stats["median_distance"]},
        {"Показатель": "90-й процентиль расстояния", "Значение": stats["percentile_90_distance"]},
        {"Показатель": "Радиус тематического ядра", "Значение": stats["core_radius"]},
        {"Показатель": "Выбрано разделов", "Значение": len(selection.section_keys)},
        {"Показатель": "Средняя полнота характеристик, %", "Значение": average_coverage},
    ])
    return SchoolHeterogeneityResult(
        summary, distance_table.sort_values("Тематическое расстояние до центра", kind="stable").reset_index(drop=True),
        medoid_code, medoid_mean, matrix, pairwise, tuple(diagnostics),
    )


def _subset_profile(dataset: SchoolSemanticDataset, codes: Collection[str], selection: SectionSelection):
    """Строит профиль для заданного подмножества Code."""
    eligible = {str(code) for code in codes} & set(dataset.dissertation_vectors)
    return build_school_section_profile(dataset.dissertation_vectors, eligible, selection)[0], eligible


def _medoid_for_codes(dataset: SchoolSemanticDataset, codes: set[str], selection: SectionSelection) -> str | None:
    """Возвращает медоид подмножества, если попарная матрица определена."""
    ordered = sorted(codes)
    if len(ordered) < 3:
        return None
    matrix, _ = composite_distance_matrix(
        [dataset.dissertation_vectors[code] for code in ordered], selection,
        get_semantic_analysis_limits().batch_size,
    )
    return find_medoid(ordered, matrix)[0] if matrix is not None else None


def compute_generation_semantics(
    dataset: SchoolSemanticDataset, generation_codes: Mapping[int, set[str]],
    selection: SectionSelection,
) -> GenerationSemanticResult:
    """Вычисляет преемственность и тематический сдвиг поколений."""
    overall = compute_school_semantic_center(dataset, selection)
    profiles: dict[int, dict[str, np.ndarray]] = {}
    eligible_by_generation: dict[int, set[str]] = {}
    for generation in sorted(generation_codes):
        profiles[generation], eligible_by_generation[generation] = _subset_profile(
            dataset, generation_codes[generation], selection,
        )
    first_generation = min(profiles) if profiles else None
    rows, details, diagnostics = [], {}, []
    previous = None
    coverage_index = dataset.coverage.set_index("Code") if not dataset.coverage.empty else pd.DataFrame()
    for generation in sorted(profiles):
        eligible = eligible_by_generation[generation]
        profile = profiles[generation]
        internal = None
        medoid = None
        if len(eligible) >= 3:
            values = [distance_to_profile(dataset.dissertation_vectors[code], profile, selection) for code in eligible]
            finite = [value for value in values if value is not None]
            internal = float(np.mean(finite)) if finite else None
            medoid = _medoid_for_codes(dataset, eligible, selection)
            if len(eligible) < 5:
                diagnostics.append(f"Для поколения {generation} количественные выводы требуют осторожности: доступно менее пяти диссертаций.")
        elif eligible:
            diagnostics.append(f"Для поколения {generation} недостаточно данных для интерпретации неоднородности и медоида.")
        continuity = composite_similarity(profiles[previous], profile, selection) if previous is not None else None
        first_similarity = composite_similarity(profiles[first_generation], profile, selection) if first_generation is not None else None
        school_similarity = composite_similarity(profile, overall, selection)
        generation_members = {str(code) for code in generation_codes[generation]}
        detail = _metadata_for_members(dataset.metadata, generation_members)
        detail = detail.merge(dataset.coverage[["Code", "coverage", "eligible"]], on="Code", how="left")
        detail["Тематическое расстояние до профиля поколения"] = detail["Code"].map(
            lambda code: distance_to_profile(dataset.dissertation_vectors[code], profile, selection)
            if code in dataset.dissertation_vectors else None
        )
        detail["Репрезентативная диссертация"] = detail["Code"].eq(medoid)
        detail["Причина исключения"] = np.where(
            detail["Code"].isin(eligible), None, "Недостаточное покрытие выбранных разделов",
        )
        details[generation] = detail
        coverage_values = [float(coverage_index.loc[code, "coverage"]) for code in generation_members
                           if not coverage_index.empty and code in coverage_index.index]
        rows.append({
            "Поколение": generation, "Всего диссертаций": len(generation_codes[generation]),
            "Диссертаций с векторами": len(eligible),
            "Доля диссертаций с достаточным покрытием, %": len(eligible) / len(generation_members) * 100 if generation_members else 0.0,
            "Среднее покрытие выбранных разделов, %": float(np.mean(coverage_values) * 100) if coverage_values else 0.0,
            "Тематическая неоднородность": internal,
            "Сходство с предыдущим поколением": continuity,
            "Расстояние от первого поколения": None if first_similarity is None else 1.0 - first_similarity,
            "Сходство с профилем школы": school_similarity,
            "Репрезентативная диссертация": _representative_label(dataset, medoid),
        })
        previous = generation
    return GenerationSemanticResult(pd.DataFrame(rows), profiles, details, tuple(dict.fromkeys(diagnostics)))


def compute_branch_semantics(
    dataset: SchoolSemanticDataset, branch_codes: Mapping[str, set[str]],
    selection: SectionSelection,
) -> BranchSemanticResult:
    """Сравнивает естественные ветви и исключает неоднозначные Code только из силуэта."""
    overall = compute_school_semantic_center(dataset, selection)
    profiles, eligible_by_branch = {}, {}
    membership_count: dict[str, int] = {}
    for branch, codes in branch_codes.items():
        profiles[branch], eligible_by_branch[branch] = _subset_profile(dataset, codes, selection)
        for code in eligible_by_branch[branch]:
            membership_count[code] = membership_count.get(code, 0) + 1
    ambiguous_codes = {code for code, count in membership_count.items() if count > 1}
    ambiguous_rows = []
    for code in sorted(ambiguous_codes):
        metadata = _display_metadata(dataset, code)
        memberships = [branch for branch, codes in eligible_by_branch.items() if code in codes]
        ambiguous_rows.append({
            "Автор": metadata["Автор"], "Название": metadata["Название"], "Год": metadata["Год"],
            "Ветви": "; ".join(memberships),
            "Причина исключения": "Диссертация относится к нескольким естественным ветвям",
            "Code": code,
        })
    ambiguous = pd.DataFrame(
        ambiguous_rows, columns=["Автор", "Название", "Год", "Ветви", "Причина исключения", "Code"],
    )
    rows = []
    details: dict[str, pd.DataFrame] = {}
    coverage_index = dataset.coverage.set_index("Code") if not dataset.coverage.empty else pd.DataFrame()
    for branch in branch_codes:
        eligible = eligible_by_branch[branch]
        profile = profiles[branch]
        distances = [(code, distance_to_profile(dataset.dissertation_vectors[code], profile, selection)) for code in eligible]
        finite = [(code, value) for code, value in distances if value is not None]
        heterogeneity = float(np.mean([value for _, value in finite])) if len(finite) >= 3 else None
        medoid = _medoid_for_codes(dataset, eligible, selection)
        farthest = max(finite, key=lambda item: item[1])[0] if finite else None
        generations = dataset.metadata.loc[dataset.metadata["Code"].isin(eligible), "Поколение"] if "Поколение" in dataset.metadata else pd.Series(dtype=float)
        coverage_values = [float(coverage_index.loc[code, "coverage"]) for code in branch_codes[branch]
                           if not coverage_index.empty and code in coverage_index.index]
        detail = _metadata_for_members(dataset.metadata, {str(code) for code in branch_codes[branch]})
        detail = detail.merge(dataset.coverage[["Code", "coverage", "eligible"]], on="Code", how="left")
        detail["Тематическое расстояние до профиля ветви"] = detail["Code"].map(
            lambda code: distance_to_profile(dataset.dissertation_vectors[code], profile, selection)
            if code in dataset.dissertation_vectors else None
        )
        detail["Репрезентативная диссертация"] = detail["Code"].eq(medoid)
        detail["Наиболее удалённая диссертация"] = detail["Code"].eq(farthest)
        detail["Причина исключения"] = np.where(
            detail["Code"].isin(eligible), None, "Недостаточное покрытие выбранных разделов",
        )
        details[branch] = detail
        rows.append({
            "Ветвь": branch, "Всего диссертаций": len(branch_codes[branch]),
            "Диссертаций с векторами": len(eligible), "Поколений": int(generations.dropna().nunique()),
            "Доля диссертаций с достаточным покрытием, %": len(eligible) / len(branch_codes[branch]) * 100 if branch_codes[branch] else 0.0,
            "Среднее покрытие выбранных разделов, %": float(np.mean(coverage_values) * 100) if coverage_values else 0.0,
            "Тематическая неоднородность": heterogeneity,
            "Сходство с профилем школы": composite_similarity(profile, overall, selection),
            "Репрезентативная диссертация": _representative_label(dataset, medoid),
            "Наиболее удалённая диссертация": _representative_label(dataset, farthest),
        })
    branches = list(branch_codes)
    similarity = pd.DataFrame(index=branches, columns=branches, dtype=float)
    for left in branches:
        for right in branches:
            similarity.loc[left, right] = composite_similarity(profiles[left], profiles[right], selection)
    similarity.index.name = "Ветвь"
    unique_by_branch = {
        branch: eligible_by_branch[branch] - ambiguous_codes for branch in branches
    }
    included = {branch: codes for branch, codes in unique_by_branch.items() if len(codes) >= 3}
    silhouette_overall = None
    silhouette_rows, sample_rows, diagnostics = [], [], []
    if len(included) >= 2:
        items, labels, sample_codes = [], [], []
        included_branches = list(included)
        for label, branch in enumerate(included_branches):
            for code in sorted(included[branch]):
                items.append(dataset.dissertation_vectors[code]); labels.append(label); sample_codes.append((branch, code))
        matrix, pairwise = composite_distance_matrix(items, selection, get_semantic_analysis_limits().batch_size)
        if matrix is not None:
            silhouette_overall, samples = compute_precomputed_silhouette(matrix, labels)
            for (branch, code), value in zip(sample_codes, samples):
                sample_rows.append({"Ветвь": branch, "Code": code, "Коэффициент силуэта": value})
            sample_frame = pd.DataFrame(sample_rows)
            for branch in included_branches:
                values = sample_frame.loc[sample_frame["Ветвь"] == branch, "Коэффициент силуэта"]
                silhouette_rows.append({
                    "Ветвь": branch, "Средний коэффициент силуэта": float(values.mean()),
                    "Медианный коэффициент силуэта": float(values.median()),
                    "Доля отрицательных значений, %": float((values < 0).mean() * 100),
                })
        elif pairwise.undefined_pair_count:
            diagnostics.append("Силуэт ветвей не определён: некоторые диссертации не имеют общих выбранных разделов.")
        else:
            diagnostics.append("Число диссертаций превышает настроенный предел попарного анализа ветвей.")
    else:
        diagnostics.append("Для силуэта нужны минимум две ветви с тремя уникально назначенными диссертациями в каждой.")
    return BranchSemanticResult(
        pd.DataFrame(rows), profiles, similarity.reset_index(), silhouette_overall,
        pd.DataFrame(silhouette_rows), pd.DataFrame(sample_rows), details,
        ambiguous.reset_index(drop=True), tuple(diagnostics),
    )
