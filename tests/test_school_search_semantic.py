"""Проверки чистой оркестрации семантического поиска школ."""

from io import BytesIO

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from core.semantic.models import QueryRankingConfig, VectorMetadata, build_section_selection
import tabs.school_search.semantic as semantic
from tabs.school_search.exports import build_semantic_query_search_excel


def _patch_resources(monkeypatch, index: pd.DataFrame, matrix: np.ndarray) -> None:
    metadata = VectorMetadata("модель", True, matrix.shape[1], ("матрица.npy", 1.0, 1))
    monkeypatch.setattr(semantic, "load_typed_vector_metadata_with_diagnostic", lambda: (metadata, "ok"))
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


def test_unavailable_section_database_has_specific_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(semantic, "load_typed_vector_metadata_with_diagnostic", lambda: (None, "section_database_unavailable"))
    result = semantic.search_schools_by_semantic_query(
        queries=["запрос"], df=pd.DataFrame(), idx={}, lineage_context_key=(("основа", 1.0, 1), (), ()),
        scope="all", selection=build_section_selection("selected", ["research_goal"]),
        ranking_config=QueryRankingConfig("broad", .5, 5, 1, 1), top_n=5,
        year_from=None, year_to=None, degree_levels=set(),
    )
    assert result.diagnostics == ("База разделов диссертаций недоступна.",)


def test_missing_similar_source_returns_result_diagnostic(monkeypatch) -> None:
    matrix = np.array([[1, 0]], dtype=np.float32)
    index = pd.DataFrame({"Code": ["1"], "section_key": ["research_goal"], "matrix_row": [0]})
    _patch_resources(monkeypatch, index, matrix)
    monkeypatch.setattr(semantic, "get_all_school_member_codes", lambda *args, **kwargs: {})
    result = semantic.search_similar_scientific_schools(
        source_root="", df=pd.DataFrame(), idx={}, lineage_context_key=(("основа", 1.0, 1), (), ()),
        scope="all", selection=build_section_selection("selected", ["research_goal"]),
        minimum_school_size=1, minimum_profiled_dissertations=1, top_n=5,
        hide_near_duplicates=False, near_duplicate_jaccard=.8,
    )
    assert result.diagnostics == ("Выбранная исходная научная школа не найдена.",)


def test_query_export_contains_normalized_weighted_contributions() -> None:
    selection = build_section_selection(
        "selected", ["research_goal", "research_methods"],
        {"research_goal": 2.0, "research_methods": 1.0}, min_coverage=1,
    )
    details = pd.DataFrame([{
        "candidate_name": "Автор", "title": "Название", "year": 2020,
        "coverage": 1.0, "section_scores": {"research_goal": .8, "research_methods": 1.0},
        "section_contributions": {"research_goal": 1.6 / 3, "research_methods": 1 / 3},
    }])
    result = semantic.SemanticSchoolQueryResult(
        pd.DataFrame(), {"Школа": details}, (), selection, None, {},
    )
    workbook = load_workbook(BytesIO(build_semantic_query_search_excel(result)), data_only=True)
    rows = list(workbook["Вклады разделов"].values)
    assert rows[0][-3:] == ("Вес раздела", "Сходство", "Взвешенный вклад")
    assert np.isclose(rows[1][-1], 1.6 / 3)
    assert np.isclose(rows[2][-1], 1 / 3)
