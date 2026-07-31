"""Чистая оркестрация семантического поиска научных школ."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

import numpy as np

import pandas as pd

from core.app.context import LineageContextKey
from core.db.dissertation_sections import (
    get_dissertation_sections_db_signature,
    load_dissertation_section_index_for_selection,
    load_typed_vector_metadata,
)
from core.lineage.membership import get_all_school_member_codes, get_school_basic_stats
from core.semantic.distances import get_semantic_analysis_limits
from core.semantic.models import QueryRankingConfig, SectionSelection, SemanticScope, VectorMetadata
from core.semantic.query_encoder import combine_query_vectors, encode_queries, get_query_encoder_device, prepare_queries
from core.semantic.school_profiles import (
    aggregate_query_scores_by_school, build_school_section_profile, rank_similar_schools,
)
from core.semantic.section_vectors import build_dissertation_section_vectors, score_dissertations_against_query
from core.semantic.distances import distance_to_profile, find_medoid
from core.semantic.section_vectors import composite_distance_matrix, composite_similarity
from core.perf import perf_timer
from tabs.dissertation_characteristics.labels import SECTION_LABELS_RU
from tabs.dissertation_characteristics.search import load_dissertation_embedding_matrix

INDEX_DIAGNOSTICS_RU = {
    "section_database_unavailable": "База разделов диссертаций недоступна.",
    "no_selected_vectors": "Для выбранных разделов не найдены индексированные векторы.",
}


@dataclass(frozen=True)
class SemanticSchoolQueryResult:
    """Содержит таблицы и параметры поиска школ по запросу."""

    summary: pd.DataFrame
    dissertation_details: dict[str, pd.DataFrame]
    diagnostics: tuple[str, ...]
    selection: SectionSelection
    vector_metadata: VectorMetadata | None
    parameters: dict[str, object]


@dataclass(frozen=True)
class SimilarSchoolResult:
    """Содержит результаты поиска школ с похожими профилями."""

    summary: pd.DataFrame
    dissertation_details: dict[str, pd.DataFrame]
    diagnostics: tuple[str, ...]
    selection: SectionSelection
    vector_metadata: VectorMetadata | None
    parameters: dict[str, object]
    section_similarities: dict[str, pd.DataFrame] = field(default_factory=dict)


def _filtered_codes(
    df: pd.DataFrame, year_from: int | None, year_to: int | None,
    degree_levels: Collection[str],
) -> set[str]:
    """Применяет фильтры диссертаций до векторной загрузки."""
    work = df.copy()
    if "Code" not in work.columns:
        return set()
    if year_from is not None or year_to is not None:
        years = pd.to_numeric(work.get("year"), errors="coerce")
        if year_from is not None:
            work = work[years >= year_from]
            years = years.loc[work.index]
        if year_to is not None:
            work = work[years <= year_to]
    levels = {str(level).strip() for level in degree_levels if str(level).strip()}
    degree_column = next((name for name in ("degree.degree_level", "degree_level") if name in work.columns), None)
    if levels:
        if degree_column is None:
            return set()
        work = work[work[degree_column].astype(str).str.strip().isin(levels)]
    return {str(code).strip() for code in work["Code"] if str(code).strip()}


def _parameters(
    *, selection: SectionSelection, metadata: VectorMetadata | None,
    db_signature: object, main_db_signature: object,
    lineage_context_key: object, values: dict[str, object],
) -> dict[str, object]:
    """Формирует полную подпись входов для экспорта и кэширования."""
    return {
        **values, "section_mode": selection.mode, "section_keys": selection.section_keys,
        "section_weights": selection.weights, "minimum_coverage": selection.min_coverage,
        "section_database_signature": db_signature,
        "main_database_signature": main_db_signature,
        "lineage_context_key": lineage_context_key,
        "model_name": metadata.model_name if metadata else None,
        "normalized": metadata.normalized if metadata else None,
        "matrix_signature": metadata.matrix_signature if metadata else None,
    }


def search_schools_by_semantic_query(
    *, queries: Sequence[str], df: pd.DataFrame, idx: dict,
    lineage_context_key: LineageContextKey, scope: SemanticScope,
    selection: SectionSelection, ranking_config: QueryRankingConfig, top_n: int,
    year_from: int | None, year_to: int | None, degree_levels: Collection[str],
    main_db_signature: object | None = None,
) -> SemanticSchoolQueryResult:
    """Выполняет полный поиск школ по одному–пяти запросам."""
    prepared = prepare_queries(queries, "")
    if not prepared:
        raise ValueError("Введите хотя бы один непустой запрос.")
    db_signature = get_dissertation_sections_db_signature()
    metadata = load_typed_vector_metadata()
    base_values = {
        "queries": tuple(prepared), "scope": scope, "ranking_mode": ranking_config.ranking_mode,
        "relevance_threshold": ranking_config.relevance_threshold,
        "shrinkage_strength": ranking_config.shrinkage_strength,
        "minimum_school_size": ranking_config.minimum_school_size,
        "minimum_profiled_dissertations": ranking_config.minimum_covered_dissertations,
        "top_n": top_n, "year_from": year_from, "year_to": year_to,
        "degree_levels": tuple(sorted(str(value) for value in degree_levels)),
    }
    main_signature = main_db_signature if main_db_signature is not None else lineage_context_key[0]
    parameters = _parameters(selection=selection, metadata=metadata, db_signature=db_signature,
                             main_db_signature=main_signature, lineage_context_key=lineage_context_key, values=base_values)
    if metadata is None:
        return SemanticSchoolQueryResult(pd.DataFrame(), {}, ("Матрица векторов недоступна или имеет неверный формат.",), selection, None, parameters)
    allowed = _filtered_codes(df, year_from, year_to, degree_levels)
    if not allowed:
        return SemanticSchoolQueryResult(pd.DataFrame(), {}, ("После применения фильтров не осталось диссертаций.",), selection, metadata, parameters)
    try:
        with perf_timer("semantic.query.encode"):
            query_vectors = encode_queries(prepared, metadata.model_name, metadata.normalized, get_query_encoder_device())
    except Exception:
        return SemanticSchoolQueryResult(pd.DataFrame(), {}, ("Не удалось загрузить модель кодирования запросов.",), selection, metadata, parameters)
    query = combine_query_vectors(query_vectors)
    try:
        matrix = load_dissertation_embedding_matrix(metadata.matrix_signature)
    except Exception:
        return SemanticSchoolQueryResult(pd.DataFrame(), {}, ("Матрица векторов недоступна или имеет неверный формат.",), selection, metadata, parameters)
    section_index = load_dissertation_section_index_for_selection(
        allowed_codes=allowed, section_keys=selection.section_keys, include_text=False,
    )
    index_reason = section_index.attrs.get("diagnostic_reason")
    if section_index.empty and index_reason in INDEX_DIAGNOSTICS_RU:
        return SemanticSchoolQueryResult(pd.DataFrame(), {}, (INDEX_DIAGNOSTICS_RU[index_reason],), selection, metadata, parameters)
    with perf_timer("semantic.query.score_sections"):
        scores = score_dissertations_against_query(
            query, section_index, matrix, selection, metadata.normalized,
            get_semantic_analysis_limits().batch_size,
        )
    with perf_timer("semantic.query.aggregate_dissertations"):
        scores = scores.copy()
    invalid_count = int(scores.attrs.get("invalid_vector_row_count", 0))
    display_columns = [column for column in (
        "Code", "candidate_name", "title", "year", "degree.degree_level",
        "science_field", "degree.science_field",
    ) if column in df.columns]
    if display_columns:
        metadata_frame = df[display_columns].copy().drop_duplicates("Code", keep="first")
        metadata_frame["Code"] = metadata_frame["Code"].astype(str)
        scores = scores.merge(metadata_frame, on="Code", how="left")
    school_codes = get_all_school_member_codes(df, idx, scope, lineage_context_key[0], context_key=lineage_context_key)
    stats = get_school_basic_stats(df, idx, scope, lineage_context_key[0], context_key=lineage_context_key)
    for root, root_stats in stats.items():
        root_stats["filtered_members"] = len(set(school_codes.get(root, set())) & allowed)
    with perf_timer("semantic.query.aggregate_schools"):
        summary, details = aggregate_query_scores_by_school(scores, school_codes, stats, ranking_config, top_n)
    diagnostics = () if not summary.empty else ("Научные школы с достаточным покрытием не найдены.",)
    if invalid_count:
        diagnostics = (*diagnostics, f"Пропущено недопустимых строк векторной матрицы: {invalid_count}.")
    return SemanticSchoolQueryResult(summary, details, diagnostics, selection, metadata, parameters)


def search_similar_scientific_schools(
    *, source_root: str, df: pd.DataFrame, idx: dict,
    lineage_context_key: LineageContextKey, scope: SemanticScope,
    selection: SectionSelection, minimum_school_size: int,
    minimum_profiled_dissertations: int, top_n: int, hide_near_duplicates: bool,
    near_duplicate_jaccard: float,
    main_db_signature: object | None = None,
) -> SimilarSchoolResult:
    """Ищет школы по сходству отдельных центров характеристик."""
    db_signature = get_dissertation_sections_db_signature()
    metadata = load_typed_vector_metadata()
    values = {
        "source_root": source_root, "scope": scope, "minimum_school_size": minimum_school_size,
        "minimum_profiled_dissertations": minimum_profiled_dissertations, "top_n": top_n,
        "hide_near_duplicates": hide_near_duplicates, "near_duplicate_jaccard": near_duplicate_jaccard,
    }
    main_signature = main_db_signature if main_db_signature is not None else lineage_context_key[0]
    parameters = _parameters(selection=selection, metadata=metadata, db_signature=db_signature,
                             main_db_signature=main_signature, lineage_context_key=lineage_context_key, values=values)
    if metadata is None:
        return SimilarSchoolResult(pd.DataFrame(), {}, ("Матрица векторов недоступна или имеет неверный формат.",), selection, None, parameters)
    codes_by_root = get_all_school_member_codes(df, idx, scope, lineage_context_key[0], context_key=lineage_context_key)
    if source_root not in codes_by_root:
        raise ValueError("Выбранная исходная научная школа не найдена.")
    eligible_roots = [root for root, codes in codes_by_root.items()
                      if root != source_root and len(codes) >= minimum_school_size]
    try:
        matrix = load_dissertation_embedding_matrix(metadata.matrix_signature)
    except Exception:
        return SimilarSchoolResult(pd.DataFrame(), {}, ("Матрица векторов недоступна или имеет неверный формат.",), selection, metadata, parameters)
    source_index = load_dissertation_section_index_for_selection(
        allowed_codes=codes_by_root[source_root], section_keys=selection.section_keys, include_text=False,
    )
    index_reason = source_index.attrs.get("diagnostic_reason")
    if source_index.empty and index_reason in INDEX_DIAGNOSTICS_RU:
        return SimilarSchoolResult(pd.DataFrame(), {}, (INDEX_DIAGNOSTICS_RU[index_reason],), selection, metadata, parameters)
    source_vectors, source_coverage = build_dissertation_section_vectors(
        codes_by_root[source_root], source_index, matrix, selection, metadata.normalized,
    )
    if len(source_vectors) < minimum_profiled_dissertations:
        return SimilarSchoolResult(
            pd.DataFrame(), {}, ("В исходной школе недостаточно диссертаций с требуемым покрытием.",),
            selection, metadata, parameters,
        )
    with perf_timer("semantic.similar.build_source_profile"):
        source_profile = build_school_section_profile(source_vectors, codes_by_root[source_root], selection)
    source_centroids, source_info = source_profile
    batch_size = get_semantic_analysis_limits().school_batch_size
    batches: list[pd.DataFrame] = []
    invalid_vector_row_count = int(source_coverage.attrs.get("invalid_vector_row_count", 0))
    section_explanations: dict[str, pd.DataFrame] = {}
    dissertation_explanations: dict[str, pd.DataFrame] = {}
    for start in range(0, len(eligible_roots), batch_size):
        roots = eligible_roots[start:start + batch_size]
        batch_codes = set().union(*(codes_by_root[root] for root in roots)) if roots else set()
        batch_index = load_dissertation_section_index_for_selection(
            allowed_codes=batch_codes, section_keys=selection.section_keys, include_text=False,
        )
        batch_vectors, batch_coverage = build_dissertation_section_vectors(
            batch_codes, batch_index, matrix, selection, metadata.normalized,
        )
        invalid_vector_row_count += int(batch_coverage.attrs.get("invalid_vector_row_count", 0))

        def builder(root: str, codes: set[str]):
            if root == source_root:
                return source_profile
            profile, info = build_school_section_profile(batch_vectors, codes, selection)
            return profile, info

        profiled_roots = [root for root in roots
                          if sum(code in batch_vectors for code in codes_by_root[root]) >= minimum_profiled_dissertations]
        with perf_timer("semantic.similar.rank_school_batch"):
            part = rank_similar_schools(
                source_root, codes_by_root[source_root], profiled_roots, codes_by_root, builder,
                selection, top_n, hide_near_duplicates, near_duplicate_jaccard,
            )
        if not part.empty:
            batches.append(part)
    summary = pd.concat(batches, ignore_index=True) if batches else pd.DataFrame()
    if not summary.empty:
        summary = summary.sort_values(
            ["semantic_similarity", "common_section_count", "coverage_ratio", "root"],
            ascending=[False, False, False, True], kind="stable",
        ).head(top_n).reset_index(drop=True)
        summary["rank"] = range(1, len(summary) + 1)
    stats = get_school_basic_stats(df, idx, scope, lineage_context_key[0], context_key=lineage_context_key)
    diagnostics: tuple[str, ...] = () if not summary.empty else ("Похожие научные школы с достаточным покрытием не найдены.",)
    if not summary.empty:
        summary["year_range"] = summary["root"].map(lambda root: stats.get(root, {}).get("year_range", "—"))
        final_roots = summary["root"].tolist()
        final_codes = set().union(*(codes_by_root[root] for root in final_roots))
        final_index = load_dissertation_section_index_for_selection(
            allowed_codes=final_codes, section_keys=selection.section_keys, include_text=False,
        )
        final_vectors, final_coverage = build_dissertation_section_vectors(
            final_codes, final_index, matrix, selection, metadata.normalized,
        )
        coverage_map = {str(row.Code): row.coverage for row in final_coverage.itertuples(index=False)}
        metadata_columns = [column for column in ("Code", "candidate_name", "title", "year") if column in df.columns]
        meta = df[metadata_columns].copy().drop_duplicates("Code", keep="first") if metadata_columns else pd.DataFrame()
        if not meta.empty:
            meta["Code"] = meta["Code"].astype(str)
        for candidate in final_roots:
            candidate_profile, candidate_info = build_school_section_profile(final_vectors, codes_by_root[candidate], selection)
            section_explanations[candidate] = pd.DataFrame([{
                "Раздел характеристики": SECTION_LABELS_RU[key],
                "Покрытие исходной школы, %": source_info["section_coverage"].get(key, 0.0) * 100,
                "Покрытие найденной школы, %": candidate_info["section_coverage"].get(key, 0.0) * 100,
                "Сходство центроидов": composite_similarity({key: source_centroids[key]}, {key: candidate_profile[key]}, selection),
            } for key in selection.section_keys if key in source_centroids and key in candidate_profile])
            candidate_codes = sorted(set(codes_by_root[candidate]) & set(final_vectors))
            detail = pd.DataFrame({
                "Code": candidate_codes,
                "distance_to_source": [distance_to_profile(final_vectors[code], source_centroids, selection) for code in candidate_codes],
                "coverage": [coverage_map.get(code, 0.0) for code in candidate_codes],
            })
            candidate_matrix, candidate_diagnostics = composite_distance_matrix(
                [final_vectors[code] for code in candidate_codes], selection, get_semantic_analysis_limits().batch_size,
            )
            medoid = find_medoid(candidate_codes, candidate_matrix)[0] if candidate_codes and candidate_matrix is not None else None
            if candidate_codes and candidate_matrix is None:
                if candidate_diagnostics.reason == "item_limit":
                    diagnostics = (*diagnostics, f"Для школы «{candidate}» не определена репрезентативная работа: превышен предел {candidate_diagnostics.maximum_pairwise_items}.")
                else:
                    diagnostics = (*diagnostics, f"Для школы «{candidate}» не определена репрезентативная работа: отсутствуют общие разделы у части пар.")
            detail["representative"] = detail["Code"].eq(medoid)
            if not meta.empty:
                detail = detail.merge(meta, on="Code", how="left")
            dissertation_explanations[candidate] = detail.sort_values("distance_to_source", na_position="last").reset_index(drop=True)
    if invalid_vector_row_count:
        diagnostics = (*diagnostics, f"Пропущено недопустимых строк векторной матрицы: {invalid_vector_row_count}.")
    returned_roots = set(summary.get("root", pd.Series(dtype=str)))
    return SimilarSchoolResult(
        summary, {root: dissertation_explanations[root] for root in returned_roots if root in dissertation_explanations},
        diagnostics, selection, metadata, parameters,
        {root: section_explanations[root] for root in returned_roots if root in section_explanations},
    )
