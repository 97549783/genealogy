# streamlit_app.py
# -------------------------------------------------------------
# Точка входа приложения: конфигурация, заголовок, загрузка данных и маршрутизация вкладок.
# Общие компоненты подключаются из core/, вкладки — через tabs/*/tab.py адаптеры.
# -------------------------------------------------------------

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

# ---------------------- Утилиты (utils/) ----------------------------------
from utils.db import load_data, AUTHOR_COLUMN, SUPERVISOR_COLUMNS, FEEDBACK_FILE
from utils.graph import build_index, TREE_OPTIONS
from utils.ui import (
    feedback_button,
    show_instruction,
)
from utils.table_display import render_dissertations_widget
from utils.urls import share_params_button

# ---------------------- Вкладки ------------------------------------------
from core.classifier import THEMATIC_CLASSIFIER
from tabs.registry import (
    DEFAULT_TAB_ID,
    TAB_ID_TO_LABEL,
    TAB_LABEL_TO_ID,
    TAB_SPECS,
)
from tabs.articles.tab import render_articles_comparison_tab
from tabs.intersection.tab import render_opponents_intersection_tab
from tabs.lineages.tab import render_school_trees_tab
from tabs.profiles.tab import render_profiles_tab
from tabs.school_analysis.tab import render_school_analysis_tab
from tabs.school_comparison.tab import render_school_comparison_tab
from tabs.school_search.tab import render_school_search_tab
# from school_comparison_new_tab import render_school_comparison_new_tab




# ---------------------- Оформление страницы -------------------------------
st.set_page_config(page_title="Академические родословные", layout="wide")

st.markdown("""
<meta name="google" content="notranslate">
<style>
  iframe { width: 100%; }
</style>
""", unsafe_allow_html=True)

# ---------------------- Секретная страница администратора -----------------
# Доступна только по URL: ?secret=nb39fdv94beraaagv2evdc9ewr3fokv
# Отображает содержимое feedback.csv без кнопки скачивания.
_ADMIN_SECRET = "nb39fdv94beraaagv2evdc9ewr3fokv"

if st.query_params.get("secret") == _ADMIN_SECRET:
    st.title("📋 Обратная связь")
    if FEEDBACK_FILE.exists():
        fb_df = pd.read_csv(FEEDBACK_FILE)
        st.caption(f"Всего записей: {len(fb_df)}")
        st.table(fb_df)
    else:
        st.info("Файл feedback.csv пока не существует — нет ни одного сообщения.")
    st.stop()

# ---------------------- Шапка --------------------------------------------
header_left, header_right = st.columns([0.78, 0.22])
with header_left:
    st.title("📚 Академическая генеалогия")
    st.caption(
        "Платформа для построения деревьев научного руководства, поиска и сравнения "
        "диссертаций по содержательным и формальным критериям. В настоящий момент "
        "основу базы данных составляют авторефераты диссертационных исследований "
        "по педагогическим наукам с 1995 года."
    )
with header_right:
    feedback_button()


# ---------------------- Загрузка данных ----------------------------------
try:
    df = load_data()
except Exception as e:
    st.error(f"Ошибка при загрузке данных: {e}")
    st.stop()

missing = [c for c in [AUTHOR_COLUMN, *SUPERVISOR_COLUMNS] if c not in df.columns]
if missing:
    st.error("Отсутствуют нужные колонки: " + ", ".join(f"`{c}`" for c in missing))
    st.stop()

idx = build_index(df, SUPERVISOR_COLUMNS)

all_supervisor_names: Set[str] = set()
for col in SUPERVISOR_COLUMNS:
    all_supervisor_names.update({v for v in df[col].dropna().astype(str).unique() if v})

shared_roots = st.query_params.get_all("root")
valid_shared_roots = [r for r in shared_roots if r in all_supervisor_names]

if not st.session_state.get("diss_search_query_hydrated", False):
    criteria_q = [
        c for c in st.query_params.get_all("diss_criterion")
        if c in {
            "title", "candidate_name", "supervisors", "opponents",
            "institution_prepared", "leading_organization", "defense_location",
            "city", "year", "specialties",
        }
    ]
    if criteria_q:
        st.session_state["dissertation_search_criteria"] = criteria_q
        for criterion in criteria_q:
            q_val = str(st.query_params.get(f"diss_{criterion}", "")).strip()
            if q_val:
                st.session_state[f"diss_search_{criterion}"] = q_val
        st.session_state["diss_search_should_run"] = True
    st.session_state["diss_search_query_hydrated"] = True


# ---------------------- Вкладки ------------------------------------------
tab_q = str(st.query_params.get("tab", DEFAULT_TAB_ID)).strip()
requested_tab_id = tab_q if tab_q in TAB_ID_TO_LABEL else DEFAULT_TAB_ID
requested_tab_label = TAB_ID_TO_LABEL[requested_tab_id]

(
    tab_lineages,
    tab_dissertations,
    tab_profiles,
    tab_school_search,
    tab_intersection,
    tab_school_analysis,
    #tab_schoolcomparison,
    #tab_articles_comparison,
) = st.tabs(
    [label for _, label in TAB_SPECS],
    default=requested_tab_label,
)


