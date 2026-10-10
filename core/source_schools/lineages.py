"""Сопоставление представителей источниковой школы с руководителями в базе."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from core.db import SUPERVISOR_COLUMNS
from core.lineage.graph import rows_for
from core.lineage.names import has_expanded_name, norm
from .presentation import get_first_field


@dataclass(frozen=True)
class SourcePersonLineage:
    """Хранит точное имя корня из базы и число записей непосредственного руководства."""

    root_name: str
    record_count: int


def source_person_name_candidates(name: str) -> tuple[str, ...]:
    """Учитывает порядок ФИО и явно указанную в скобках другую фамилию."""
    aliases = re.findall(r"\(([^()]*)\)", name)
    plain = re.sub(r"\([^()]*\)", "", name).strip()
    parts = plain.split()
    candidates = [plain]
    if len(parts) >= 2:
        candidates.append(" ".join([parts[-1], *parts[:-1]]))
        for alias in aliases:
            if len(alias.split()) == 1:
                candidates.append(" ".join([alias, *parts[:-1]]))
    return tuple(dict.fromkeys(candidate for candidate in candidates if has_expanded_name(candidate)))


def resolve_source_school_lineages(
    document: Mapping[str, Any], df: pd.DataFrame, idx: dict,
) -> dict[str, SourcePersonLineage]:
    """Разрешает только однозначные совпадения развёрнутых имён с существующими связями."""
    names_by_key: dict[str, set[str]] = {}
    for column in SUPERVISOR_COLUMNS:
        if column in df:
            for raw in df[column].dropna().astype(str).unique():
                name = raw.strip()
                if name and has_expanded_name(name):
                    names_by_key.setdefault(norm(name), set()).add(name)
    links: dict[str, SourcePersonLineage] = {}
    for person in document.get("школа", {}).get("персоны", []):
        display_name = str(get_first_field(person, "полное_имя", "имя")).strip()
        matched_keys = {
            norm(candidate)
            for candidate in source_person_name_candidates(display_name)
            if norm(candidate) in names_by_key
        }
        if len(matched_keys) != 1:
            continue
        root = sorted(names_by_key[next(iter(matched_keys))])[0]
        records = rows_for(df, idx, root)
        count = records["Code"].nunique() if "Code" in records else len(records)
        if count:
            links[str(person["id"])] = SourcePersonLineage(root_name=root, record_count=int(count))
    return links


@st.cache_data(show_spinner=False)
def _cached_source_school_lineages(db_signature, people: tuple[tuple[str, str], ...], _df, _idx):
    document = {"школа": {"персоны": [{"id": person_id, "имя": name} for person_id, name in people]}}
    return resolve_source_school_lineages(document, _df, _idx)


def get_source_school_lineages(document, df, idx, db_signature) -> dict[str, SourcePersonLineage]:
    """Повторно использует сопоставление до изменения базы или списка персон."""
    people = tuple(
        (str(person["id"]), str(get_first_field(person, "полное_имя", "имя")))
        for person in document["школа"]["персоны"]
    )
    return _cached_source_school_lineages(db_signature, people, df, idx)
