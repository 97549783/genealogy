"""Кэширование состава и деревьев научных школ.

Все cached helpers получают полный LineageContextKey и только underscore-
аргументы для больших DataFrame/индексов. Это изолирует результаты разных
science-фильтров при одинаковой сигнатуре БД.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import networkx as nx

from core.lineage.graph import is_candidate, is_doctor, lineage, rows_for, subset_by_codes, subset_codes
from core.lineage.names import norm, variants
from core.perf import perf_timer
from core.app.context import DbSignature, LineageContextKey


def _norm_initials(s: str) -> str:
    s = str(s).lower().replace("ё", "е")
    s = " ".join(s.split())
    prev = None
    while prev != s:
        prev = s
        s = __import__("re").sub(r"([а-яеa-z])\. ([а-яеa-z]\.)", r"\1.\2", s)
    return s


@st.cache_data(show_spinner=False)
def _roots_cached(context_key: LineageContextKey, _df: pd.DataFrame) -> list[str]:
    """Возвращает кэшированный список корней научных школ."""
    df = _df
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


def _default_context_key(db_signature: DbSignature, df: pd.DataFrame | None = None, idx: dict | None = None) -> LineageContextKey:
    # Compatibility path for tests/legacy callers that have not yet supplied
    # an explicit science-filter context key. Production tab code passes a
    # stable key; here we include object ids to avoid unsafe collisions when
    # different in-memory test DataFrames reuse the same fake DB signature.
    suffix = () if df is None and idx is None else (f"__df:{id(df)}", f"__idx:{id(idx)}")
    return (db_signature, suffix, ("supervisors_1.name", "supervisors_2.name"))


def _assert_context_signature(context_key: LineageContextKey, db_signature: DbSignature) -> None:
    assert context_key[0] == db_signature


def get_cached_roots(df: pd.DataFrame, db_signature: DbSignature, *, context_key: LineageContextKey | None = None) -> list[str]:
    context_key = context_key or _default_context_key(db_signature, df=df)
    _assert_context_signature(context_key, db_signature)
    return _roots_cached(context_key, df)


def _compute_school_member_codes_uncached(
    df: pd.DataFrame,
    idx: dict,
    root: str,
    scope: str,
) -> list[str]:
    """Вычисляет список Code для одной школы без обращения к st.cache_data."""
    if scope == "direct":
        subset = rows_for(df, idx, root)
    elif scope == "all":
        _, subset = lineage(df, idx, root)
    else:
        raise ValueError("Неизвестная область школы. Допустимо: direct или all.")
    return subset_codes(subset)

@st.cache_data(show_spinner=False)
def _member_codes_cached(context_key: LineageContextKey, root: str, scope: str, _df: pd.DataFrame, _idx: dict) -> list[str]:
    """Возвращает кэшированный список Code для школы."""
    with perf_timer(f"membership.member_codes.{scope}"):
        return _compute_school_member_codes_uncached(_df, _idx, root, scope)


def get_school_member_codes(df, idx, root, scope, db_signature, *, context_key: LineageContextKey | None = None):
    context_key = context_key or _default_context_key(db_signature, df=df, idx=idx)
    _assert_context_signature(context_key, db_signature)
    return _member_codes_cached(context_key, root, scope, df, idx)


def get_school_subset(df, idx, root, scope, db_signature, *, context_key: LineageContextKey | None = None):
    context_key = context_key or _default_context_key(db_signature, df=df, idx=idx)
    codes = get_school_member_codes(df, idx, root, scope, db_signature, context_key=context_key)
    return subset_by_codes(df, codes)


@st.cache_data(show_spinner=False)
def _lineage_cached(context_key: LineageContextKey, root, first_level_filter_name, _df: pd.DataFrame, _idx: dict):
    """Возвращает кэшированное дерево научной школы."""
    filters = {None: None, 'doctors': is_doctor, 'candidates': is_candidate}
    if first_level_filter_name not in filters:
        raise ValueError("Неизвестный фильтр дерева.")
    return lineage(_df, _idx, root, first_level_filter=filters[first_level_filter_name])


def get_school_lineage(df, idx, root, first_level_filter_name, db_signature, *, context_key: LineageContextKey | None = None) -> tuple[nx.DiGraph, pd.DataFrame]:
    context_key = context_key or _default_context_key(db_signature, df=df, idx=idx)
    _assert_context_signature(context_key, db_signature)
    return _lineage_cached(context_key, root, first_level_filter_name, df, idx)


def get_all_school_member_codes(
    df: pd.DataFrame,
    idx: dict,
    scope: str,
    db_signature: tuple[str, float, int],
    *,
    context_key: LineageContextKey | None = None,
) -> dict[str, set[str]]:
    """Возвращает словарь root → множество Code для всех школ."""
    context_key = context_key or _default_context_key(db_signature, df=df, idx=idx)
    _assert_context_signature(context_key, db_signature)
    return _all_school_member_codes_cached(context_key, scope, df, idx)


@st.cache_data(show_spinner=False)
def _all_school_member_codes_cached(context_key: LineageContextKey, scope: str, _df: pd.DataFrame, _idx: dict) -> dict[str, set[str]]:
    """Возвращает кэшированные множества Code для всех школ."""
    if scope not in {"direct", "all"}:
        raise ValueError("Неизвестная область школы. Допустимо: direct или all.")
    with perf_timer(f"membership.all_school_member_codes.{scope}"):
        out: dict[str, set[str]] = {}
        roots = _roots_cached(context_key, _df)
        for root in roots:
            out[root] = set(_compute_school_member_codes_uncached(_df, _idx, root, scope))
        return out


def get_school_basic_stats(
    df: pd.DataFrame,
    idx: dict,
    scope: str,
    db_signature: tuple[str, float, int],
    *,
    context_key: LineageContextKey | None = None,
) -> dict[str, dict]:
    """Возвращает базовую статистику школ для быстрого построения результатов."""
    context_key = context_key or _default_context_key(db_signature, df=df, idx=idx)
    _assert_context_signature(context_key, db_signature)
    return _school_basic_stats_cached(context_key, scope, df, idx)


@st.cache_data(show_spinner=False)
def _school_basic_stats_cached(context_key: LineageContextKey, scope: str, _df: pd.DataFrame, _idx: dict) -> dict[str, dict]:
    """Возвращает кэшированную базовую статистику по школам."""
    with perf_timer(f"membership.school_basic_stats.{scope}"):
        codes_by_root = _all_school_member_codes_cached(context_key, scope, _df, _idx)
        by_code = _df.copy()
        if "Code" in by_code.columns:
            by_code["Code"] = by_code["Code"].astype(str).str.strip()
            by_code = by_code[by_code["Code"] != ""].drop_duplicates(subset=["Code"], keep="first").set_index("Code", drop=False)
        stats: dict[str, dict] = {}
        for root, codes in codes_by_root.items():
            valid_codes = {str(c).strip() for c in codes if str(c).strip()}
            subset = by_code.loc[by_code.index.intersection(valid_codes)] if not by_code.empty else pd.DataFrame()
            years = pd.to_numeric(subset["year"], errors="coerce").dropna().astype(int) if "year" in subset.columns else pd.Series(dtype=int)
            year_min = int(years.min()) if not years.empty else None
            year_max = int(years.max()) if not years.empty else None
            year_range = "—" if year_min is None else f"{year_min}–{year_max}"
            if "city" in subset.columns:
                n_cities = int(subset["city"].dropna().astype(str).str.strip().pipe(lambda s: s[s != ""]).nunique())
            else:
                n_cities = 0
            stats[root] = {
                "codes": valid_codes,
                "n_members": len(valid_codes),
                "year_min": year_min,
                "year_max": year_max,
                "year_range": year_range,
                "n_cities": n_cities,
            }
        return stats


def get_author_by_code(
    df: pd.DataFrame,
    db_signature: DbSignature,
    *,
    context_key: LineageContextKey | None = None,
) -> dict[str, str]:
    """Возвращает словарь Code → ФИО автора диссертации."""
    context_key = context_key or _default_context_key(db_signature, df=df)
    _assert_context_signature(context_key, db_signature)
    return _get_author_by_code_cached(context_key, df)


@st.cache_data(show_spinner=False)
def _get_author_by_code_cached(
    context_key: LineageContextKey,
    _df: pd.DataFrame,
) -> dict[str, str]:
    """Кэширует соответствие Code → ФИО автора."""
    df = _df
    if "Code" not in df.columns or "candidate_name" not in df.columns:
        return {}
    work = df[["Code", "candidate_name"]].copy()
    work["Code"] = work["Code"].astype(str).str.strip()
    work["candidate_name"] = work["candidate_name"].astype(str).str.strip()
    work = work[(work["Code"] != "") & (work["candidate_name"] != "")]
    work = work.drop_duplicates(subset=["Code"], keep="first")
    return dict(zip(work["Code"], work["candidate_name"]))


def get_supervisor_norm_set(
    idx: dict[str, set[int]],
    db_signature: DbSignature,
    *,
    context_key: LineageContextKey | None = None,
) -> set[str]:
    """Возвращает множество нормализованных имён людей, у которых есть ученики."""
    context_key = context_key or _default_context_key(db_signature, idx=idx)
    _assert_context_signature(context_key, db_signature)
    return _get_supervisor_norm_set_cached(context_key, idx)


@st.cache_data(show_spinner=False)
def _get_supervisor_norm_set_cached(
    context_key: LineageContextKey,
    _idx: dict[str, set[int]],
) -> set[str]:
    """Кэширует множество нормализованных имён руководителей."""
    return {norm(str(name)) for name, row_ids in _idx.items() if str(name).strip() and row_ids}


def is_author_supervisor(author_name: str, supervisor_norms: set[str]) -> bool:
    """Проверяет, встречается ли автор как научный руководитель."""
    name = str(author_name).strip()
    if not name:
        return False
    return any(norm(variant) in supervisor_norms for variant in variants(name))


def get_author_supervisor_flags_by_code(
    df: pd.DataFrame,
    idx: dict[str, set[int]],
    db_signature: tuple[str, float, int],
    *,
    context_key: LineageContextKey | None = None,
) -> dict[str, bool]:
    """Возвращает словарь Code → является ли автор научным руководителем."""
    context_key = context_key or _default_context_key(db_signature, df=df, idx=idx)
    _assert_context_signature(context_key, db_signature)
    return _get_author_supervisor_flags_by_code_cached(context_key, df, idx)


@st.cache_data(show_spinner=False)
def _get_author_supervisor_flags_by_code_cached(
    context_key: LineageContextKey,
    _df: pd.DataFrame,
    _idx: dict[str, set[int]],
) -> dict[str, bool]:
    """Кэширует флаги авторов, являющихся научными руководителями."""
    authors = _get_author_by_code_cached(context_key, _df)
    supervisor_norms = _get_supervisor_norm_set_cached(context_key, _idx)
    return {code: is_author_supervisor(author, supervisor_norms) for code, author in authors.items()}


def get_supervisor_rate_stats(
    df: pd.DataFrame,
    idx: dict[str, set[int]],
    db_signature: tuple[str, float, int],
    *,
    context_key: LineageContextKey | None = None,
) -> dict[str, dict]:
    """Возвращает статистику доли учеников, ставших руководителями, по всем школам."""
    context_key = context_key or _default_context_key(db_signature, df=df, idx=idx)
    _assert_context_signature(context_key, db_signature)
    return _get_supervisor_rate_stats_cached(context_key, df, idx)


@st.cache_data(show_spinner=False)
def _get_supervisor_rate_stats_cached(
    context_key: LineageContextKey,
    _df: pd.DataFrame,
    _idx: dict[str, set[int]],
) -> dict[str, dict]:
    """Кэширует статистику доли учеников-руководителей по школам."""
    direct_codes_by_root = _all_school_member_codes_cached(context_key, "direct", _df, _idx)
    flags = _get_author_supervisor_flags_by_code_cached(context_key, _df, _idx)
    out: dict[str, dict] = {}
    for root, direct_codes in direct_codes_by_root.items():
        direct = {str(code).strip() for code in direct_codes if str(code).strip()}
        supervisor_codes = {code for code in direct if flags.get(code, False)}
        direct_count = len(direct)
        supervisor_count = len(supervisor_codes)
        rate = round(100.0 * supervisor_count / direct_count, 1) if direct_count > 0 else 0.0
        out[root] = {
            "direct_count": direct_count,
            "supervisor_count": supervisor_count,
            "rate": rate,
            "supervisor_codes": supervisor_codes,
            "direct_codes": direct,
        }
    return out
