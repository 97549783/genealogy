"""
core/lineage/graph.py — построение графов научного руководства и операции над ними.

Публичный API:
    build_index(df, supervisor_cols)         -> Dict[str, Set[int]]
    rows_for(df, index, name)               -> pd.DataFrame
    lineage(df, index, root, filter)        -> (nx.DiGraph, pd.DataFrame)
    gather_school_dataset(...)              -> (pd.DataFrame, pd.DataFrame, int)
    degree_level(row)                       -> str
    is_doctor(row)                          -> bool
    is_candidate(row)                       -> bool
    slug(s)                                 -> str
    multiline(name)                         -> str

Константы:
    TREE_OPTIONS    — список стандартных типов деревьев
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Literal, Optional, Set, Tuple

import networkx as nx
import pandas as pd

from core.lineage.names import norm, variants
from core.db import AUTHOR_COLUMN, SUPERVISOR_COLUMNS


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def slug(s: str) -> str:
    """Slug-версия строки для использования в именах файлов."""
    return re.sub(r"[^A-Za-zА-Яа-я0-9]+", "_", s).strip("_")


def multiline(name: str) -> str:
    """Разбивает имя по пробелам для отображения в узлах графа."""
    return "\n".join(str(name).split())


# ---------------------------------------------------------------------------
# Индекс руководителей
# ---------------------------------------------------------------------------

def build_index(
    df: pd.DataFrame,
    supervisor_cols: List[str],
) -> Dict[str, Set[int]]:
    """
    Строит инвертированный индекс: нормализованное имя руководителя
    → множество индексов строк DataFrame, где он упомянут.
    """
    idx: Dict[str, Set[int]] = {}
    for col in supervisor_cols:
        if col not in df.columns:
            continue
        for i, raw in df[col].dropna().items():
            for v in variants(str(raw)):
                idx.setdefault(norm(v), set()).add(i)
    return idx


# ---------------------------------------------------------------------------
# Поиск строк по имени
# ---------------------------------------------------------------------------

def rows_for(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    name: str,
) -> pd.DataFrame:
    """
    Возвращает строки DataFrame, где name встречается среди руководителей
    (с учётом всех вариантов написания).
    """
    hits: Set[int] = set()
    for v in variants(name):
        hits.update(index.get(norm(v), set()))
    return df.loc[list(hits)] if hits else df.iloc[0:0]


# ---------------------------------------------------------------------------
# Степени
# ---------------------------------------------------------------------------

def degree_level(row: pd.Series) -> str:
    """Возвращает 'doctor', 'candidate' или '' по значению степени в строке."""
    raw = str(row.get("degree.degree_level", ""))
    value = raw.strip().lower()
    if value.startswith("док"):
        return "doctor"
    if value.startswith("кан"):
        return "candidate"
    return ""


def is_doctor(row: pd.Series) -> bool:
    return degree_level(row) == "doctor"


def is_candidate(row: pd.Series) -> bool:
    return degree_level(row) == "candidate"


# ---------------------------------------------------------------------------
# Типы деревьев
# ---------------------------------------------------------------------------

TREE_OPTIONS: List[Tuple[str, str, Optional[Callable[[pd.Series], bool]]]] = [
    ("Общее дерево",          "general",    None),
    ("Дерево докторов наук",  "doctors",    is_doctor),
    ("Дерево кандидатов наук", "candidates", is_candidate),
]


# ---------------------------------------------------------------------------
# Построение дерева (обход BFS)
# ---------------------------------------------------------------------------

def lineage(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    first_level_filter: Optional[Callable[[pd.Series], bool]] = None,
) -> Tuple[nx.DiGraph, pd.DataFrame]:
    """
    Строит направленный граф «научный руководитель → ученик» от root вглубь.

    first_level_filter, если задан, применяется только к первому уровню:
    ученики, не прошедшие фильтр, не включаются в граф вместе со своими
    поддеревьями.

    Возвращает:
        G      — nx.DiGraph с рёбрами руководитель → ученик
        subset — строки df, соответствующие узлам графа (кроме root)
    """
    G = nx.DiGraph()
    selected_indices: Set[int] = set()
    Q, seen = [root], set()
    while Q:
        cur = Q.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        rows = rows_for(df, index, cur)
        for idx, r in rows.iterrows():
            child = str(r.get(AUTHOR_COLUMN, "")).strip()
            if child:
                if cur == root and first_level_filter is not None:
                    if not first_level_filter(r):
                        continue
                G.add_edge(cur, child)
                Q.append(child)
                selected_indices.add(idx)
    subset = (
        df.loc[sorted(selected_indices)]
        if selected_indices
        else df.iloc[0:0]
    )
    return G, subset


# ---------------------------------------------------------------------------
# Сбор датасета научной школы для анализа
# ---------------------------------------------------------------------------

ComparisonScope = Literal["direct", "all"]


def gather_school_dataset(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    scores: pd.DataFrame,
    scope: ComparisonScope = "direct",
) -> Tuple[pd.DataFrame, pd.DataFrame, int]:
    """
    Собирает тематические профили диссертаций научной школы.

    scope='direct' — только прямые ученики;
    scope='all'    — всё дерево.

    Возвращает:
        dataset      — scores, обогащённые полем school и candidate_name
        missing_info — диссертации без профиля в scores
        total_codes  — общее число кодов в выборке
    """
    if scope == "direct":
        subset = rows_for(df, index, root)
    elif scope == "all":
        _, subset = lineage(df, index, root)
    else:
        raise ValueError(f"Неизвестный режим сравнения: {scope}")

    if subset.empty:
        empty = pd.DataFrame(columns=[*scores.columns, "school", AUTHOR_COLUMN])
        return empty, empty, 0

    working = subset[["Code", AUTHOR_COLUMN]].copy()
    working["Code"] = working["Code"].astype(str).str.strip()
    working = working[working["Code"].str.len() > 0]
    codes = working["Code"].unique().tolist()

    dataset = scores[scores["Code"].isin(codes)].copy()
    dataset["school"] = root
    dataset = dataset.merge(
        working.drop_duplicates(subset="Code"), on="Code", how="left"
    )

    missing_codes = sorted(set(codes) - set(dataset["Code"]))
    missing_info = (
        working[working["Code"].isin(missing_codes)]
        .drop_duplicates(subset="Code")
        .rename(columns={AUTHOR_COLUMN: "candidate_name"})
    )

    dataset = dataset.rename(columns={AUTHOR_COLUMN: "candidate_name"})
    if "candidate_name" not in dataset.columns:
        dataset["candidate_name"] = None

    return dataset, missing_info, len(codes)
