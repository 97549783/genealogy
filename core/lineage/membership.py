"""Кэширование состава и деревьев научных школ."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import networkx as nx

from core.lineage.graph import is_candidate, is_doctor, lineage, rows_for, subset_by_codes, subset_codes
from core.lineage.names import norm, variants


def _norm_initials(s: str) -> str:
    s = str(s).lower().replace("ё", "е")
    s = " ".join(s.split())
    prev = None
    while prev != s:
        prev = s
        s = __import__("re").sub(r"([а-яеa-z])\. ([а-яеa-z]\.)", r"\1.\2", s)
    return s


@st.cache_data(show_spinner=False)
def _roots_cached(db_signature: tuple[str, float, int], df: pd.DataFrame) -> list[str]:
    """Возвращает кэшированный список корней научных школ."""
    _ = db_signature
    raw = set()
    for col in ["supervisors_1.name", "supervisors_2.name"]:
        if col in df.columns:
            raw.update(str(v).strip() for v in df[col].dropna().unique() if str(v).strip())
    groups = {}
    for name in raw:
        key = _norm_initials(name)
        best = groups.get(key)
        if best is None or len(name) > len(best) or (len(name) == len(best) and name < best):
            groups[key] = name
    return sorted(groups.values())


def get_cached_roots(df: pd.DataFrame, db_signature: tuple[str, float, int]) -> list[str]:
    return _roots_cached(db_signature, df)


@st.cache_data(show_spinner=False)
def _member_codes_cached(db_signature, df, idx, root: str, scope: str) -> list[str]:
    """Возвращает кэшированный список Code для школы."""
    _ = db_signature
    if scope == 'direct':
        subset = rows_for(df, idx, root)
    elif scope == 'all':
        _, subset = lineage(df, idx, root)
    else:
        raise ValueError("Неизвестная область школы. Допустимо: direct или all.")
    return subset_codes(subset)


def get_school_member_codes(df, idx, root, scope, db_signature):
    return _member_codes_cached(db_signature, df, idx, root, scope)


def get_school_subset(df, idx, root, scope, db_signature):
    codes = get_school_member_codes(df, idx, root, scope, db_signature)
    return subset_by_codes(df, codes)


@st.cache_data(show_spinner=False)
def _lineage_cached(db_signature, df, idx, root, first_level_filter_name):
    """Возвращает кэшированное дерево научной школы."""
    _ = db_signature
    filters = {None: None, 'doctors': is_doctor, 'candidates': is_candidate}
    if first_level_filter_name not in filters:
        raise ValueError("Неизвестный фильтр дерева.")
    return lineage(df, idx, root, first_level_filter=filters[first_level_filter_name])


def get_school_lineage(df, idx, root, first_level_filter_name, db_signature) -> tuple[nx.DiGraph, pd.DataFrame]:
    return _lineage_cached(db_signature, df, idx, root, first_level_filter_name)