# ---------- Вкладка: Построение деревьев ---------------------------------
with tab_lineages:
    render_school_trees_tab(
        df=df,
        idx=idx,
        all_supervisor_names=all_supervisor_names,
        shared_roots=valid_shared_roots,
    )

# ---------- Вкладка: Поиск информации о диссертациях ---------------------
with tab_dissertations:
    if st.button("📖 Инструкция", key="instruction_dissertations"):
        show_instruction("dissertations")

    st.subheader("Поиск информации о диссертациях")
    st.write("На этой вкладке доступен поиск диссертаций по формальным критериям.")

    all_years = sorted(
        [str(y) for y in df["year"].dropna().unique() if str(y).strip()], reverse=True
    )
    all_cities = sorted(
        [str(c) for c in df["city"].dropna().unique() if str(c).strip()]
    )
    all_specialties: Set[str] = set()
    for col in ["specialties_1.code", "specialties_1.name", "specialties_2.code", "specialties_2.name"]:
        if col in df.columns:
            all_specialties.update([str(v).strip() for v in df[col].dropna().unique() if str(v).strip()])
    all_specialties_sorted = sorted(all_specialties)

    available_criteria = {
        "title": "Название диссертации",
        "candidate_name": "ФИО автора",
        "supervisors": "ФИО научного руководителя",
        "opponents": "ФИО оппонента",
        "institution_prepared": "Организация выполнения",
        "leading_organization": "Ведущая организация",
        "defense_location": "Место защиты",
        "city": "Город защиты",
        "year": "Год защиты",
        "specialties": "Специальность",
    }

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
    else:
        st.markdown("### 2. Ввод данных")
        search_params: Dict[str, str] = {}

        for criterion in selected_criteria:
            if criterion == "year":
                search_params[criterion] = st.selectbox(
                    available_criteria[criterion],
                    options=["Все"] + all_years,
                    key=f"diss_search_{criterion}",
                )
            elif criterion == "city":
                search_params[criterion] = st.selectbox(
                    available_criteria[criterion],
                    options=["Все"] + all_cities,
                    key=f"diss_search_{criterion}",
                )
            elif criterion == "specialties":
                search_params[criterion] = st.selectbox(
                    available_criteria[criterion],
                    options=["Все"] + all_specialties_sorted,
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
            st.session_state["diss_search_should_run"] = True

        if st.session_state.get("diss_search_should_run", False):
            result_df = df.copy()
            for criterion, value in search_params.items():
                if not value or value == "Все":
                    continue
                if criterion in [
                    "title", "candidate_name", "institution_prepared",
                    "leading_organization", "defense_location",
                ]:
                    result_df = result_df[
                        result_df[criterion].astype(str).str.contains(value, case=False, na=False)
                    ]
                elif criterion == "supervisors":
                    mask = pd.Series([False] * len(result_df), index=result_df.index)
                    for col in ["supervisors_1.name", "supervisors_2.name"]:
                        if col in result_df.columns:
                            mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
                    result_df = result_df[mask]
                elif criterion == "opponents":
                    mask = pd.Series([False] * len(result_df), index=result_df.index)
                    for col in ["opponents_1.name", "opponents_2.name", "opponents_3.name"]:
                        if col in result_df.columns:
                            mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
                    result_df = result_df[mask]
                elif criterion in ["city", "year"]:
                    result_df = result_df[
                        result_df[criterion].astype(str).str.contains(value, case=False, na=False)
                    ]
                elif criterion == "specialties":
                    mask = pd.Series([False] * len(result_df), index=result_df.index)
                    for col in [
                        "specialties_1.code", "specialties_1.name",
                        "specialties_2.code", "specialties_2.name",
                    ]:
                        if col in result_df.columns:
                            mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
                    result_df = result_df[mask]
            st.session_state["diss_search_result"] = result_df

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

# ---------- Вкладка: Поиск по тематическим профилям ---------------------
with tab_profiles:
    render_profiles_tab(
        df=df,
        idx=idx,
        thematic_classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
        specific_files=None,
    )

# ---------- Вкладка: Поиск научных школ ---------------------------------
with tab_school_search:
    render_school_search_tab(
        df=df,
        idx=idx,
        classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
    )

# ---------- Вкладка: Взаимосвязи научных школ ----------------------------
with tab_intersection:
    render_opponents_intersection_tab(
        df=df,
        idx=idx,
    )

# ---------- Вкладка: Анализ научной школы --------------------------------
with tab_school_analysis:
    render_school_analysis_tab(
        df=df,
        idx=idx,
        classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
    )

# ---------- Вкладка: Сравнение научных школ ------------------------------
#with tab_schoolcomparison:
#    classifier_labels = {code: title for code, title, _ in THEMATIC_CLASSIFIER}
#    render_school_comparison_tab(
#        df=df,
#        idx=idx,
#        scores_folder="basic_scores",
#        specific_files=None,
#        classifier_labels=classifier_labels,
#    )

# ---------- Вкладка: Сравнение по статьям --------------------------------
#with tab_articles_comparison:
#    render_articles_comparison_tab(
#        df_lineage=df,
#        idx_lineage=idx,
#    )
