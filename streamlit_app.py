# streamlit_app.py
# -------------------------------------------------------------
# Точка входа приложения: конфигурация, заголовок, загрузка данных и маршрутизация вкладок.
# Общие компоненты подключаются из core/, вкладки — через tabs/*/tab.py адаптеры.
# -------------------------------------------------------------

from __future__ import annotations

import os
from typing import List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

# ---------------------- Утилиты (utils/) ----------------------------------
from utils.db import load_data, AUTHOR_COLUMN, SUPERVISOR_COLUMNS, FEEDBACK_FILE
from utils.graph import build_index, TREE_OPTIONS
from utils.ui import (
    feedback_button,
)

# ---------------------- Вкладки ------------------------------------------
from core.classifier import THEMATIC_CLASSIFIER
from tabs.registry import (
    DEFAULT_TAB_ID,
    TAB_ID_TO_LABEL,
    TAB_LABEL_TO_ID,
    TAB_SPECS,
)
from tabs.articles.tab import render_articles_comparison_tab
from tabs.dissertations.tab import render_dissertations_tab
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


# ---------------------- Вкладки ------------------------------------------
tab_q = str(st.query_params.get("tab", DEFAULT_TAB_ID)).strip()
requested_tab_id = tab_q if tab_q in TAB_ID_TO_LABEL else DEFAULT_TAB_ID
requested_tab_label = TAB_ID_TO_LABEL[requested_tab_id]

tab_labels = [label for _, label in TAB_SPECS]
tab_objects = st.tabs(tab_labels, default=requested_tab_label)
tab_by_id = {
    tab_id: tab
    for (tab_id, _), tab in zip(TAB_SPECS, tab_objects)
}


# ---------- Вкладка: Построение деревьев ---------------------------------
with tab_by_id["lineages"]:
    render_school_trees_tab(
        df=df,
        idx=idx,
        all_supervisor_names=all_supervisor_names,
        shared_roots=valid_shared_roots,
    )

# ---------- Вкладка: Поиск информации о диссертациях ---------------------
with tab_by_id["dissertations"]:
    render_dissertations_tab(df=df)

# ---------- Вкладка: Поиск по тематическим профилям ---------------------
with tab_by_id["profiles"]:
    render_profiles_tab(
        df=df,
        idx=idx,
        thematic_classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
        specific_files=None,
    )

# ---------- Вкладка: Поиск научных школ ---------------------------------
with tab_by_id["school_search"]:
    render_school_search_tab(
        df=df,
        idx=idx,
        classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
    )

# ---------- Вкладка: Взаимосвязи научных школ ----------------------------
with tab_by_id["intersection"]:
    render_opponents_intersection_tab(
        df=df,
        idx=idx,
    )

# ---------- Вкладка: Анализ научной школы --------------------------------
with tab_by_id["school_analysis"]:
    render_school_analysis_tab(
        df=df,
        idx=idx,
        classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
    )

# ---------- Вкладка: Сравнение научных школ ------------------------------
with tab_by_id["school_comparison"]:
    classifier_labels = {code: title for code, title, _ in THEMATIC_CLASSIFIER}
    render_school_comparison_tab(
        df=df,
        idx=idx,
        scores_folder="basic_scores",
        specific_files=None,
        classifier_labels=classifier_labels,
    )

# ---------- Вкладка: Сравнение по статьям --------------------------------
with tab_by_id["articles_comparison"]:
    render_articles_comparison_tab(
        df_lineage=df,
        idx_lineage=idx,
    )
