from __future__ import annotations

import streamlit as st

from core.classifier import PROFILE_SELECTION_LIMIT, PROFILE_SELECTION_SESSION_KEY


def hydrate_topics_query_params(classifier_dict: dict[str, str]) -> None:
    """Гидратирует состояние поиска по query params один раз за сессию."""
    if st.session_state.get("profile_query_hydrated", False):
        return

    query_codes = [c.strip() for c in st.query_params.get_all("codes") if str(c).strip()]
    if query_codes:
        valid_codes = [c for c in query_codes if c in classifier_dict][:PROFILE_SELECTION_LIMIT]
        if valid_codes:
            st.session_state[PROFILE_SELECTION_SESSION_KEY] = valid_codes
            st.session_state["profile_search_active"] = True

    min_score_q = str(st.query_params.get("min_score", "")).strip()
    if min_score_q:
        try:
            min_score_val = float(min_score_q)
            if 1.0 <= min_score_val <= 10.0:
                st.session_state["profile_min_score"] = min_score_val
        except ValueError:
            pass

    st.session_state["profile_query_hydrated"] = True


def trigger_rerun() -> None:
    """Перезапускает Streamlit с fallback на старый API."""
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()  # type: ignore[attr-defined]
