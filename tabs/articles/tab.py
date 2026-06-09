"""Оркестратор демо-вкладки анализа статей."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

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
from .semantic_imrad_mode import render_semantic_imrad_search_mode
from .data import ALL_JOURNALS_KEY, filter_articles_by_journals, normalize_journal_key
from .query_params import query_params_signature, should_hydrate_query

ARTICLE_MODE_LABELS = {
    "single_school": "Анализ одной школы",
    "similar_schools": "Поиск похожих школ",
    "comparison": "Сравнение выбранных школ",
    "semantic_imrad_search": "Анализ по разделам статьи",
    
}
ARTICLE_MODE_KEYS = list(ARTICLE_MODE_LABELS.keys())

def _journal_fallback_key(journal: Any) -> str:
    """Строит запасной ключ для журнала без ISSN."""
    return f"journal:{normalize_journal_key(journal)}"


def build_available_journal_options(df_articles: pd.DataFrame) -> list[dict[str, Any]]:
    """Строит варианты выбора журналов по загруженным статьям."""
    if df_articles is None or df_articles.empty:
        return []
    work = df_articles.copy()
    for column in ["ISSN", "Journal", "Year", "Article_id"]:
        if column not in work.columns:
            work[column] = ""
    work["ISSN"] = work["ISSN"].fillna("").astype(str).str.strip()
    work["Journal"] = work["Journal"].fillna("").astype(str).str.strip()
    work = work[(work["ISSN"] != "") | (work["Journal"] != "")]
    if work.empty:
        return []
    work["_key"] = work["ISSN"].where(work["ISSN"] != "", work["Journal"].map(_journal_fallback_key))
    work["_year"] = pd.to_numeric(work["Year"], errors="coerce")
    options: list[dict[str, Any]] = []
    for key, group in work.groupby("_key", sort=True):
        issn_values = [value for value in group["ISSN"].astype(str) if value.strip()]
        journal_values = [value for value in group["Journal"].astype(str) if value.strip()]
        issn = issn_values[0] if issn_values else ""
        journal = journal_values[0] if journal_values else issn
        article_count = int(group["Article_id"].nunique()) if "Article_id" in group.columns else int(len(group))
        label = f"{journal} ({issn})" if issn else journal
        if article_count:
            label = f"{label} — {article_count} статей"
        options.append({"key": str(key), "issn": issn, "journal": journal, "label": label, "article_count": article_count})
    return sorted(options, key=lambda item: (str(item.get("journal", "")), str(item.get("issn", ""))))


def _hydrate_journals_from_query(valid_keys: set[str]) -> None:
    """Загружает выбранные журналы из query-параметров."""
    signature = query_params_signature(["aa_journals"])
    if not should_hydrate_query("aa_journals_query_signature", signature):
        if "aa_selected_journals" not in st.session_state:
            st.session_state["aa_selected_journals"] = [ALL_JOURNALS_KEY]
            st.session_state["aa_selected_journals_input"] = [ALL_JOURNALS_KEY]
        return
    raw_values = [normalize_journal_key(value) for value in st.query_params.get_all("aa_journals") if str(value).strip()]
    if not raw_values or normalize_journal_key(ALL_JOURNALS_KEY) in raw_values:
        st.session_state["aa_selected_journals"] = [ALL_JOURNALS_KEY]
        st.session_state["aa_selected_journals_input"] = [ALL_JOURNALS_KEY]
        return
    selected = [value for value in raw_values if value in valid_keys]
    st.session_state["aa_selected_journals"] = selected or [ALL_JOURNALS_KEY]
    st.session_state["aa_selected_journals_input"] = selected or [ALL_JOURNALS_KEY]


def render_article_journal_selector(journal_options: list[dict[str, Any]]) -> list[str]:
    """Отрисовывает выбор журналов для анализа статей."""
    valid_keys = {normalize_journal_key(option["key"]) for option in journal_options}
    _hydrate_journals_from_query(valid_keys)

    option_keys = [ALL_JOURNALS_KEY, *[str(option["key"]) for option in journal_options]]
    labels = {ALL_JOURNALS_KEY: "Все журналы"}
    labels.update({str(option["key"]): str(option["label"]) for option in journal_options})
    current = st.session_state.get("aa_selected_journals", [ALL_JOURNALS_KEY])
    default = [value for value in current if value in option_keys] or [ALL_JOURNALS_KEY]
    selected = st.multiselect(
        "Журналы для анализа",
        options=option_keys,
        default=default,
        format_func=lambda value: labels.get(str(value), str(value)),
        help="Выберите один или несколько журналов. Если выбран вариант «Все журналы», анализ строится по всем доступным статьям.",
        key="aa_selected_journals_input",
    )
    if not selected or ALL_JOURNALS_KEY in selected:
        st.session_state["aa_selected_journals"] = [ALL_JOURNALS_KEY]
        return [ALL_JOURNALS_KEY]
    cleaned = [str(value) for value in selected if str(value) in option_keys and str(value) != ALL_JOURNALS_KEY]
    if not cleaned:
        st.session_state["aa_selected_journals"] = [ALL_JOURNALS_KEY]
        return [ALL_JOURNALS_KEY]
    st.session_state["aa_selected_journals"] = cleaned
    return cleaned


def _hydrate_mode_from_query() -> None:
    """Загружает режим из URL при изменении сигнатуры query-параметров."""
    signature = query_params_signature(["articles_mode", "aa_journals", "ac_people", "aa_school", "aa_source_school"])
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
    st.caption(
        "В данный момент анализ основан только на статьях журналов "
        "«Информатика и образование» и "
        "«Вестник Московского городского педагогического университета. "
        "Серия: Информатика и информатизация образования»."
         "Серия: Информатика и информатизация образования1»."
    )

    df_articles_all = load_articles_data()
    journal_options = build_available_journal_options(df_articles_all)
    selected_journals = render_article_journal_selector(journal_options)
    df_articles_filtered = filter_articles_by_journals(df_articles_all, selected_journals)
    if df_articles_filtered is None or df_articles_filtered.empty:
        st.warning("Для выбранных журналов статьи не найдены.")
        return

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
            df_articles=df_articles_filtered,
        )
    elif mode == "similar_schools":
        render_similar_schools_mode(
            df_lineage=df_lineage,
            idx_lineage=idx_lineage,
            classifier_labels=classifier_labels,
            df_articles=df_articles_filtered,
        )
    elif mode == "comparison":
        _sync_comparison_mode_for_tests()
        _comparison_mode.render_articles_comparison_mode(
            df_lineage=df_lineage,
            idx_lineage=idx_lineage,
            selected_roots=selected_roots,
            classifier_labels=classifier_labels,
            df_articles=df_articles_filtered,
        )
    elif mode == "semantic_imrad_search":
        render_semantic_imrad_search_mode(df_articles=df_articles_filtered)
    else:
        st.warning("Неизвестный режим анализа статей.")


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



