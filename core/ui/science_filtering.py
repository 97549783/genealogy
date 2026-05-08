from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

import pandas as pd
import streamlit as st

from core.domain.science_fields import filter_df_by_science_fields
from core.lineage.graph import build_index
from core.people import get_unique_supervisors
from core.ui.filters import (
    hydrate_science_fields_from_query_params,
    render_science_field_filter,
    science_field_filter_caption,
)


@dataclass(frozen=True)
class FilteredLineageContext:
    df: pd.DataFrame
    idx: Dict[str, Set[int]]
    all_supervisor_names: List[str]
    science_field_ids: list[str]


def build_science_filtered_lineage_context(
    *,
    df: pd.DataFrame,
    selected_ids: list[str],
    supervisor_columns: list[str],
) -> FilteredLineageContext:
    """Возвращает отфильтрованный контекст родословных без отрисовки виджетов."""
    filtered_df = filter_df_by_science_fields(df, selected_ids)
    filtered_idx = build_index(filtered_df, supervisor_columns)
    supervisors = get_unique_supervisors(filtered_df, supervisor_columns=supervisor_columns)
    return FilteredLineageContext(
        df=filtered_df,
        idx=filtered_idx,
        all_supervisor_names=supervisors,
        science_field_ids=selected_ids,
    )


def render_science_filtered_lineage_context(
    *,
    df: pd.DataFrame,
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

    context = build_science_filtered_lineage_context(
        df=df,
        selected_ids=selected_ids,
        supervisor_columns=supervisor_columns,
    )

    st.caption(science_field_filter_caption(selected_ids))
    if selected_ids:
        st.caption(f"После фильтрации осталось диссертаций: {len(context.df)} из {len(df)}.")

    return context
