"""Общие помощники сопоставления авторов статей с участниками научных школ."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import pandas as pd
import streamlit as st

from core.db.articles import load_article_authors
from core.lineage.graph import lineage, rows_for

AUTHOR_COLUMN = "candidate_name"
_RE_MULTI_SPACE = re.compile(r"\s+")
_RE_DOTS_SPACES = re.compile(r"\s*\.\s*")
_RE_INIT_SPACES = re.compile(r"([A-Za-zА-Яа-я])\.\s+([A-Za-zА-Яа-я])\.")


@dataclass(frozen=True)
class LineageAuthorResolution:
    """Результат разрешения имени автора статьи в корень генеалогии."""

    display_name: str
    canon_key: str
    root_name: str | None
    ambiguous_full_names: tuple[str, ...]
    is_exact_match: bool


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
    """Возвращает реальные формы имён из `article_authors.Name` с каноническими ключами."""
    article_authors = load_article_authors()
    if article_authors is None or article_authors.empty or "Name" not in article_authors.columns:
        return {}
    return _author_name_display_to_canon(article_authors)


@st.cache_data(show_spinner=False)
def _extract_author_initials_from_article_authors() -> Set[str]:
    """Извлекает канонические ключи только из реальных имён `article_authors.Name`."""
    return set(_extract_author_names_from_article_authors().values())


@st.cache_data(show_spinner=False)
def compute_selectable_people(
    df_lineage: pd.DataFrame,
    include_without_descendants: bool,
) -> Tuple[List[str], Dict[str, str]]:
    """Возвращает все непустые имена авторов из `article_authors.Name`.

    Параметры генеалогии и флаг `include_without_descendants` оставлены для
    совместимости с прежними вызовами, но не участвуют в фильтрации списка.
    """
    article_author_names = _extract_author_names_from_article_authors()
    options = sorted(article_author_names.keys())
    meta = {option: "article_author" for option in options}
    return options, meta


def _lineage_full_names(df_lineage: pd.DataFrame) -> Set[str]:
    """Собирает полные ФИО людей, присутствующих в таблице генеалогии."""
    names: Set[str] = set()
    if df_lineage is None or df_lineage.empty:
        return names
    if AUTHOR_COLUMN in df_lineage.columns:
        names.update(str(v).strip() for v in df_lineage[AUTHOR_COLUMN].dropna().astype(str) if str(v).strip())
    for col in supervisor_columns(df_lineage):
        names.update(str(v).strip() for v in df_lineage[col].dropna().astype(str) if str(v).strip())
    return names


def resolve_article_author_to_lineage_root(
    selected_option: str,
    df_lineage: pd.DataFrame,
) -> LineageAuthorResolution:
    """Разрешает отображаемое имя автора статьи в корень генеалогии, если это возможно.

    Точное совпадение полного ФИО имеет приоритет над совпадениями по инициалам.
    Если краткая форма неоднозначна, корень не выбирается автоматически.
    """
    display_name = str(selected_option or "").strip()
    canon_key = canon_article_author_name(display_name)
    full_names = _lineage_full_names(df_lineage)

    if display_name in full_names:
        return LineageAuthorResolution(
            display_name=display_name,
            canon_key=canon_key,
            root_name=display_name,
            ambiguous_full_names=(),
            is_exact_match=True,
        )

    fulls = tuple(build_initials_to_fullnames(df_lineage).get(canon_key, []))
    if len(fulls) == 1:
        return LineageAuthorResolution(
            display_name=display_name,
            canon_key=canon_key,
            root_name=fulls[0],
            ambiguous_full_names=(),
            is_exact_match=False,
        )
    if len(fulls) > 1:
        return LineageAuthorResolution(
            display_name=display_name,
            canon_key=canon_key,
            root_name=None,
            ambiguous_full_names=fulls,
            is_exact_match=False,
        )
    return LineageAuthorResolution(
        display_name=display_name,
        canon_key=canon_key,
        root_name=None,
        ambiguous_full_names=(),
        is_exact_match=False,
    )


def _session_resolved_lineage_root(resolution: LineageAuthorResolution) -> str | None:
    """Возвращает выбранное пользователем ФИО для неоднозначных инициалов."""
    if not resolution.ambiguous_full_names:
        return None
    resolved = st.session_state.get("ac_disambiguation", {}).get(resolution.canon_key)
    if resolved in resolution.ambiguous_full_names:
        return resolved
    return None


def get_school_member_names(
    selected_option: str,
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    scope: str,
) -> Set[str]:
    """Возвращает имена участников школы через расчёт генеалогической линии."""
    resolution = resolve_article_author_to_lineage_root(selected_option, df_lineage)
    root_name = resolution.root_name or _session_resolved_lineage_root(resolution)
    if not root_name:
        return {resolution.display_name} if resolution.display_name else set()

    if scope == "direct":
        names = {root_name}
        rows = rows_for(df_lineage, idx_lineage, root_name)
        if not rows.empty and AUTHOR_COLUMN in rows.columns:
            names.update(
                str(value).strip()
                for value in rows[AUTHOR_COLUMN].dropna().astype(str)
                if str(value).strip()
            )
        return names

    if scope == "all":
        graph, _ = lineage(df_lineage, idx_lineage, root_name)
        if graph is None or not getattr(graph, "has_node", lambda _: False)(root_name):
            return {root_name}
        names = set(getattr(graph, "nodes")())
        names.add(root_name)
        return names

    return {root_name}


def get_source_school_excluded_initials(
    selected_option: str,
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
) -> Set[str]:
    """Возвращает ключи исходного автора и всех участников его полной школы.

    Используется, чтобы режим поиска похожих школ сравнивал исходную школу
    только с внешними авторами, а не с её внутренними подшколами.
    """
    resolution = resolve_article_author_to_lineage_root(selected_option, df_lineage)
    root_name = resolution.root_name or _session_resolved_lineage_root(resolution)
    excluded: Set[str] = {resolution.canon_key} - {""}

    if not root_name:
        return excluded

    graph, _ = lineage(df_lineage, idx_lineage, root_name)
    names = {root_name}
    if graph is not None:
        names.update(str(name).strip() for name in getattr(graph, "nodes")() if str(name).strip())

    excluded.update(
        key
        for key in (canon_initials(fio_to_short(name)) for name in names)
        if key
    )
    return excluded


def get_school_member_initials(
    selected_option: str,
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    scope: str,
) -> Set[str]:
    """Возвращает нормализованные инициалы участников выбранной школы или автора без школы."""
    resolution = resolve_article_author_to_lineage_root(selected_option, df_lineage)
    if not resolution.root_name and not _session_resolved_lineage_root(resolution):
        return {resolution.canon_key} - {""}
    return {
        canon_initials(fio_to_short(name))
        for name in get_school_member_names(selected_option, options_meta, df_lineage, idx_lineage, scope)
        if canon_initials(fio_to_short(name))
    }
