from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest

from tabs.profiles.search import load_basic_scores, load_dissertation_profile_scores


# ==============================================================================
# ТЕСТ СОВМЕСТИМОСТИ ALIAS
# ==============================================================================

def test_load_basic_scores_alias_kept_for_compatibility() -> None:
    """load_basic_scores сохранён как совместимый alias — он должен существовать."""
    assert load_basic_scores is not None


def test_load_basic_scores_alias_matches_new_loader() -> None:
    """load_basic_scores и load_dissertation_profile_scores возвращают одно и то же при одинаковом входе."""
    import unittest.mock as mock

    fake_df = pd.DataFrame([{"Code": "X1", "1.1": 5.0}])

    with mock.patch(
        "tabs.profiles.search.load_dissertation_scores",
        return_value=fake_df,
    ) as patched:
        result_new = load_dissertation_profile_scores(profile_source_id="pedagogy_5_8")
        result_alias = load_basic_scores(profile_source_id="pedagogy_5_8")

    assert patched.call_count == 2
    pd.testing.assert_frame_equal(result_new, result_alias)


# ==============================================================================
# ТЕСТЫ МАРШРУТИЗАЦИИ ВКЛАДКИ
# ==============================================================================

def test_profiles_tab_routes_to_selected_mode() -> None:
    app = AppTest.from_string(
        """
import streamlit as st
import pandas as pd
import tabs.profiles.tab as profiles_tab

captured = []

def _topics(**kwargs):
    captured.append(("topics", kwargs))

def _entropy(**kwargs):
    captured.append(("entropy", kwargs))

profiles_tab.render_search_by_topics = _topics
profiles_tab.render_entropy_specificity_tab = _entropy

sample_df = pd.DataFrame([
    {"Code": "A1", "candidate.name": "Иванов И.И.", "title": "Тема"}
])

scores = pd.DataFrame([
    {"Code": "A1", "1.1.1": 5.0}
])

profiles_tab.load_dissertation_profile_scores = lambda profile_source_id="pedagogy_5_8": scores

profiles_tab.get_classifier_by_profile_source = lambda source_id: [("1.1.1", "Тема", False)]
profiles_tab.get_classifier_labels_by_profile_source = lambda source_id: {"1.1.1": "Тема"}
profiles_tab.render_profiles_tab(
    df=sample_df,
    idx={},
)

st.session_state["_captured_calls"] = captured
"""
    )

    app.run()
    assert app.session_state["_captured_calls"][0][0] == "topics"

    app.radio(key="profile_search_mode_selector").set_value("По мере общности/специфичности")
    app.run()
    assert app.session_state["_captured_calls"][0][0] == "entropy"


def test_topics_mode_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import streamlit as st
import pandas as pd
import tabs.profiles.topics_mode as topics


def _fake_share(payload, key):
    st.session_state["_captured_share_payload"] = payload
    st.session_state["_captured_share_key"] = key


topics.share_params_button = _fake_share
topics.validate_code_selection = lambda selected_codes, all_feature_columns: (True, "")
topics.search_by_codes = lambda scores_df, selected_codes, min_score: pd.DataFrame([
    {"Code": "A1", "1.1.1": 6.5, "profile_total": 6.5}
])
topics.merge_with_dissertation_info = lambda search_results, dissertations_df, selected_codes: pd.DataFrame([
    {
        "Code": "A1",
        "candidate.name": "Иванов И.И.",
        "title": "Тема",
        "profile_total": 6.5,
        "1.1.1": 6.5,
    }
])

def _format(results, selected_codes, classifier_labels=None):
    display = pd.DataFrame([
        {"Скачать": "https://example.org", "Автор": "Иванов И.И.", "Название": "Тема"}
    ])
    return display, {}, results

topics.format_results_for_display = _format
topics.build_export_df = lambda results, display_df, for_excel=False: display_df

sample_df = pd.DataFrame([
    {"Code": "A1", "candidate.name": "Иванов И.И.", "title": "Тема"}
])
scores_df = pd.DataFrame([
    {"Code": "A1", "1.1.1": 6.5}
])

topics.render_search_by_topics(
    df=sample_df,
    scores_df=scores_df,
    thematic_classifier=[("1.1.1", "Тема", False)],
    classifier_dict={"1.1.1": "Тема"},
)
"""
    )

    app.query_params["codes"] = ["1.1.1"]
    app.query_params["min_score"] = "5.5"
    app.run()

    assert app.session_state["profile_query_hydrated_pedagogy_5_8"] is True
    assert app.session_state["profile_selected_codes_pedagogy_5_8"] == ["1.1.1"]
    assert app.session_state["profile_search_active_pedagogy_5_8"] is True
    assert app.session_state["profile_min_score_pedagogy_5_8"] == 5.5

    assert app.session_state["_captured_share_key"] == "profiles_share_results_pedagogy_5_8"
    assert app.session_state["_captured_share_payload"] == {
        "tab": "profiles",
        "profile_source": "pedagogy_5_8",
        "codes": ["1.1.1"],
        "min_score": 5.5,
    }
