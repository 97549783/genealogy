from __future__ import annotations

import streamlit as st

from core.classifier import PROFILE_SELECTION_LIMIT, PROFILE_SELECTION_SESSION_KEY
from core.domain.profile_sources import get_profile_source


def profile_state_key(base: str, profile_source_id: str) -> str:
    return f"{base}_{profile_source_id}"


def hydrate_topics_query_params(
    classifier_dict: dict[str, str],
    profile_source_id: str,
) -> None:
    """Гидратирует состояние поиска по query params один раз на источник профилей."""
    hydrated_key = profile_state_key("profile_query_hydrated", profile_source_id)
    selection_key = profile_state_key(PROFILE_SELECTION_SESSION_KEY, profile_source_id)
    search_active_key = profile_state_key("profile_search_active", profile_source_id)
    min_score_key = profile_state_key("profile_min_score", profile_source_id)

    if st.session_state.get(hydrated_key, False):
        return

    profile_source_q = get_profile_source(st.query_params.get("profile_source", "pedagogy_5_8")).id
    if profile_source_q != profile_source_id:
        st.session_state[hydrated_key] = True
        return

    query_codes = [c.strip() for c in st.query_params.get_all("codes") if str(c).strip()]
    if query_codes:
        valid_codes = [c for c in query_codes if c in classifier_dict][:PROFILE_SELECTION_LIMIT]
        if valid_codes:
            st.session_state[selection_key] = valid_codes
            st.session_state[search_active_key] = True

    min_score_q = str(st.query_params.get("min_score", "")).strip()
    if min_score_q:
        try:
            min_score_val = float(min_score_q)
            if 1.0 <= min_score_val <= 10.0:
                st.session_state[min_score_key] = min_score_val
        except ValueError:
            pass

    st.session_state[hydrated_key] = True


def trigger_rerun() -> None:
    """Перезапускает Streamlit с fallback на старый API."""
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()  # type: ignore[attr-defined]
