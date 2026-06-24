from __future__ import annotations

import numpy as np
import pandas as pd

from tabs.dissertation_characteristics.search import filter_targets_for_similar_search, search_similar_dissertation_sections
from tabs.dissertation_characteristics.query_search import search_dissertation_sections_by_query_vector


def _index():
    return pd.DataFrame({
        "Code": ["A", "B", "C"],
        "section_key": ["research_goal", "research_goal", "research_methods"],
        "matrix_row": [0, 1, 2],
        "text": ["a", "b", "c"],
    })


def test_similar_search_excludes_source_dissertation_and_same_type():
    targets = filter_targets_for_similar_search(_index(), "A", ["research_goal"])
    assert targets["Code"].tolist() == ["B"]
    assert targets["section_key"].unique().tolist() == ["research_goal"]


def test_cross_type_allows_selected_multiple_section_keys():
    targets = filter_targets_for_similar_search(_index(), "A", ["research_goal", "research_methods"])
    assert targets["Code"].tolist() == ["B", "C"]


def test_batched_search_returns_expected_top_n():
    matrix = np.array([[1, 0], [0.9, 0.1], [0, 1]], dtype=np.float32)
    out = search_similar_dissertation_sections(0, matrix, _index().iloc[1:], top_n=1, batch_size=1, normalized=True)
    assert out.iloc[0]["Code"] == "B"
    assert out.iloc[0]["rank"] == 1


def test_query_vector_search_returns_contributions():
    matrix = np.array([[1, 0], [0, 1], [0.7, 0.7]], dtype=np.float32)
    queries = np.array([[1, 0], [0, 1]], dtype=np.float32)
    out = search_dissertation_sections_by_query_vector(queries, matrix, _index(), top_n=2, batch_size=1, normalized=True)
    assert len(out) == 2
    assert "query_similarity_1" in out.columns
    assert "query_weight_2" in out.columns
