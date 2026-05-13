"""Оркестратор демо-вкладки анализа статей."""

from __future__ import annotations

from typing import Dict, List, Optional, Set

import pandas as pd
import streamlit as st

from . import comparison_mode as _comparison_mode
from .comparison_mode import (
    SPECIAL_OPTION_ALL,
    SPECIAL_OPTION_YEAR,
    _filter_feature_columns,
    _build_articles_dataset,
    _compute_selectable_people,
    compute_article_analysis,
    create_articles_silhouette_plot,
    create_comparison_summary,
    load_articles_classifier,
    load_articles_data,
    share_params_button,
)
from .single_school_mode import render_single_school_mode
from .similar_schools_mode import render_similar_schools_mode
from .query_params import query_params_signature, should_hydrate_query

ARTICLE_MODE_LABELS = {
    "single_school": "Анализ одной школы",
    "similar_schools": "Поиск похожих школ",
    "comparison": "Сравнение выбранных школ",
}
ARTICLE_MODE_KEYS = list(ARTICLE_MODE_LABELS.keys())


def _hydrate_mode_from_query() -> None:
    """Загружает режим из URL при изменении сигнатуры query-параметров."""
    signature = query_params_signature(["articles_mode", "ac_people", "aa_school", "aa_source_school"])
    if not should_hydrate_query("aa_mode_query_signature", signature):
        return
    mode = str(st.query_params.get("articles_mode", "")).strip()
    if mode in ARTICLE_MODE_LABELS:
        st.session_state["aa_mode"] = mode
    elif st.query_params.get_all("ac_people"):
        st.session_state["aa_mode"] = "comparison"
    elif st.query_params.get_all("aa_source_school"):
        st.session_state["aa_mode"] = "similar_schools"
    elif st.query_params.get_all("aa_school"):
        st.session_state["aa_mode"] = "single_school"
    elif "aa_mode" not in st.session_state:
        st.session_state["aa_mode"] = "single_school"


def render_articles_analysis_tab(
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    selected_roots: Optional[List[str]] = None,
    classifier_labels: Optional[Dict[str, str]] = None,
) -> None:
    """Отрисовывает вкладку «Анализ статей (демо)» и выбранный режим."""
    _hydrate_mode_from_query()
    if classifier_labels is None:
        classifier_labels = load_articles_classifier()

    st.markdown("## Анализ статей (демо)")
    st.caption("В данный момент анализ основан только на статьях журнала «Информатика и образование».")

    default_mode = st.session_state.get("aa_mode", "single_school")
    index = ARTICLE_MODE_KEYS.index(default_mode) if default_mode in ARTICLE_MODE_KEYS else 0
    mode = st.radio(
        "Режим:",
        options=ARTICLE_MODE_KEYS,
        format_func=lambda value: ARTICLE_MODE_LABELS[value],
        index=index,
        horizontal=True,
        key="aa_mode",
    )

    if mode == "single_school":
        render_single_school_mode(
            df_lineage=df_lineage,
            idx_lineage=idx_lineage,
            classifier_labels=classifier_labels,
        )
    elif mode == "similar_schools":
        render_similar_schools_mode(
            df_lineage=df_lineage,
            idx_lineage=idx_lineage,
            classifier_labels=classifier_labels,
        )
    else:
        _sync_comparison_mode_for_tests()
        _comparison_mode.render_articles_comparison_mode(
            df_lineage=df_lineage,
            idx_lineage=idx_lineage,
            selected_roots=selected_roots,
            classifier_labels=classifier_labels,
        )


def _sync_comparison_mode_for_tests() -> None:
    """Передаёт тестовые подмены из старого модуля во внутренний режим сравнения."""
    for name in [
        "load_articles_classifier",
        "_compute_selectable_people",
        "load_articles_data",
        "_build_articles_dataset",
        "compute_article_analysis",
        "create_articles_silhouette_plot",
        "create_comparison_summary",
        "share_params_button",
    ]:
        if name in globals():
            setattr(_comparison_mode, name, globals()[name])


def render_articles_comparison_tab(
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    selected_roots: Optional[List[str]] = None,
    classifier_labels: Optional[Dict[str, str]] = None,
) -> None:
    """Совместимый вход для прежних ссылок и тестов вкладки сравнения."""
    _sync_comparison_mode_for_tests()
    _comparison_mode.render_articles_comparison_mode(
        df_lineage=df_lineage,
        idx_lineage=idx_lineage,
        selected_roots=selected_roots,
        classifier_labels=classifier_labels,
    )
