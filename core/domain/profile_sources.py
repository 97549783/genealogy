from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProfileSourceId = Literal["pedagogy_5_8", "it_2_3"]
DEFAULT_PROFILE_SOURCE_ID: ProfileSourceId = "pedagogy_5_8"


@dataclass(frozen=True)
class ProfileSource:
    id: str
    label: str
    short_label: str
    score_table: str
    key_column: str
    classifier_id: str
    new_vak_codes: tuple[str, ...]
    old_vak_codes: tuple[str, ...]
    default_science_field_ids: tuple[str, ...]
    query_param_value: str


PROFILE_SOURCES: dict[str, ProfileSource] = {
    "pedagogy_5_8": ProfileSource(
        id="pedagogy_5_8",
        label="Педагогические науки — 5.8.x / 13.00.xx",
        short_label="Педагогические науки",
        score_table="diss_scores_5_8",
        key_column="Code",
        classifier_id="pedagogy_5_8",
        new_vak_codes=("5.8",),
        old_vak_codes=("13.00",),
        default_science_field_ids=("pedagogy",),
        query_param_value="pedagogy_5_8",
    ),
    "it_2_3": ProfileSource(
        id="it_2_3",
        label="Информационные технологии — 2.3.x / 05.13.xx",
        short_label="Информационные технологии",
        score_table="diss_scores_2_3",
        key_column="Code",
        classifier_id="it_2_3",
        new_vak_codes=("2.3",),
        old_vak_codes=("05.13",),
        default_science_field_ids=("technical", "phys_math"),
        query_param_value="it_2_3",
    ),
}

PROFILE_SUMMARY_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "pedagogy_5_8": (
        ("1.1.1", "🎓 Уровень образования"),
        ("1.1.2", "🔬 Область знания"),
    ),
    "it_2_3": (
        ("1", "1. Объект исследования и предметная область"),
        ("2", "2. Методы, технологии и процессы"),
        ("3", "3. Результаты и целевые характеристики"),
    ),
}


def get_default_profile_source_id() -> str:
    return DEFAULT_PROFILE_SOURCE_ID


def get_profile_source(source_id: str | None = None) -> ProfileSource:
    if not source_id:
        return PROFILE_SOURCES[DEFAULT_PROFILE_SOURCE_ID]
    source = PROFILE_SOURCES.get(str(source_id).strip())
    if source is None:
        return PROFILE_SOURCES[DEFAULT_PROFILE_SOURCE_ID]
    return source


def get_profile_source_options() -> list[ProfileSource]:
    return [PROFILE_SOURCES["pedagogy_5_8"], PROFILE_SOURCES["it_2_3"]]


def get_profile_summary_groups(source_id: str | None = None) -> tuple[tuple[str, str], ...]:
    source = get_profile_source(source_id)
    return PROFILE_SUMMARY_GROUPS[source.id]
