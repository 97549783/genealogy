"""Загрузка данных и построение общего контекста приложения."""

from __future__ import annotations

from typing import Set

import streamlit as st

from core.classifier import THEMATIC_CLASSIFIER
from core.db import AUTHOR_COLUMN, SUPERVISOR_COLUMNS, load_data, get_db_signature
from core.lineage.graph import build_index
from core.app.context import AppContext
from core.perf import perf_timer


def build_app_context() -> AppContext:
    """Собирает и валидирует общий контекст для вкладок."""
    try:
        with perf_timer("app.load_data"):
            df = load_data()
    except Exception as exc:
        st.error(f"Ошибка при загрузке данных: {exc}")
        st.stop()

    missing = [c for c in [AUTHOR_COLUMN, *SUPERVISOR_COLUMNS] if c not in df.columns]
    if missing:
        st.error("Отсутствуют нужные колонки: " + ", ".join(f"`{c}`" for c in missing))
        st.stop()

    db_signature = get_db_signature()
    # Временный кэш до перехода на материализованные таблицы графа в SQLite.
    with perf_timer("app.build_index"):
        idx = _build_cached_index(db_signature, df)
    with perf_timer("app.collect_supervisor_names"):
        all_supervisor_names = _collect_cached_supervisor_names(db_signature, df)

    shared_roots = st.query_params.get_all("root")
    valid_shared_roots = [r for r in shared_roots if r in all_supervisor_names]

    classifier_labels = {code: title for code, title, _ in THEMATIC_CLASSIFIER}

    return AppContext(
        df=df,
        idx=idx,
        all_supervisor_names=all_supervisor_names,
        valid_shared_roots=valid_shared_roots,
        classifier_labels=classifier_labels,
    )


@st.cache_data(show_spinner=False)
def _build_cached_index(
    db_signature: tuple[str, float, int],
    df,
):
    """Строит кэшированный индекс научных руководителей."""
    _ = db_signature
    return build_index(df, SUPERVISOR_COLUMNS)


@st.cache_data(show_spinner=False)
def _collect_cached_supervisor_names(
    db_signature: tuple[str, float, int],
    df,
) -> Set[str]:
    """Собирает кэшированный список имён научных руководителей."""
    _ = db_signature
    all_supervisor_names: Set[str] = set()
    for col in SUPERVISOR_COLUMNS:
        all_supervisor_names.update({v for v in df[col].dropna().astype(str).unique() if v})
    return all_supervisor_names
