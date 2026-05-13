"""Общие помощники сопоставления авторов статей с участниками научных школ."""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

import pandas as pd
import streamlit as st

from core.db.articles import load_article_authors
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


def canon_article_author_name(name: str) -> str:
    """Нормализует имя из `article_authors.Name` в ключ вида «фамилия и.о.» ."""
    if not isinstance(name, str):
        return ""
    value = name.strip()
    if not value:
        return ""
    if value.count(".") >= 2 and len(value.split()) <= 2:
        return canon_initials(value)
    return canon_initials(fio_to_short(value))


def _author_name_display_to_canon(article_authors: pd.DataFrame) -> Dict[str, str]:
    """Строит отображаемые имена из `article_authors.Name` и их канонические ключи."""
    if article_authors is None or article_authors.empty or "Name" not in article_authors.columns:
        return {}
    mapping: Dict[str, str] = {}
    for raw in article_authors["Name"].dropna().astype(str):
        display = raw.strip()
        key = canon_article_author_name(display)
        if display and key and display not in mapping:
            mapping[display] = key
    return mapping


@st.cache_data(show_spinner=False)
def _extract_author_names_from_article_authors() -> Dict[str, str]:
    """Возвращает только реальные формы имён из `article_authors.Name` с каноническими ключами."""
    article_authors = load_article_authors()
    if article_authors is None or article_authors.empty or "Name" not in article_authors.columns:
        return {}

    work = article_authors.copy()
    try:
        df_articles = load_articles_data()
    except Exception:
        df_articles = pd.DataFrame()
    if df_articles is not None and not df_articles.empty and "Article_id" in df_articles.columns and "Article_id" in work.columns:
        valid_article_ids = {str(value).strip() for value in df_articles["Article_id"].dropna().astype(str) if str(value).strip()}
        work = work[work["Article_id"].astype(str).str.strip().isin(valid_article_ids)]

    return _author_name_display_to_canon(work)


@st.cache_data(show_spinner=False)
def _extract_author_initials_from_article_authors() -> Set[str]:
    """Извлекает канонические ключи только из реальных имён `article_authors.Name`."""
    return set(_extract_author_names_from_article_authors().values())


@st.cache_data(show_spinner=False)
def compute_selectable_people(
    df_lineage: pd.DataFrame,
    include_without_descendants: bool,
) -> Tuple[List[str], Dict[str, str]]:
    """Формирует список отображаемых имён строго из `article_authors.Name`."""
    article_author_names = _extract_author_names_from_article_authors()
    initials_to_full = build_initials_to_fullnames(df_lineage)

    leaders: Set[str] = set()
    for col in supervisor_columns(df_lineage):
        leaders.update(str(v).strip() for v in df_lineage[col].dropna().astype(str).unique() if str(v).strip())
    leader_keys = {canon_initials(fio_to_short(full)) for full in leaders if canon_initials(fio_to_short(full))}

    options: List[str] = []
    meta: Dict[str, str] = {}
    for display, key in sorted(article_author_names.items(), key=lambda item: item[0]):
        fulls = initials_to_full.get(key, [])
        if len(fulls) > 1:
            kind = "initials_ambiguous"
        elif key in leader_keys:
            kind = "leader"
        elif fulls:
            kind = "person_no_desc"
        else:
            kind = "initials_only"

        if kind != "leader" and not include_without_descendants:
            continue
        options.append(display)
        meta[display] = kind

    return options, meta


def _resolve_lineage_full_name(selected_option: str, df_lineage: pd.DataFrame) -> str:
    """Находит внутреннее полное ФИО из генеалогии по имени из `article_authors`."""
    key = canon_article_author_name(selected_option)
    fulls = build_initials_to_fullnames(df_lineage).get(key, [])
    if len(fulls) == 1:
        return fulls[0]
    resolved = st.session_state.get("ac_disambiguation", {}).get(key)
    if resolved:
        return resolved
    return selected_option


def get_school_member_names(
    selected_option: str,
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    scope: str,
) -> Set[str]:
    """Возвращает участников школы, внутренне разрешая имя из `article_authors` в ФИО генеалогии."""
    kind = options_meta.get(selected_option, "")
    root_name = _resolve_lineage_full_name(selected_option, df_lineage)
    if kind not in {"leader", "person_no_desc"}:
        return {root_name}

    try:
        graph, _ = lineage(df_lineage, idx_lineage, root_name)
    except TypeError:
        graph, _ = lineage(df_lineage, idx_lineage, root_name)
    if graph is None or not getattr(graph, "has_node", lambda _: False)(root_name):
        return {root_name}
    if scope == "direct":
        names = set(getattr(graph, "successors")(root_name))
        names.add(root_name)
        return names
    names = set(getattr(graph, "nodes")())
    names.add(root_name)
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
    selected_key = canon_article_author_name(selected_option)
    if kind in {"initials_only", "initials_ambiguous"}:
        resolved = st.session_state.get("ac_disambiguation", {}).get(selected_key)
        if resolved:
            return {canon_initials(fio_to_short(resolved))}
        return {selected_key} - {""}
    return {canon_initials(fio_to_short(name)) for name in get_school_member_names(selected_option, options_meta, df_lineage, idx_lineage, scope) if canon_initials(fio_to_short(name))}
