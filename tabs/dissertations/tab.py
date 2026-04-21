from __future__ import annotations

from typing import Dict

import pandas as pd
import streamlit as st

from utils.table_display import render_dissertations_widget
from utils.ui import show_instruction
from utils.urls import share_params_button

from .search import build_filter_options, filter_dissertations, get_available_criteria
from .state import hydrate_dissertations_query_params, request_search


def render_dissertations_tab(df: pd.DataFrame) -> None:
    hydrate_dissertations_query_params()

    if st.button("📖 Инструкция", key="instruction_dissertations"):
        show_instruction("dissertations")

    st.subheader("Поиск информации о диссертациях")
    st.write("На этой вкладке доступен поиск диссертаций по формальным критериям.")

    available_criteria = get_available_criteria()
    filter_options = build_filter_options(df)

    st.markdown("### 1. Выбор критериев поиска")
    selected_criteria = st.multiselect(
        "Выберите критерии поиска (максимум 5 одновременно)",
        options=list(available_criteria.keys()),
        format_func=lambda x: available_criteria[x],
        max_selections=5,
        key="dissertation_search_criteria",
    )

    if not selected_criteria:
        st.info("Выберите хотя бы один критерий для поиска.")
        return

    st.markdown("### 2. Ввод данных")
    search_params: Dict[str, str] = {}

    for criterion in selected_criteria:
        if criterion in ["year", "city", "specialties"]:
            search_params[criterion] = st.selectbox(
                available_criteria[criterion],
                options=["Все"] + filter_options[criterion],
                key=f"diss_search_{criterion}",
            )
        else:
            search_params[criterion] = st.text_input(
                available_criteria[criterion],
                placeholder=f"Введите {available_criteria[criterion].lower()}...",
                key=f"diss_search_{criterion}",
            )

    st.markdown("### 3. Результат")

    if st.button("Найти", type="primary", key="dissertation_search_button"):
        request_search()

    if st.session_state.get("diss_search_should_run", False):
        st.session_state["diss_search_result"] = filter_dissertations(df, search_params)

    if "diss_search_result" in st.session_state:
        result_df = st.session_state["diss_search_result"]
        if result_df.empty:
            st.warning("По заданным критериям ничего не найдено.")
        else:
            st.success(f"Найдено диссертаций: {len(result_df)}")
            share_params_button(
                {
                    "tab": "dissertations",
                    "diss_criterion": selected_criteria,
                    **{
                        f"diss_{criterion}": search_params.get(criterion, "")
                        for criterion in selected_criteria
                    },
                },
                key="diss_search_share",
            )
            render_dissertations_widget(
                subset=result_df,
                key="поиск_диссертаций",
                title="Результаты",
                expanded=False,
                file_name_prefix="список_диссертаций_поиск",
            )
