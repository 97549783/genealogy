"""Проверки агрегации, покрытия и расстояний между разделами."""

import numpy as np
import pandas as pd

from core.semantic.models import build_section_selection
from core.semantic.section_vectors import (
    aggregate_duplicate_section_vectors,
    composite_distance_matrix,
    composite_similarity,
    score_dissertations_against_query,
)


def _index() -> pd.DataFrame:
    return pd.DataFrame({
        "text_id": ["a", "b", "c", "bad"], "Code": ["A", "A", "A", "B"],
        "section_key": ["research_goal", "research_goal", "research_methods", "research_goal"],
        "matrix_row": [0, 1, 2, 99],
    })


def test_duplicate_vectors_are_averaged_and_normalized() -> None:
    matrix = np.array([[2, 0], [0, 2], [0, 3]], dtype=np.float32)
    vectors = aggregate_duplicate_section_vectors(matrix, _index(), normalized=False)
    assert np.allclose(vectors["A"]["research_goal"], [2 ** -0.5, 2 ** -0.5])


def test_query_scoring_uses_weighted_coverage_and_best_duplicate() -> None:
    matrix = np.array([[1, 0], [0.8, 0.6], [0, 1]], dtype=np.float32)
    selection = build_section_selection(
        "selected", ["research_goal", "research_methods"],
        {"research_goal": 3, "research_methods": 1}, min_coverage=1,
    )
    result = score_dissertations_against_query([1, 0], _index(), matrix, selection, True, 1)
    assert result.loc[0, "coverage"] == 1
    assert result.loc[0, "best_text_id"] == "a"
    assert np.isclose(result.loc[0, "semantic_score"], 0.75)


def test_no_common_section_makes_pairwise_distance_undefined() -> None:
    selection = build_section_selection("selected", ["research_goal", "research_methods"])
    left, right = {"research_goal": np.array([1, 0])}, {"research_methods": np.array([1, 0])}
    assert composite_similarity(left, right, selection) is None
    matrix, diagnostics = composite_distance_matrix([left, right], selection, 1)
    assert matrix is None
    assert diagnostics.undefined_pair_count == 1
    assert diagnostics.reason == "undefined_pairs"


def test_pairwise_limit_has_explicit_reason(monkeypatch) -> None:
    monkeypatch.setenv("SEMANTIC_MAX_PAIRWISE_ITEMS", "1")
    selection = build_section_selection("selected", ["research_goal"])
    matrix, diagnostics = composite_distance_matrix([
        {"research_goal": np.array([1, 0])}, {"research_goal": np.array([0, 1])},
    ], selection, 1)
    assert matrix is None
    assert diagnostics.reason == "item_limit"
    assert diagnostics.maximum_pairwise_items == 1


def test_block_pairwise_matches_scalar_reference() -> None:
    selection = build_section_selection(
        "selected", ["research_goal", "research_methods"],
        {"research_goal": 2, "research_methods": 1},
    )
    items = [
        {"research_goal": np.array([1, 0]), "research_methods": np.array([0, 1])},
        {"research_goal": np.array([1, 1]), "research_methods": np.array([1, 0])},
    ]
    matrix, diagnostics = composite_distance_matrix(items, selection, 1)
    expected = 1 - composite_similarity(items[0], items[1], selection)
    assert diagnostics.reason == "ok"
    assert np.isclose(matrix[0, 1], expected)
