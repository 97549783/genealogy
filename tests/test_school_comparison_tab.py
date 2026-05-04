from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest

from tabs.school_comparison.comparison import filter_columns_by_nodes


def test_school_comparison_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import tabs.school_comparison.tab as comp_tab


def _fake_load_scores_from_db(**kwargs):
    return pd.DataFrame([
        {"Code": "C1", "1": 0.4, "1.1": 0.2, "2": 0.1},
        {"Code": "C2", "1": 0.6, "1.1": 0.5, "2": 0.3},
    ])


def _fake_get_feature_columns(scores_df):
    return ["1", "1.1", "2"]


def _fake_get_selectable_nodes(columns, max_level=3):
    return ["1", "1.1", "2"]


def _fake_filter_columns_by_nodes(columns, selected_nodes=None):
    if not selected_nodes:
        return columns
    return [c for c in columns if any(c == n or c.startswith(f"{n}.") for n in selected_nodes)]


def _fake_gather_school_dataset(**kwargs):
    root = kwargs["root"]
    df = pd.DataFrame([
        {"Code": f"{root}-1", "1": 0.4, "1.1": 0.2, "2": 0.1, "school": root, "candidate_name": "A"},
        {"Code": f"{root}-2", "1": 0.6, "1.1": 0.5, "2": 0.3, "school": root, "candidate_name": "B"},
    ])
    return df, pd.DataFrame(columns=["Code", "school", "candidate_name"]), 2


def _fake_compute_silhouette_analysis(**kwargs):
    school_order = sorted(kwargs["datasets"].keys())
    labels = np.array([school_order[0], school_order[0], school_order[1], school_order[1]])
    sample_scores = np.array([0.3, 0.4, 0.5, 0.6])
    used_columns = _fake_filter_columns_by_nodes(kwargs["feature_columns"], kwargs.get("selected_nodes"))
    return 0.45, sample_scores, labels, school_order, used_columns


def _fake_create_node_scores_table(**kwargs):
    schools = kwargs["school_order"]
    return pd.DataFrame({"Узел": ["1"], "Раздел": ["Раздел 1"], schools[0]: [0.5], schools[1]: [0.4]})


def _fake_create_comparison_summary(**kwargs):
    schools = kwargs["school_order"]
    return pd.DataFrame({"Школа": schools, "Профилей": [2, 2]})


def _fake_create_silhouette_plot(**kwargs):
    fig, _ = plt.subplots()
    return fig


def _fake_interpret(score):
    return "ok"


def _fake_download_data_dialog(*args, **kwargs):
    return None


def _fake_share(payload, key):
    st.session_state["_school_comp_share_payload"] = payload
    st.session_state["_school_comp_share_key"] = key


comp_tab.load_scores_from_db = _fake_load_scores_from_db
comp_tab.get_feature_columns = _fake_get_feature_columns
comp_tab.get_selectable_nodes = _fake_get_selectable_nodes
comp_tab.filter_columns_by_nodes = _fake_filter_columns_by_nodes
comp_tab.gather_school_dataset = _fake_gather_school_dataset
comp_tab.compute_silhouette_analysis = _fake_compute_silhouette_analysis
comp_tab.create_node_scores_table = _fake_create_node_scores_table
comp_tab.create_comparison_summary = _fake_create_comparison_summary
comp_tab.create_silhouette_plot = _fake_create_silhouette_plot
comp_tab.interpret_silhouette_score = _fake_interpret
comp_tab.download_data_dialog = _fake_download_data_dialog
comp_tab.share_params_button = _fake_share

sample_df = pd.DataFrame([
    {"supervisors_1.name": "Иванов И.И.", "supervisors_2.name": ""},
    {"supervisors_1.name": "Петров П.П.", "supervisors_2.name": ""},
])

comp_tab.render_school_comparison_tab(sample_df, idx={})
"""
    )

    app.query_params["school_comp_schools"] = ["Иванов И.И.", "Петров П.П."]
    app.query_params["school_comp_scope"] = "all"
    app.query_params["school_comp_metric"] = "euclidean_oblique"
    app.query_params["school_comp_basis"] = "selected"
    app.query_params["school_comp_nodes"] = ["1"]
    app.query_params["school_comp_decay"] = "0.5"

    app.run()

    assert app.session_state["school_comp_query_hydrated"] is True
    assert app.session_state["school_comp_selection"] == ["Иванов И.И.", "Петров П.П."]
    assert app.session_state["school_comp_results"] is not None
    assert app.session_state["_school_comp_share_key"] == "school_comp_share"
    assert app.session_state["_school_comp_share_payload"] == {
        "tab": "school_comparison",
        "school_comp_schools": ["Иванов И.И.", "Петров П.П."],
        "school_comp_scope": "all",
        "school_comp_metric": "euclidean_oblique",
        "school_comp_basis": "selected",
        "school_comp_nodes": ["1"],
        "school_comp_decay": 0.5,
    }


def test_filter_columns_by_nodes_selects_expected_branch() -> None:
    feature_columns = ["1.1", "1.1.1", "1.1.2", "1.2", "2.1"]

    assert filter_columns_by_nodes(feature_columns, ["1.1"]) == [
        "1.1",
        "1.1.1",
        "1.1.2",
    ]
