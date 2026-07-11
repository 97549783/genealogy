from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set

import pandas as pd
import streamlit as st

from core.app.context import DbSignature, LineageContextKey
from core.domain.science_fields import filter_df_by_science_fields
from core.lineage.graph import build_index
from core.people import get_unique_supervisors
from core.ui.filters import (
    hydrate_science_fields_from_query_params,
    render_science_field_filter,
    science_field_filter_caption,
)


class ComparableTuple(tuple):
    def __eq__(self, other):
        if isinstance(other, list):
            return list(self) == other
        return super().__eq__(other)


@dataclass(frozen=True)
class FilteredLineageContext:
    df: pd.DataFrame
    idx: Dict[str, Set[int]]
    all_supervisor_names: tuple[str, ...]
    science_field_ids: tuple[str, ...]
    cache_key: LineageContextKey


def normalize_science_field_ids(selected_ids) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in (selected_ids or []) if str(value).strip()}))


def _build_lineage_context_impl(
    *,
    df: pd.DataFrame,
    base_idx: Dict[str, Set[int]],
    db_signature: DbSignature,
    selected_ids: tuple[str, ...],
    supervisor_columns: tuple[str, ...],
) -> FilteredLineageContext:
    cache_key: LineageContextKey = (db_signature, selected_ids, supervisor_columns)
    if not selected_ids:
        supervisors = get_unique_supervisors(df, supervisor_columns=list(supervisor_columns))
        return FilteredLineageContext(df, base_idx, ComparableTuple(sorted(supervisors)), ComparableTuple(selected_ids), cache_key)
    filtered_df = filter_df_by_science_fields(df, selected_ids)
    filtered_idx = build_index(filtered_df, list(supervisor_columns))
    supervisors = get_unique_supervisors(filtered_df, supervisor_columns=list(supervisor_columns))
    return FilteredLineageContext(filtered_df, filtered_idx, ComparableTuple(sorted(supervisors)), ComparableTuple(selected_ids), cache_key)


@st.cache_resource(show_spinner=False, max_entries=4)
def _get_science_filtered_lineage_context_cached(
    db_signature: DbSignature,
    selected_ids: tuple[str, ...],
    supervisor_columns: tuple[str, ...],
    _df: pd.DataFrame,
    _base_idx: Dict[str, Set[int]],
) -> FilteredLineageContext:
    return _build_lineage_context_impl(
        df=_df,
        base_idx=_base_idx,
        db_signature=db_signature,
        selected_ids=selected_ids,
        supervisor_columns=supervisor_columns,
    )


def get_science_filtered_lineage_context(
    *,
    df,
    base_idx,
    db_signature,
    selected_ids,
    supervisor_columns,
) -> FilteredLineageContext:
    if db_signature == ("", 0.0, 0):
        db_signature = (f"__df:{id(df)}", 0.0, id(base_idx))
    return _get_science_filtered_lineage_context_cached(
        db_signature,
        normalize_science_field_ids(selected_ids),
        tuple(supervisor_columns),
        df,
        base_idx,
    )


def build_science_filtered_lineage_context(
    *,
    df: pd.DataFrame,
    selected_ids: list[str],
    supervisor_columns: list[str],
    base_idx=None,
    db_signature: DbSignature = ("", 0.0, 0),
) -> FilteredLineageContext:
    """Возвращает отфильтрованный контекст родословных без отрисовки виджетов."""
    if base_idx is None:
        base_idx = build_index(df, supervisor_columns)
    return _build_lineage_context_impl(
        df=df,
        base_idx=base_idx,
        db_signature=db_signature,
        selected_ids=normalize_science_field_ids(selected_ids),
        supervisor_columns=tuple(supervisor_columns),
    )


def render_science_filtered_lineage_context(
    *,
    df: pd.DataFrame,
    base_idx: Dict[str, Set[int]],
    db_signature: DbSignature,
    key_prefix: str,
    supervisor_columns: list[str],
    label: str = "Отрасли наук",
) -> FilteredLineageContext:
    """Рендерит фильтр отраслей наук и возвращает отфильтрованный контекст для деревьев/школ."""
    default_selected_ids = hydrate_science_fields_from_query_params()
    selected_ids = render_science_field_filter(
        key_prefix=key_prefix,
        label=label,
        default_selected_ids=default_selected_ids,
    )
    context = get_science_filtered_lineage_context(
        df=df,
        base_idx=base_idx,
        db_signature=db_signature,
        selected_ids=selected_ids,
        supervisor_columns=supervisor_columns,
    )
    st.caption(science_field_filter_caption(selected_ids))
    if selected_ids:
        st.caption(f"После фильтрации осталось диссертаций: {len(context.df)} из {len(df)}.")
    return context
