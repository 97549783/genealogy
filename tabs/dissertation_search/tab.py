from __future__ import annotations

from typing import Dict

import pandas as pd
import streamlit as st

from tabs.dissertations.tab import render_dissertations_tab
from tabs.profiles.tab import render_profiles_tab


SUBTAB_STATE_KEY = "dissertation_search_subtab"

FORMAL_SUBTAB_ID = "formal"
PROFILES_SUBTAB_ID = "profiles"

SUBTAB_SPECS = [
    (FORMAL_SUBTAB_ID, "Поиск по формальным признакам"),
    (PROFILES_SUBTAB_ID, "Поиск по тематическим профилям"),
]

SUBTAB_ID_TO_LABEL = dict(SUBTAB_SPECS)


def render_dissertation_search_tab(df: pd.DataFrame, idx: Dict[str, set], *, db_signature) -> None:
    st.subheader("Поиск диссертаций")
    st.write(
        "Здесь объединены два режима: поиск по формальным признакам "
        "и поиск по тематическим профилям диссертаций."
    )

    subtab_labels = [label for _, label in SUBTAB_SPECS]
    subtab_objects = st.tabs(
        subtab_labels,
        key=SUBTAB_STATE_KEY,
        on_change="rerun",
    )

    subtab_by_id = {
        subtab_id: tab
        for (subtab_id, _), tab in zip(SUBTAB_SPECS, subtab_objects)
    }

    def _should_render_subtab(subtab_id: str) -> bool:
        tab = subtab_by_id[subtab_id]
        open_state = getattr(tab, "open", None)

        if open_state is not None:
            return bool(open_state)

        # Запасной путь для тестов или старого поведения Streamlit.
        active_label = st.session_state.get(
            SUBTAB_STATE_KEY,
            SUBTAB_ID_TO_LABEL[FORMAL_SUBTAB_ID],
        )
        return SUBTAB_ID_TO_LABEL[subtab_id] == active_label

    if _should_render_subtab(FORMAL_SUBTAB_ID):
        with subtab_by_id[FORMAL_SUBTAB_ID]:
            render_dissertations_tab(df=df, db_signature=db_signature)

    if _should_render_subtab(PROFILES_SUBTAB_ID):
        with subtab_by_id[PROFILES_SUBTAB_ID]:
            render_profiles_tab(df=df, idx=idx)
