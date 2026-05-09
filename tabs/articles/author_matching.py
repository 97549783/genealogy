"""Общие помощники сопоставления авторов статей с участниками научных школ."""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

import pandas as pd
import streamlit as st

from core.lineage.graph import lineage
from .comparison import load_articles_data

AUTHOR_COLUMN = "candidate_name"
_RE_MULTI_SPACE = re.compile(r"\s+")
_RE_DOTS_SPACES = re.compile(r"\s*\.\s*")
_RE_INIT_SPACES = re.compile(r"([A-Za-zА-Яа-я])\.\s+([A-Za-zА-Яа-я])\.")


def canon_initials(name: str) -> str:
    """Нормализует запись вида «Фамилия И.О.» для устойчивого сравнения."""
    if not isinstance(name, str):
        return ""
    s = name.strip()
    if not s:
        return ""
    s = _RE_MULTI_SPACE.sub(" ", s)
    s = _RE_DOTS_SPACES.sub(".", s)
    s = _RE_INIT_SPACES.sub(r"\1.\2.", s)
    s = _RE_MULTI_SPACE.sub(" ", s)
    return s.lower().replace("ё", "е")


def fio_to_short(full_name: str) -> str:
    """Преобразует полное ФИО в краткий формат «Фамилия И.О.» ."""
    if not isinstance(full_name, str):
        return ""
    s = full_name.strip().replace(".", " ")
    parts = [p for p in s.split() if p]
    if not parts:
        return ""
    initials = ""
    if len(parts) >= 2:
        initials += parts[1][0] + "."
    if len(parts) >= 3:
        initials += parts[2][0] + "."
    return f"{parts[0]} {initials}".strip()


def display_initials(canon_key: str) -> str:
    """Возвращает человекочитаемое отображение нормализованных инициалов."""
    if not isinstance(canon_key, str):
        return ""
    s = canon_key.strip()
    if not s:
        return ""
    parts = s.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0].title()
    return f"{parts[0].title()} {parts[1].upper()}".strip()


def supervisor_columns(df_lineage: pd.DataFrame) -> List[str]:
    """Находит столбцы с именами научных руководителей."""
    return [col for col in df_lineage.columns if "supervisor" in col.lower() and "name" in col.lower()]


@st.cache_data(show_spinner=False)
def build_initials_to_fullnames(df_lineage: pd.DataFrame) -> Dict[str, List[str]]:
    """Строит словарь соответствия кратких инициалов полным ФИО из генеалогии."""
    names: Set[str] = set()
    if AUTHOR_COLUMN in df_lineage.columns:
        names.update(str(v).strip() for v in df_lineage[AUTHOR_COLUMN].dropna().astype(str) if str(v).strip())
    for col in supervisor_columns(df_lineage):
        names.update(str(v).strip() for v in df_lineage[col].dropna().astype(str) if str(v).strip())
    mapping: Dict[str, List[str]] = {}
    for full in names:
        key = canon_initials(fio_to_short(full))
        if key:
            mapping.setdefault(key, [])
            if full not in mapping[key]:
                mapping[key].append(full)
    return {key: sorted(values) for key, values in mapping.items()}


def extract_authors_initials_from_articles(df_articles: pd.DataFrame) -> Set[str]:
    """Извлекает нормализованные инициалы авторов из датафрейма статей."""
    if df_articles is None or df_articles.empty or "Authors" not in df_articles.columns:
        return set()
    authors: Set[str] = set()
    for raw in df_articles["Authors"].dropna().astype(str):
        for part in re.split(r"[;]", raw):
            key = canon_initials(part)
            if key:
                authors.add(key)
    return authors


@st.cache_data(show_spinner=False)
def _extract_authors_initials_from_loaded_articles() -> Set[str]:
    return extract_authors_initials_from_articles(load_articles_data())


@st.cache_data(show_spinner=False)
def compute_selectable_people(
    df_lineage: pd.DataFrame,
    include_without_descendants: bool,
) -> Tuple[List[str], Dict[str, str]]:
    """Формирует список людей, по которым есть статьи для анализа."""
    authors_in_articles = _extract_authors_initials_from_loaded_articles()
    initials_to_full = build_initials_to_fullnames(df_lineage)

    leaders: Set[str] = set()
    for col in supervisor_columns(df_lineage):
        leaders.update(str(v).strip() for v in df_lineage[col].dropna().astype(str).unique() if str(v).strip())

    leader_options = [full for full in sorted(leaders) if canon_initials(fio_to_short(full)) in authors_in_articles]
    meta: Dict[str, str] = {option: "leader" for option in leader_options}
    if not include_without_descendants:
        return leader_options, meta

    person_no_desc = []
    for fulls in initials_to_full.values():
        for full in fulls:
            if full not in leaders and canon_initials(fio_to_short(full)) in authors_in_articles:
                person_no_desc.append(full)
    for option in sorted(set(person_no_desc)):
        meta[option] = "person_no_desc"

    initials_only: List[str] = []
    initials_ambiguous: List[str] = []
    for key in sorted(authors_in_articles):
        fulls = initials_to_full.get(key, [])
        display = display_initials(key)
        if not fulls:
            initials_only.append(display)
            meta[display] = "initials_only"
        elif len(fulls) > 1:
            initials_ambiguous.append(display)
            meta[display] = "initials_ambiguous"

    return [*leader_options, *sorted(set(person_no_desc)), *initials_only, *initials_ambiguous], meta


def get_school_member_names(
    selected_option: str,
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    scope: str,
) -> Set[str]:
    """Возвращает участников школы: корень с прямыми учениками или всю генеалогию."""
    kind = options_meta.get(selected_option, "")
    if kind not in {"leader", "person_no_desc"}:
        resolved = st.session_state.get("ac_disambiguation", {}).get(canon_initials(selected_option))
        return {resolved or selected_option}

    try:
        graph, _ = lineage(df_lineage, idx_lineage, selected_option)
    except TypeError:
        graph, _ = lineage(df_lineage, idx_lineage, selected_option)
    if graph is None or not getattr(graph, "has_node", lambda _: False)(selected_option):
        return {selected_option}
    if scope == "direct":
        names = set(getattr(graph, "successors")(selected_option))
        names.add(selected_option)
        return names
    names = set(getattr(graph, "nodes")())
    names.add(selected_option)
    return names


def get_school_member_initials(
    selected_option: str,
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    scope: str,
) -> Set[str]:
    """Возвращает нормализованные инициалы участников выбранной школы."""
    kind = options_meta.get(selected_option, "")
    if kind in {"initials_only", "initials_ambiguous"}:
        resolved = st.session_state.get("ac_disambiguation", {}).get(canon_initials(selected_option))
        if resolved:
            return {canon_initials(fio_to_short(resolved))}
        return {canon_initials(selected_option)} - {""}
    return {canon_initials(fio_to_short(name)) for name in get_school_member_names(selected_option, options_meta, df_lineage, idx_lineage, scope) if canon_initials(fio_to_short(name))}
