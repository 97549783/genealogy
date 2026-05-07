from __future__ import annotations

import streamlit as st

from core.domain.profile_sources import (
    ProfileSource,
    get_default_profile_source_id,
    get_profile_source,
    get_profile_source_options,
)
from core.domain.science_fields import SCIENCE_FIELD_OPTIONS, get_science_field_options


def render_profile_source_radio(
    *,
    key: str,
    label: str = "Классификатор тематических профилей",
    default_id: str | None = None,
    horizontal: bool = True,
    help: str | None = None,
) -> ProfileSource:
    options = get_profile_source_options()
    default_source = get_profile_source(default_id or get_default_profile_source_id())
    try:
        index = [source.id for source in options].index(default_source.id)
    except ValueError:
        index = 0

    selected = st.radio(
        label,
        options=options,
        index=index,
        format_func=lambda source: source.label,
        horizontal=horizontal,
        key=key,
        help=help,
    )
    return selected


def render_science_field_filter(
    *,
    key_prefix: str,
    label: str = "Отрасли наук",
    default_selected_ids: list[str] | None = None,
) -> list[str]:
    mode = st.radio(
        label,
        options=["all", "selected"],
        format_func=lambda value: "Все диссертации" if value == "all" else "Выбрать отрасли",
        horizontal=True,
        key=f"{key_prefix}_science_field_mode",
    )

    if mode == "all":
        return []

    options = get_science_field_options()
    default_selected_ids = default_selected_ids or []
    selected = st.multiselect(
        "Выберите отрасли наук",
        options=options,
        default=[option for option in options if option.id in default_selected_ids],
        format_func=lambda option: option.label,
        key=f"{key_prefix}_science_field_ids",
    )

    if not selected:
        st.warning("Выберите хотя бы одну отрасль или переключитесь на «Все диссертации».")
        return []

    return [option.id for option in selected]


def science_fields_to_query_params(selected_ids: list[str]) -> dict[str, list[str]]:
    values = [SCIENCE_FIELD_OPTIONS[field_id].query_param_value for field_id in selected_ids if field_id in SCIENCE_FIELD_OPTIONS]
    return {"science_field": values} if values else {}


def profile_source_to_query_params(source: ProfileSource) -> dict[str, str]:
    return {"profile_source": source.query_param_value}


def hydrate_science_fields_from_query_params(param_name: str = "science_field") -> list[str]:
    raw_values = st.query_params.get_all(param_name)
    allowed_by_param = {option.query_param_value: option.id for option in get_science_field_options()}
    return [allowed_by_param[value] for value in raw_values if value in allowed_by_param]


def hydrate_profile_source_from_query_params(param_name: str = "profile_source") -> str:
    raw_value = st.query_params.get(param_name)
    return get_profile_source(raw_value).id
