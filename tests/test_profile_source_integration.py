from __future__ import annotations

import pandas as pd


def _scores_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"Code": "A", "1": 2.0, "2.4.2.3": 7.0},
    ])


def test_profiles_load_dissertation_profile_scores_accepts_profile_source(monkeypatch):
    from tabs.profiles import search

    captured = {}

    def _fake_load(profile_source_id="pedagogy_5_8"):
        captured["profile_source_id"] = profile_source_id
        return _scores_df()

    monkeypatch.setattr(search, "load_dissertation_scores", _fake_load)

    df = search.load_dissertation_profile_scores(profile_source_id="it_2_3")
    assert captured["profile_source_id"] == "it_2_3"
    assert "Code" in df.columns


def test_load_basic_scores_alias_matches_new_loader(monkeypatch):
    from tabs.profiles import search

    captured = {}

    def _fake_load(profile_source_id="pedagogy_5_8"):
        captured["profile_source_id"] = profile_source_id
        return _scores_df()

    monkeypatch.setattr(search, "load_dissertation_scores", _fake_load)

    df = search.load_basic_scores(profile_source_id="it_2_3")
    assert captured["profile_source_id"] == "it_2_3"
    assert "Code" in df.columns


def test_entropy_loader_accepts_profile_source(monkeypatch):
    from tabs.profiles import entropy_mode

    captured = {}

    def _fake_load(profile_source_id="pedagogy_5_8"):
        captured["profile_source_id"] = profile_source_id
        return _scores_df()

    monkeypatch.setattr(entropy_mode, "load_dissertation_scores_core", _fake_load)

    df = entropy_mode.load_scores_from_db(profile_source_id="it_2_3")
    assert captured["profile_source_id"] == "it_2_3"
    assert "Code" in df.columns


def test_school_comparison_loader_accepts_profile_source(monkeypatch):
    from tabs.school_comparison import comparison

    captured = {}

    def _fake_load(profile_source_id="pedagogy_5_8"):
        captured["profile_source_id"] = profile_source_id
        return _scores_df()

    monkeypatch.setattr(comparison, "load_dissertation_scores_core", _fake_load)

    df = comparison.load_scores_from_db(profile_source_id="it_2_3")
    assert captured["profile_source_id"] == "it_2_3"
    assert "Code" in df.columns


def test_school_search_classifier_score_accepts_profile_source(monkeypatch):
    from tabs.school_search import search as school_search

    captured = {}
    key = (("db", 1.0, 1), (), ("supervisors_1.name", "supervisors_2.name"))
    monkeypatch.setattr(
        school_search,
        "get_all_school_member_codes",
        lambda *args, **kwargs: {"Root": {"A"}},
    )
    monkeypatch.setattr(
        school_search,
        "get_school_basic_stats",
        lambda *args, **kwargs: {
            "Root": {"n_members": 1, "year_range": "2020–2020", "n_cities": 1}
        },
    )

    def _fake_fetch(codes, classifier_node, profile_source_id="pedagogy_5_8"):
        captured["profile_source_id"] = profile_source_id
        return pd.DataFrame([{"Code": "A", "node_score": 7.0}])

    monkeypatch.setattr(school_search, "fetch_dissertation_node_score_by_codes", _fake_fetch)

    result = school_search.search_by_classifier_score(
        df=pd.DataFrame([{"Code": "A"}]),
        index={},
        lineage_func=None,
        rows_for_func=None,
        classifier_node="2.4",
        profile_source_id="it_2_3",
        lineage_context_key=key,
    )

    assert captured["profile_source_id"] == "it_2_3"
    assert result.iloc[0]["Средний балл (2.4)"] == 7.0


def test_school_analysis_thematic_profile_accepts_profile_source(monkeypatch):
    from core.classifier import get_classifier_by_profile_source
    from core.domain.profile_sources import get_profile_summary_groups
    from tabs.school_analysis import analysis

    captured = {}

    def _fake_load(profile_source_id="pedagogy_5_8"):
        captured["profile_source_id"] = profile_source_id
        return pd.DataFrame([
            {"Code": "A", "1": 2.0, "1.1": 3.0, "2": 4.0, "2.4": 5.0, "3": 6.0, "3.1": 7.0},
        ])

    monkeypatch.setattr(analysis, "load_dissertation_scores", _fake_load)

    result = analysis.compute_thematic_profile(
        subset=pd.DataFrame([{"Code": "A"}]),
        classifier=get_classifier_by_profile_source("it_2_3"),
        profile_source_id="it_2_3",
        groups=get_profile_summary_groups("it_2_3"),
        min_avg=0.0,
    )

    assert captured["profile_source_id"] == "it_2_3"
    assert list(result) == [
        "1. Объект исследования и предметная область",
        "2. Методы, технологии и процессы",
        "3. Результаты и целевые характеристики",
    ]
    assert all(list(df.columns) == ["Название", "Средний балл"] for df in result.values())
