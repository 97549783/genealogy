from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_school_analysis_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.school_analysis.tab as analysis_tab


def _fake_collect_school_subset(df, idx, root, scope, lineage_func, rows_for_func):
    return pd.DataFrame([
        {"candidate_name": "Кандидат", "year": 2020, "city": "Москва", "degree.degree_level": "кандидат"}
    ])


def _fake_compute_overview(**kwargs):
    return {
        "total": 1,
        "candidates": 1,
        "doctors": 0,
        "cities": 1,
        "year_min": 2020,
        "year_max": 2020,
        "generations": 1,
    }


def _fake_compute_metrics(**kwargs):
    return (
        pd.DataFrame([{"Метрика": "Число прямых учеников", "Значение": 1}]),
        pd.DataFrame([{"Поколение": 1, "Число учеников": 1}]),
    )


def _fake_compute_yearly_stats(subset):
    return pd.DataFrame([{"Год": 2020, "Кандидатских": 1, "Докторских": 0, "Всего": 1}])


def _fake_compute_city_stats(subset):
    return pd.DataFrame([{"Город": "Москва", "Число защит": 1}])


def _fake_compute_institutional_stats(subset):
    return {"institution_prepared": pd.DataFrame(), "defense_location": pd.DataFrame(), "leading_organization": pd.DataFrame(), "specialties": pd.DataFrame()}


def _fake_compute_top_opponents(subset, top_n=5):
    return pd.DataFrame([{"Оппонент": "Оппонент", "Число защит": 1}])


def _fake_compute_continuity(**kwargs):
    return pd.DataFrame([{"Ученик": "Кандидат", "Число учеников в базе": 1}])


def _fake_build_excel_report(**kwargs):
    return b"excel"


def _fake_share(payload, key):
    st.session_state["_school_analysis_share_payload"] = payload
    st.session_state["_school_analysis_share_key"] = key


analysis_tab.collect_school_subset = _fake_collect_school_subset
analysis_tab.compute_overview = _fake_compute_overview
analysis_tab.compute_metrics = _fake_compute_metrics
analysis_tab.compute_yearly_stats = _fake_compute_yearly_stats
analysis_tab.compute_city_stats = _fake_compute_city_stats
analysis_tab.compute_institutional_stats = _fake_compute_institutional_stats
analysis_tab.compute_top_opponents = _fake_compute_top_opponents
analysis_tab.compute_continuity = _fake_compute_continuity
analysis_tab.build_excel_report = _fake_build_excel_report
analysis_tab._scores_folder_available = lambda _: False
analysis_tab.share_params_button = _fake_share

sample_df = pd.DataFrame([
    {
        "candidate_name": "Кандидат",
        "supervisors_1.name": "Иванов И.И.",
        "year": 2020,
        "city": "Москва",
        "degree.degree_level": "кандидат",
    }
])

analysis_tab.render_school_analysis_tab(sample_df, idx={})
"""
    )

    app.query_params["analysis_root"] = "Иванов И.И."
    app.query_params["analysis_scope"] = "all"

    app.run()

    assert app.session_state["school_analysis_query_hydrated"] is True
    assert app.session_state["school_analysis_root"] == "Иванов И.И."
    assert app.session_state["school_analysis_run_state"] is True
    assert app.session_state["_school_analysis_share_key"] == "school_analysis_share"
    assert app.session_state["_school_analysis_share_payload"] == {
        "tab": "school_analysis",
        "analysis_root": "Иванов И.И.",
        "analysis_scope": "all",
    }
