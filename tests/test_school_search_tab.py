from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_school_search_city_mode_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.school_search.tab as school_search_tab


def _fake_search_by_city(**kwargs):
    return pd.DataFrame([
        {"Руководитель": "Иванов И.И.", "Защит в городе": 3}
    ]), {"Иванов И.И.": ["Москва"]}


def _fake_excel(**kwargs):
    return b"excel-bytes"


def _fake_share(payload, key):
    st.session_state["_school_search_share_payload"] = payload
    st.session_state["_school_search_share_key"] = key


school_search_tab.search_by_city = _fake_search_by_city
school_search_tab.build_excel_search_results = _fake_excel
school_search_tab.share_params_button = _fake_share

sample_df = pd.DataFrame([
    {"candidate_name": "Иванов И.И.", "city": "Москва", "supervisors_1.name": "Петров П.П."}
])

school_search_tab.render_school_search_tab(
    df=sample_df,
    idx={},
    classifier=None,
)
"""
    )

    app.query_params["mode"] = "city"
    app.query_params["scope"] = "all"
    app.query_params["top_n"] = "10"
    app.query_params["city_query"] = "Москва"

    app.run()

    assert app.session_state["school_search_query_hydrated"] is True
    assert app.session_state["school_search_mode"] == "city"
    assert app.session_state["school_search_run_state"] is True
    assert app.session_state["school_search_top_n"] == 10
    assert app.session_state["school_search_city"] == "Москва"
    assert app.session_state["_school_search_share_key"] == "school_search_share_city"
    assert app.session_state["_school_search_share_payload"] == {
        "tab": "school_search",
        "mode": "city",
        "scope": "all",
        "top_n": 10,
        "city_query": "Москва",
        "text_search_mode": "fast",
    }


def test_excel_not_reused_across_different_signatures() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.school_search.tab as school_search_tab

def _fake_search_by_city(**kwargs):
    return pd.DataFrame([{"Руководитель": "Иванов И.И.", "Защит в городе": 3}]), {"Иванов И.И.": ["Москва"]}

def _fake_excel(**kwargs):
    st.session_state["excel_build_calls"] = st.session_state.get("excel_build_calls", 0) + 1
    return b"new-excel"

school_search_tab.search_by_city = _fake_search_by_city
school_search_tab.build_excel_search_results = _fake_excel

st.session_state["school_search_last_signature"] = {"mode": "old"}
st.session_state["school_search_last_payload"] = {"excel_bytes": b"old-excel"}

sample_df = pd.DataFrame([{"candidate_name": "Иванов И.И.", "city": "Москва", "supervisors_1.name": "Петров П.П."}])
school_search_tab.render_school_search_tab(df=sample_df, idx={}, classifier=None)
"""
    )
    app.query_params["mode"] = "city"
    app.query_params["scope"] = "all"
    app.query_params["top_n"] = "10"
    app.query_params["city_query"] = "Москва"
    app.run()
    app.button[0].click()
    app.run()
    assert ("excel_build_calls" in app.session_state) and app.session_state["excel_build_calls"] >= 1
