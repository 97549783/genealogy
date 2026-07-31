"""Чистая оркестрация семантического поиска научных школ."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

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
from tabs.dissertation_characteristics.search import load_dissertation_embedding_matrix


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
    db_signature: object, values: dict[str, object],
) -> dict[str, object]:
    """Формирует полную подпись входов для экспорта и кэширования."""
    return {
        **values, "section_mode": selection.mode, "section_keys": selection.section_keys,
        "section_weights": selection.weights, "minimum_coverage": selection.min_coverage,
        "section_database_signature": db_signature,
        "model_name": metadata.model_name if metadata else None,
        "normalized": metadata.normalized if metadata else None,
        "matrix_signature": metadata.matrix_signature if metadata else None,
    }


def search_schools_by_semantic_query(
    *, queries: Sequence[str], df: pd.DataFrame, idx: dict,
    lineage_context_key: LineageContextKey, scope: SemanticScope,
    selection: SectionSelection, ranking_config: QueryRankingConfig, top_n: int,
    year_from: int | None, year_to: int | None, degree_levels: Collection[str],
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
    parameters = _parameters(selection=selection, metadata=metadata, db_signature=db_signature, values=base_values)
    if metadata is None:
        return SemanticSchoolQueryResult(pd.DataFrame(), {}, ("Матрица векторов недоступна или имеет неверный формат.",), selection, None, parameters)
    allowed = _filtered_codes(df, year_from, year_to, degree_levels)
    if not allowed:
        return SemanticSchoolQueryResult(pd.DataFrame(), {}, ("После применения фильтров не осталось диссертаций.",), selection, metadata, parameters)
    try:
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
    scores = score_dissertations_against_query(
        query, section_index, matrix, selection, metadata.normalized,
        get_semantic_analysis_limits().batch_size,
    )
    school_codes = get_all_school_member_codes(df, idx, scope, lineage_context_key[0], context_key=lineage_context_key)
    stats = get_school_basic_stats(df, idx, scope, lineage_context_key[0], context_key=lineage_context_key)
    summary, details = aggregate_query_scores_by_school(scores, school_codes, stats, ranking_config, top_n)
    diagnostics = () if not summary.empty else ("Научные школы с достаточным покрытием не найдены.",)
    return SemanticSchoolQueryResult(summary, details, diagnostics, selection, metadata, parameters)


def search_similar_scientific_schools(
    *, source_root: str, df: pd.DataFrame, idx: dict,
    lineage_context_key: LineageContextKey, scope: SemanticScope,
    selection: SectionSelection, minimum_school_size: int,
    minimum_profiled_dissertations: int, top_n: int, hide_near_duplicates: bool,
    near_duplicate_jaccard: float,
) -> SimilarSchoolResult:
    """Ищет школы по сходству отдельных центров характеристик."""
    db_signature = get_dissertation_sections_db_signature()
    metadata = load_typed_vector_metadata()
    values = {
        "source_root": source_root, "scope": scope, "minimum_school_size": minimum_school_size,
        "minimum_profiled_dissertations": minimum_profiled_dissertations, "top_n": top_n,
        "hide_near_duplicates": hide_near_duplicates, "near_duplicate_jaccard": near_duplicate_jaccard,
    }
    parameters = _parameters(selection=selection, metadata=metadata, db_signature=db_signature, values=values)
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
    source_vectors, _ = build_dissertation_section_vectors(
        codes_by_root[source_root], source_index, matrix, selection, metadata.normalized,
    )
    if len(source_vectors) < minimum_profiled_dissertations:
        return SimilarSchoolResult(
            pd.DataFrame(), {}, ("В исходной школе недостаточно диссертаций с требуемым покрытием.",),
            selection, metadata, parameters,
        )
    source_profile = build_school_section_profile(source_vectors, codes_by_root[source_root], selection)
    batch_size = get_semantic_analysis_limits().school_batch_size
    batches: list[pd.DataFrame] = []
    for start in range(0, len(eligible_roots), batch_size):
        roots = eligible_roots[start:start + batch_size]
        batch_codes = set().union(*(codes_by_root[root] for root in roots)) if roots else set()
        batch_index = load_dissertation_section_index_for_selection(
            allowed_codes=batch_codes, section_keys=selection.section_keys, include_text=False,
        )
        batch_vectors, _ = build_dissertation_section_vectors(
            batch_codes, batch_index, matrix, selection, metadata.normalized,
        )

        def builder(root: str, codes: set[str]):
            if root == source_root:
                return source_profile
            profile, info = build_school_section_profile(batch_vectors, codes, selection)
            return profile, info

        profiled_roots = [root for root in roots
                          if sum(code in batch_vectors for code in codes_by_root[root]) >= minimum_profiled_dissertations]
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
    if not summary.empty:
        summary["year_range"] = summary["root"].map(lambda root: stats.get(root, {}).get("year_range", "—"))
    diagnostics = () if not summary.empty else ("Похожие научные школы с достаточным покрытием не найдены.",)
    return SimilarSchoolResult(summary, {}, diagnostics, selection, metadata, parameters)
