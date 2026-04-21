from __future__ import annotations

import streamlit as st

from .search import get_available_criteria


def hydrate_dissertations_query_params() -> None:
    if st.session_state.get("diss_search_query_hydrated", False):
        return

    available_criteria = set(get_available_criteria().keys())
    criteria_q = [
        c for c in st.query_params.get_all("diss_criterion") if c in available_criteria
    ]

    if criteria_q:
        st.session_state["dissertation_search_criteria"] = criteria_q
        for criterion in criteria_q:
            q_val = str(st.query_params.get(f"diss_{criterion}", "")).strip()
            if q_val:
                st.session_state[f"diss_search_{criterion}"] = q_val
        st.session_state["diss_search_should_run"] = True

    st.session_state["diss_search_query_hydrated"] = True


def request_search() -> None:
    st.session_state["diss_search_should_run"] = True
