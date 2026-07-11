"""Загрузка данных и построение общего контекста приложения."""

from __future__ import annotations

import streamlit as st

from core.classifier import THEMATIC_CLASSIFIER
from core.db import AUTHOR_COLUMN, SUPERVISOR_COLUMNS, get_db_signature, read_dissertation_metadata
from core.lineage.graph import build_index
from core.app.context import AppContext, BaseAppData, DbSignature
from core.perf import perf_timer


def build_app_context() -> AppContext:
    """Собирает и валидирует общий контекст для вкладок."""
    db_signature = get_db_signature()
    try:
        base = _load_base_app_data(db_signature)
    except Exception as exc:
        st.error(f"Ошибка при загрузке данных: {exc}")
        st.stop()

    shared_roots = st.query_params.get_all("root")
    valid_shared_roots = [r for r in shared_roots if r in base.all_supervisor_names]
    classifier_labels = {code: title for code, title, _ in THEMATIC_CLASSIFIER}
    return AppContext(
        db_signature=base.db_signature,
        df=base.df,
        idx=base.idx,
        all_supervisor_names=base.all_supervisor_names,
        valid_shared_roots=valid_shared_roots,
        classifier_labels=classifier_labels,
    )


@st.cache_resource(show_spinner=False)
def _load_base_app_data(db_signature: DbSignature) -> BaseAppData:
    """Загружает общие данные приложения только для чтения на процесс Streamlit."""
    with perf_timer("app.base_data.read_metadata"):
        df = read_dissertation_metadata()

    missing = [c for c in [AUTHOR_COLUMN, *SUPERVISOR_COLUMNS] if c not in df.columns]
    if missing:
        raise KeyError("Отсутствуют нужные колонки: " + ", ".join(f"`{c}`" for c in missing))

    with perf_timer("app.base_data.build_index"):
        idx = build_index(df, SUPERVISOR_COLUMNS)
    with perf_timer("app.base_data.collect_supervisors"):
        names: set[str] = set()
        for col in SUPERVISOR_COLUMNS:
            names.update({v for v in df[col].dropna().astype(str).unique() if v})

    return BaseAppData(
        db_signature=db_signature,
        df=df,
        idx=idx,
        all_supervisor_names=frozenset(names),
    )
