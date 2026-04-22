"""Загрузка данных и построение общего контекста приложения."""

from __future__ import annotations

from typing import Set

import streamlit as st

from core.classifier import THEMATIC_CLASSIFIER
from core.db import AUTHOR_COLUMN, SUPERVISOR_COLUMNS, load_data
from core.lineage.graph import build_index
from core.app.context import AppContext


def build_app_context() -> AppContext:
    """Собирает и валидирует общий контекст для вкладок."""
    try:
        df = load_data()
    except Exception as exc:
        st.error(f"Ошибка при загрузке данных: {exc}")
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

    classifier_labels = {code: title for code, title, _ in THEMATIC_CLASSIFIER}

    return AppContext(
        df=df,
        idx=idx,
        all_supervisor_names=all_supervisor_names,
        valid_shared_roots=valid_shared_roots,
        classifier_labels=classifier_labels,
    )
