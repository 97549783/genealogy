"""Проверки семантических профилей научных школ."""

import numpy as np
import pandas as pd

from core.semantic.models import QueryRankingConfig, build_section_selection
from core.semantic.school_profiles import (
    aggregate_query_scores_by_school, build_school_section_profile,
    jaccard_overlap, rank_similar_schools,
)


def test_broad_and_focused_ranking_use_explicit_shrinkage() -> None:
    scores = pd.DataFrame({"Code": ["1", "2", "3"], "semantic_score": [1.0, 0.0, 0.6]})
    schools = {"Широкая": {"1", "2"}, "Узкая": {"3"}}
    stats = {root: {"n_members": len(codes)} for root, codes in schools.items()}
    broad = QueryRankingConfig("broad", 0.5, 5.0, 1, 1)
    focused = QueryRankingConfig("focused", 0.5, 5.0, 1, 1)
    broad_result, _ = aggregate_query_scores_by_school(scores, schools, stats, broad, 10)
    focused_result, _ = aggregate_query_scores_by_school(scores, schools, stats, focused, 10)
    assert broad_result.iloc[0]["root"] == "Узкая"
    assert focused_result.iloc[0]["root"] == "Широкая"


def test_profile_keeps_section_centroids_separate() -> None:
    selection = build_section_selection("selected", ["research_goal", "research_methods"])
    vectors = {
        "1": {"research_goal": np.array([1, 0]), "research_methods": np.array([0, 1])},
        "2": {"research_goal": np.array([0, 1])},
    }
    profile, info = build_school_section_profile(vectors, {"1", "2"}, selection)
    assert np.allclose(profile["research_goal"], [2 ** -0.5, 2 ** -0.5])
    assert np.array_equal(profile["research_methods"], [0, 1])
    assert info["section_counts"] == {"research_goal": 2, "research_methods": 1}


def test_similar_ranking_excludes_source_and_hides_duplicate() -> None:
    selection = build_section_selection("selected", ["research_goal"])
    codes = {"Источник": {"1", "2"}, "Дубликат": {"1", "2"}, "Кандидат": {"3"}}

    def builder(root, member_codes):
        return {"research_goal": np.array([1.0, 0.0])}, {"coverage_ratio": 1.0, "profiled_dissertations": len(member_codes)}

    result = rank_similar_schools("Источник", codes["Источник"], list(codes), codes, builder,
                                  selection, 10, True, 0.8)
    assert result["root"].tolist() == ["Кандидат"]
    assert jaccard_overlap({"1", "2"}, {"2", "3"}) == 1 / 3
