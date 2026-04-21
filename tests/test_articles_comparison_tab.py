from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from tabs.articles.tab import SPECIAL_OPTION_ALL, SPECIAL_OPTION_YEAR, _filter_feature_columns


def test_articles_tab_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import tabs.articles.tab as articles_tab


def _fake_load_articles_classifier():
    return {"1": "Раздел 1", "1.1": "Раздел 1.1", "1.1.1": "Раздел 1.1.1", "2": "Раздел 2"}


def _fake_compute_selectable_people(df_lineage, include_without_descendants):
    return ["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "leader", "Петров П.П.": "leader"}


def _fake_load_articles_data():
    return pd.DataFrame(
        [
            {"Article_id": "A1", "Authors": "Иванов И.И.", "Title": "T1", "Year": "2020", "1": 1.0, "1.1": 0.0, "1.1.1": 0.3, "2": 0.2, "Year_num": 2020},
            {"Article_id": "A2", "Authors": "Петров П.П.", "Title": "T2", "Year": "2021", "1": 0.5, "1.1": 0.2, "1.1.1": 0.4, "2": 0.1, "Year_num": 2021},
        ]
    )


def _fake_build_articles_dataset(**kwargs):
    return pd.DataFrame(
        [
            {"school": "Иванов И.И.", "1": 1.0, "1.1": 0.0, "1.1.1": 0.3, "2": 0.2, "Year_num": 2020, "Article_id": "A1", "Authors": "Иванов И.И.", "Title": "T1", "Year": "2020"},
            {"school": "Петров П.П.", "1": 0.5, "1.1": 0.2, "1.1.1": 0.4, "2": 0.1, "Year_num": 2021, "Article_id": "A2", "Authors": "Петров П.П.", "Title": "T2", "Year": "2021"},
        ]
    )


def _fake_compute_article_analysis(**kwargs):
    labels = np.array(["Иванов И.И.", "Петров П.П."])
    return {
        "silhouette_avg": 0.42,
        "sample_silhouette_values": np.array([0.35, 0.49]),
        "labels": labels,
        "school_order": ["Иванов И.И.", "Петров П.П."],
        "unique_schools": ["Иванов И.И.", "Петров П.П."],
        "davies_bouldin": 0.9,
        "calinski_harabasz": 11.0,
        "centroids_dist": 0.7,
    }


def _fake_create_articles_silhouette_plot(**kwargs):
    fig, _ = plt.subplots()
    return fig


def _fake_create_comparison_summary(df, feature_cols):
    return pd.DataFrame({"Научная школа": ["Иванов И.И.", "Петров П.П."], "Количество статей": [1, 1]})


def _fake_share(payload, key):
    st.session_state["_ac_share_payload"] = payload
    st.session_state["_ac_share_key"] = key


articles_tab.load_articles_classifier = _fake_load_articles_classifier
articles_tab._compute_selectable_people = _fake_compute_selectable_people
articles_tab.load_articles_data = _fake_load_articles_data
articles_tab._build_articles_dataset = _fake_build_articles_dataset
articles_tab.compute_article_analysis = _fake_compute_article_analysis
articles_tab.create_articles_silhouette_plot = _fake_create_articles_silhouette_plot
articles_tab.create_comparison_summary = _fake_create_comparison_summary
articles_tab.share_params_button = _fake_share

sample_df = pd.DataFrame([
    {"candidate_name": "Иванов И.И.", "supervisors_1.name": "", "supervisors_2.name": ""},
    {"candidate_name": "Петров П.П.", "supervisors_1.name": "", "supervisors_2.name": ""},
])

articles_tab.render_articles_comparison_tab(df_lineage=sample_df, idx_lineage={})
"""
    )

    app.query_params["ac_people"] = ["Иванов И.И.", "Петров П.П."]
    app.query_params["ac_scope"] = "all"
    app.query_params["ac_metric"] = "euclidean_oblique"
    app.query_params["ac_decay"] = "0.5"
    app.query_params["ac_include_without_desc"] = "true"
    app.query_params["ac_nodes"] = [SPECIAL_OPTION_ALL, SPECIAL_OPTION_YEAR]

    app.run()

    assert app.session_state["ac_query_hydrated"] is True
    assert app.session_state["ac_selected_options"] == ["Иванов И.И.", "Петров П.П."]
    assert app.session_state["ac_run_state"] is True
    assert app.session_state["_ac_share_key"] == "ac_share"
    assert app.session_state["_ac_share_payload"] == {
        "tab": "articles_comparison",
        "ac_people": ["Иванов И.И.", "Петров П.П."],
        "ac_scope": "all",
        "ac_metric": "euclidean_oblique",
        "ac_decay": 0.5,
        "ac_nodes": [SPECIAL_OPTION_ALL, SPECIAL_OPTION_YEAR],
        "ac_include_without_desc": True,
    }


def test_filter_feature_columns_respects_all_basis_and_year() -> None:
    all_feature_cols = ["1", "1.1", "1.1.1", "2", "Year_num"]

    assert _filter_feature_columns(all_feature_cols, [SPECIAL_OPTION_ALL]) == ["1", "1.1", "1.1.1", "2"]
    assert _filter_feature_columns(all_feature_cols, [SPECIAL_OPTION_ALL, SPECIAL_OPTION_YEAR]) == [
        "1",
        "1.1",
        "1.1.1",
        "2",
        "Year_num",
    ]
    assert _filter_feature_columns(all_feature_cols, ["1.1", SPECIAL_OPTION_YEAR]) == ["1.1", "1.1.1", "Year_num"]
