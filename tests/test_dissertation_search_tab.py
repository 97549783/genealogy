from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_dissertation_search_tab_renders_formal_subtab_by_default() -> None:
    app = AppTest.from_string(
        """
import streamlit as st
import pandas as pd
import tabs.dissertation_search.tab as tab

calls = []

def _formal(df, **kwargs):
    calls.append("formal")

def _profiles(df, idx):
    calls.append("profiles")

tab.render_dissertations_tab = _formal
tab.render_profiles_tab = _profiles

tab.render_dissertation_search_tab(
    df=pd.DataFrame([{"Code": "1"}]),
    idx={},
    db_signature=("diss-search", 1.0, 1),
)

st.session_state["_calls"] = calls
"""
    )

    app.run()

    assert app.session_state["_calls"] == ["formal"]


def test_dissertation_search_tab_can_render_profiles_subtab() -> None:
    app = AppTest.from_string(
        """
import streamlit as st
import pandas as pd
import tabs.dissertation_search.tab as tab

calls = []

def _formal(df, **kwargs):
    calls.append("formal")

def _profiles(df, idx):
    calls.append("profiles")

tab.render_dissertations_tab = _formal
tab.render_profiles_tab = _profiles

tab.render_dissertation_search_tab(
    df=pd.DataFrame([{"Code": "1"}]),
    idx={},
    db_signature=("diss-search", 1.0, 1),
)

st.session_state["_calls"] = calls
"""
    )

    app.session_state["dissertation_search_subtab"] = "Поиск по тематическим профилям"
    app.run()

    assert app.session_state["_calls"] == ["profiles"]
