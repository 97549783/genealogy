from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest

from tabs.intersection.tab import compute_intersection_analysis


def test_compute_intersection_analysis_directionality_basic_case() -> None:
    school_data = {
        "A": ({"a", "x"}, {"b"}),
        "B": ({"b"}, {"x"}),
    }

    raw_df, jaccard_df, m_share_df, o_share_df, stats_df, persons_df = compute_intersection_analysis(school_data)

    assert raw_df.loc["A", "B"] == 1
    assert raw_df.loc["B", "A"] == 1
    assert jaccard_df.loc["A", "B"] == 0.5
    assert m_share_df.loc["A", "B"] == 0.5
    assert o_share_df.loc["A", "B"] == 1.0
    assert not stats_df.empty
    assert set(persons_df["Имя"]) == {"b", "x"}


def test_intersection_tab_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.intersection.tab as intersection_tab


def _fake_collect_members(df, idx, root, scope):
    return ({root.lower()}, pd.DataFrame([{"opponents_1.name": "Оппонент"}]))


def _fake_collect_opponents(subset):
    return {"оппонент"}


def _fake_compute(school_data):
    names = sorted(school_data.keys())
    matrix = pd.DataFrame(0, index=names, columns=names)
    stats = pd.DataFrame([{"Научная школа": n, "Членов в школе": 1, "Оппонентов привлечено": 1} for n in names])
    persons = pd.DataFrame(columns=["Школа, к которой принадлежит человек", "Школа, где он выступал оппонентом", "Имя"])
    return matrix, matrix.copy(), matrix.copy(), matrix.copy(), stats, persons


def _fake_render_widget(**kwargs):
    st.session_state["_intersection_widget_key"] = kwargs["key"]


def _fake_share(payload, key):
    st.session_state["_intersection_share_payload"] = payload
    st.session_state["_intersection_share_key"] = key


intersection_tab._collect_members = _fake_collect_members
intersection_tab._collect_opponents = _fake_collect_opponents
intersection_tab.compute_intersection_analysis = _fake_compute
intersection_tab.render_dissertations_widget = _fake_render_widget
intersection_tab.share_params_button = _fake_share

sample_df = pd.DataFrame([
    {"supervisors_1.name": "Иванов И.И.", "supervisors_2.name": "Петров П.П."},
    {"supervisors_1.name": "Петров П.П.", "supervisors_2.name": ""},
])

intersection_tab.render_opponents_intersection_tab(sample_df, idx={})
"""
    )

    app.query_params["schools"] = ["Иванов И.И.", "Петров П.П."]
    app.query_params["scope"] = "all"

    app.run()

    assert app.session_state["opponents_intersection_query_hydrated"] is True
    assert app.session_state["opponents_intersection_schools"] == ["Иванов И.И.", "Петров П.П."]
    assert app.session_state["opponents_intersection_run_state"] is True
    assert app.session_state["_intersection_share_key"] == "opponents_intersection_share"
    assert app.session_state["_intersection_share_payload"] == {
        "tab": "intersection",
        "schools": ["Иванов И.И.", "Петров П.П."],
        "scope": "all",
    }
