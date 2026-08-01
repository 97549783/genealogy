"""Агрегация семантических результатов в профили научных школ."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from math import ceil

import numpy as np
import pandas as pd

from core.semantic.models import QueryRankingConfig, SectionSelection
from core.semantic.section_vectors import composite_similarity
from core.semantic.distances import get_semantic_analysis_limits


def aggregate_query_scores_by_school(
    dissertation_scores: pd.DataFrame,
    school_codes: Mapping[str, set[str]],
    school_stats: Mapping[str, Mapping[str, object]],
    config: QueryRankingConfig,
    top_n: int,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Агрегирует оценки диссертаций с прозрачным сглаживанием."""
    required = {"Code", "semantic_score"}
    if not required.issubset(dissertation_scores.columns):
        raise ValueError("В результатах диссертаций отсутствуют обязательные столбцы.")
    scores = dissertation_scores.copy()
    scores["Code"] = scores["Code"].astype(str)
    scores["semantic_score"] = pd.to_numeric(scores["semantic_score"], errors="coerce")
    scores = scores.dropna(subset=["semantic_score"]).drop_duplicates("Code", keep="first")
    global_mean = float(scores["semantic_score"].mean()) if not scores.empty else 0.0
    strength = max(0.0, float(config.shrinkage_strength))
    rows: list[dict[str, object]] = []
    details: dict[str, pd.DataFrame] = {}
    for root in sorted(school_codes):
        members = {str(code) for code in school_codes[root]}
        total = int(school_stats.get(root, {}).get("n_members", len(members)))
        filtered = int(school_stats.get(root, {}).get("filtered_members", total))
        school = scores[scores["Code"].isin(members)].sort_values(
            ["semantic_score", "Code"], ascending=[False, True], kind="stable"
        )
        n = len(school)
        if total < config.minimum_school_size or filtered <= 0 or n < config.minimum_covered_dissertations:
            continue
        values = school["semantic_score"].to_numpy(dtype=float)
        k = max(1, ceil(0.20 * n))
        top_mean = float(values[:k].mean())
        if config.ranking_mode == "broad":
            base, effective_n = float(values.mean()), n
        elif config.ranking_mode == "focused":
            base, effective_n = top_mean, k
        else:
            raise ValueError("Неизвестная цель семантического ранжирования.")
        ranking = (effective_n * base + strength * global_mean) / (effective_n + strength) if effective_n + strength else base
        rows.append({
            "root": root, "total_members": total, "filtered_members": filtered,
            "covered_dissertations": n, "coverage_ratio": n / filtered,
            "mean_similarity": float(values.mean()), "median_similarity": float(np.median(values)),
            "upper_quartile_similarity": float(np.percentile(values, 75)),
            "top_20_percent_mean": top_mean,
            "share_above_threshold": float(np.mean(values >= config.relevance_threshold)),
            "maximum_similarity": float(values.max()), "ranking_score": float(ranking),
            **{key: value for key, value in school_stats.get(root, {}).items() if key not in {"codes", "n_members"}},
        })
        details[root] = school.head(max(1, int(top_n))).reset_index(drop=True)
    result = pd.DataFrame(rows)
    if result.empty:
        return result, {}
    ties = (["share_above_threshold", "coverage_ratio", "covered_dissertations"]
            if config.ranking_mode == "broad"
            else ["share_above_threshold", "maximum_similarity", "coverage_ratio"])
    result = result.sort_values(
        ["ranking_score", *ties, "root"],
        ascending=[False] * (1 + len(ties)) + [True], kind="stable",
    ).head(max(0, int(top_n))).reset_index(drop=True)
    result["rank"] = np.arange(1, len(result) + 1)
    roots = set(result["root"])
    return result, {root: details[root] for root in result["root"] if root in roots}


def _normalized_mean(vectors: list[np.ndarray]) -> np.ndarray | None:
    """Нормализует среднее конечных ненулевых векторов."""
    valid = [np.asarray(vector, dtype=np.float32) for vector in vectors]
    valid = [vector for vector in valid if vector.ndim == 1 and np.all(np.isfinite(vector)) and np.linalg.norm(vector) > 0]
    if not valid:
        return None
    mean = np.mean(valid, axis=0, dtype=np.float32)
    norm = float(np.linalg.norm(mean))
    return mean / norm if norm > 0 else None


def build_school_section_profile(
    dissertation_vectors: Mapping[str, Mapping[str, np.ndarray]],
    member_codes: Collection[str], selection: SectionSelection,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    """Строит отдельный нормализованный центр для каждого раздела."""
    members = {str(code) for code in member_codes}
    profile: dict[str, np.ndarray] = {}
    counts: dict[str, int] = {}
    coverage: dict[str, float] = {}
    for key in selection.section_keys:
        vectors = [dissertation_vectors[code][key] for code in sorted(members)
                   if code in dissertation_vectors and key in dissertation_vectors[code]]
        centroid = _normalized_mean(vectors)
        counts[key] = len(vectors)
        coverage[key] = len(vectors) / len(members) if members else 0.0
        if centroid is not None:
            profile[key] = centroid.astype(np.float32, copy=False)
    profiled = len(members & set(dissertation_vectors))
    return profile, {
        "total_members": len(members), "profiled_dissertations": profiled,
        "coverage_ratio": profiled / len(members) if members else 0.0,
        "section_counts": counts, "section_coverage": coverage,
    }


def compare_school_profiles(
    source_profile: Mapping[str, np.ndarray], candidate_profile: Mapping[str, np.ndarray],
    selection: SectionSelection,
) -> float | None:
    """Сравнивает профили по общим характеристическим ролям."""
    return composite_similarity(source_profile, candidate_profile, selection)


def jaccard_overlap(left: Collection[str], right: Collection[str]) -> float:
    """Возвращает пересечение Жаккара двух множеств состава."""
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 1.0


def rank_similar_schools(
    source_root: str, source_codes: set[str], candidate_roots: Sequence[str],
    codes_by_root: Mapping[str, set[str]],
    profile_builder: Callable[[str, set[str]], tuple[dict[str, np.ndarray], dict]],
    selection: SectionSelection, top_n: int, hide_near_duplicates: bool,
    near_duplicate_jaccard: float,
) -> pd.DataFrame:
    """Ранжирует школы, исключая источник и при необходимости дубликаты."""
    source_profile, source_info = profile_builder(source_root, source_codes)
    rows = []
    batch_size = get_semantic_analysis_limits().school_batch_size
    roots = list(candidate_roots)
    for start in range(0, len(roots), batch_size):
        for root in roots[start:start + batch_size]:
            if root == source_root or root not in codes_by_root:
                continue
            overlap = jaccard_overlap(source_codes, codes_by_root[root])
            if hide_near_duplicates and overlap >= near_duplicate_jaccard:
                continue
            profile, info = profile_builder(root, codes_by_root[root])
            similarity = compare_school_profiles(source_profile, profile, selection)
            if similarity is None:
                continue
            common = [key for key in selection.section_keys if key in source_profile and key in profile]
            rows.append({
                "root": root, "semantic_similarity": similarity,
                "common_section_count": len(common), "common_section_keys": tuple(common),
                "jaccard_overlap": overlap, "source_coverage_ratio": source_info.get("coverage_ratio", 0.0),
                **info,
            })
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = result.sort_values(
        ["semantic_similarity", "common_section_count", "coverage_ratio", "root"],
        ascending=[False, False, False, True], kind="stable",
    ).head(max(0, int(top_n))).reset_index(drop=True)
    result["rank"] = np.arange(1, len(result) + 1)
    return result
