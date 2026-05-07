from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

SCIENCE_FIELD_COLUMN = "degree.science_field"


@dataclass(frozen=True)
class ScienceFieldOption:
    id: str
    label: str
    match_stems: tuple[str, ...]
    query_param_value: str


SCIENCE_FIELD_OPTIONS: dict[str, ScienceFieldOption] = {
    "pedagogy": ScienceFieldOption("pedagogy", "Педагогические науки", ("педагог",), "pedagogy"),
    "psychology": ScienceFieldOption("psychology", "Психологические науки", ("психолог",), "psychology"),
    "philosophy": ScienceFieldOption("philosophy", "Философские науки", ("философ",), "philosophy"),
    "technical": ScienceFieldOption("technical", "Технические науки", ("техник",), "technical"),
    "phys_math": ScienceFieldOption("phys_math", "Физико-математические науки", ("математ",), "phys_math"),
}


def get_science_field_options() -> list[ScienceFieldOption]:
    return [
        SCIENCE_FIELD_OPTIONS["pedagogy"],
        SCIENCE_FIELD_OPTIONS["psychology"],
        SCIENCE_FIELD_OPTIONS["philosophy"],
        SCIENCE_FIELD_OPTIONS["technical"],
        SCIENCE_FIELD_OPTIONS["phys_math"],
    ]


def normalize_science_field_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.casefold().replace("ё", "е")
    return " ".join(text.split())


def get_science_field_stem_variants(stem: str) -> tuple[str, ...]:
    normalized = normalize_science_field_text(stem)
    variants = [normalized]
    if normalized.endswith("к"):
        variants.append(normalized[:-1] + "ч")
    return tuple(dict.fromkeys(value for value in variants if value))


def science_field_matches(
    raw_value: object,
    selected_field_ids: list[str] | tuple[str, ...] | set[str] | None,
) -> bool:
    if not selected_field_ids:
        return True
    text = normalize_science_field_text(raw_value)
    if not text:
        return False
    for field_id in selected_field_ids:
        option = SCIENCE_FIELD_OPTIONS.get(str(field_id).strip())
        if option is None:
            continue
        for stem in option.match_stems:
            if any(variant in text for variant in get_science_field_stem_variants(stem)):
                return True
    return False


def filter_df_by_science_fields(
    df: pd.DataFrame,
    selected_field_ids: list[str] | tuple[str, ...] | set[str] | None,
    column: str = SCIENCE_FIELD_COLUMN,
) -> pd.DataFrame:
    if df is None or df.empty or not selected_field_ids:
        return df
    if column not in df.columns:
        return df
    mask = df[column].apply(lambda value: science_field_matches(value, selected_field_ids))
    return df[mask].copy()
