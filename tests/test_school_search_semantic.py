"""Проверки чистой оркестрации семантического поиска школ."""

import numpy as np
import pandas as pd

from core.semantic.models import QueryRankingConfig, VectorMetadata, build_section_selection
import tabs.school_search.semantic as semantic


def _patch_resources(monkeypatch, index: pd.DataFrame, matrix: np.ndarray) -> None:
    metadata = VectorMetadata("модель", True, matrix.shape[1], ("матрица.npy", 1.0, 1))
    monkeypatch.setattr(semantic, "load_typed_vector_metadata", lambda: metadata)
    monkeypatch.setattr(semantic, "get_dissertation_sections_db_signature", lambda: ("разделы", 1.0, 1))
    monkeypatch.setattr(semantic, "load_dissertation_embedding_matrix", lambda signature: matrix)
    monkeypatch.setattr(semantic, "load_dissertation_section_index_for_selection", lambda **kwargs: index[index["Code"].isin(kwargs["allowed_codes"])].copy())
    monkeypatch.setattr(semantic, "encode_queries", lambda *args, **kwargs: np.array([[1.0, 0.0]], dtype=np.float32))


def test_query_filters_metadata_and_uses_filtered_denominator(monkeypatch) -> None:
    matrix = np.array([[1, 0], [.8, .2]], dtype=np.float32)
    index = pd.DataFrame({"Code": ["1", "2"], "section_key": ["research_goal"] * 2,
                          "matrix_row": [0, 1], "text_id": ["t1", "t2"]})
    _patch_resources(monkeypatch, index, matrix)
    schools = {"Руководитель": {"1", "2", "3"}}
    monkeypatch.setattr(semantic, "get_all_school_member_codes", lambda *args, **kwargs: schools)
    monkeypatch.setattr(semantic, "get_school_basic_stats", lambda *args, **kwargs: {
        "Руководитель": {"n_members": 3, "year_range": "2020–2022"},
    })
    df = pd.DataFrame({"Code": ["1", "2", "3"], "candidate_name": ["А", "Б", "В"],
                       "title": ["Тема А", "Тема Б", "Тема В"], "year": [2020, 2022, 2010],
                       "degree.degree_level": ["кандидат"] * 3})
    result = semantic.search_schools_by_semantic_query(
        queries=["запрос"], df=df, idx={}, lineage_context_key=(("основа", 1.0, 1), (), ()),
        scope="all", selection=build_section_selection("selected", ["research_goal"]),
        ranking_config=QueryRankingConfig("broad", .5, 5, 1, 1), top_n=5,
        year_from=2020, year_to=None, degree_levels={"кандидат"}, main_db_signature=("основа", 1.0, 1),
    )
    row = result.summary.iloc[0]
    assert row["total_members"] == 3
    assert row["filtered_members"] == 2
    assert row["coverage_ratio"] == 1
    assert result.dissertation_details["Руководитель"].iloc[0]["candidate_name"] == "А"
    assert result.parameters["main_database_signature"] == ("основа", 1.0, 1)
    assert "lineage_context_key" in result.parameters


def test_similar_search_returns_section_and_dissertation_explanations(monkeypatch) -> None:
    matrix = np.array([[1, 0], [.9, .1], [0, 1], [.1, .9]], dtype=np.float32)
    index = pd.DataFrame({"Code": ["1", "2", "3", "4"], "section_key": ["research_goal"] * 4,
                          "matrix_row": range(4), "text_id": [f"t{x}" for x in range(4)]})
    _patch_resources(monkeypatch, index, matrix)
    schools = {"Источник": {"1", "2"}, "Кандидат": {"3", "4"}}
    monkeypatch.setattr(semantic, "get_all_school_member_codes", lambda *args, **kwargs: schools)
    monkeypatch.setattr(semantic, "get_school_basic_stats", lambda *args, **kwargs: {
        "Источник": {"year_range": "2020"}, "Кандидат": {"year_range": "2021"},
    })
    df = pd.DataFrame({"Code": list("1234"), "candidate_name": list("АБВГ"), "title": ["Тема"] * 4, "year": [2020] * 4})
    result = semantic.search_similar_scientific_schools(
        source_root="Источник", df=df, idx={}, lineage_context_key=(("основа", 1.0, 1), (), ()),
        scope="all", selection=build_section_selection("selected", ["research_goal"]),
        minimum_school_size=1, minimum_profiled_dissertations=1, top_n=5,
        hide_near_duplicates=False, near_duplicate_jaccard=.8,
    )
    assert result.summary["root"].tolist() == ["Кандидат"]
    assert result.section_similarities["Кандидат"]["Раздел характеристики"].tolist() == ["Цель исследования"]
    assert result.dissertation_details["Кандидат"]["representative"].sum() == 1
