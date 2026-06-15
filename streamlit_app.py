"""Точка композиции Streamlit-приложения."""

from __future__ import annotations

import streamlit as st

from core.app import (
    build_app_context,
    maybe_render_admin_page_and_stop,
    render_app_header,
)
from tabs.articles.tab import render_articles_analysis_tab
from tabs.dissertations.tab import render_dissertations_tab
from tabs.intersection.tab import render_opponents_intersection_tab
from tabs.lineages.tab import render_school_trees_tab
from tabs.profiles.tab import render_profiles_tab
from tabs.registry import DEFAULT_TAB_ID, TAB_ID_TO_LABEL, TAB_SPECS
from tabs.school_analysis.tab import render_school_analysis_tab
from tabs.school_comparison.tab import render_school_comparison_tab
from tabs.school_search.tab import render_school_search_tab
from tabs.test1111 import  test1

MAIN_TAB_STATE_KEY = "main_tab"


st.set_page_config(page_title="Академическая генеалогия", layout="wide")

st.markdown(
    """
<meta name="google" content="notranslate">
<style>
  iframe { width: 100%; }
</style>
""",
    unsafe_allow_html=True,
)

maybe_render_admin_page_and_stop()
ctx = build_app_context()
render_app_header()

tab_q = str(st.query_params.get("tab", DEFAULT_TAB_ID)).strip()
requested_tab_id = tab_q if tab_q in TAB_ID_TO_LABEL else DEFAULT_TAB_ID
requested_tab_label = TAB_ID_TO_LABEL[requested_tab_id]

tab_labels = [label for _, label in TAB_SPECS]
tab_objects = st.tabs(
    tab_labels,
    default=requested_tab_label,
    key=MAIN_TAB_STATE_KEY,
    on_change="rerun",
)
tab_by_id = {tab_id: tab for (tab_id, _), tab in zip(TAB_SPECS, tab_objects)}


def _should_render_tab(tab_id: str) -> bool:
    tab = tab_by_id[tab_id]
    open_state = getattr(tab, "open", None)

    if open_state is not None:
        return bool(open_state)

    # Запасной путь для тестов или старого поведения Streamlit.
    active_label = st.session_state.get(MAIN_TAB_STATE_KEY, requested_tab_label)
    return TAB_ID_TO_LABEL[tab_id] == active_label


if _should_render_tab("lineages"):
    with tab_by_id["lineages"]:
        render_school_trees_tab(
            df=ctx.df,
            idx=ctx.idx,
            all_supervisor_names=ctx.all_supervisor_names,
            shared_roots=ctx.valid_shared_roots,
        )

if _should_render_tab("dissertations"):
    with tab_by_id["dissertations"]:
        render_dissertations_tab(df=ctx.df)

if _should_render_tab("profiles"):
    with tab_by_id["profiles"]:
        render_profiles_tab(
            df=ctx.df,
            idx=ctx.idx,
        )

if _should_render_tab("school_search"):
    with tab_by_id["school_search"]:
        render_school_search_tab(
            df=ctx.df,
            idx=ctx.idx,
        )

if _should_render_tab("intersection"):
    with tab_by_id["intersection"]:
        render_opponents_intersection_tab(df=ctx.df, idx=ctx.idx)

if _should_render_tab("school_analysis"):
    with tab_by_id["school_analysis"]:
        render_school_analysis_tab(
            df=ctx.df,
            idx=ctx.idx,
        )

if _should_render_tab("school_comparison"):
    with tab_by_id["school_comparison"]:
        render_school_comparison_tab(
            df=ctx.df,
            idx=ctx.idx,
        )

if _should_render_tab("articles_comparison"):
    with tab_by_id["articles_comparison"]:
        render_articles_analysis_tab(df_lineage=ctx.df, idx_lineage=ctx.idx)

if _should_render_tab("test1111"):
    with tab_by_id["test1111"]:
   render_test1111(df=ctx.df, idx=ctx.idx)     
