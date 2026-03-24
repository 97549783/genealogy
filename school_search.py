"""
Модуль вычислительной логики для вкладки «Поиск научных школ».

Содержит функции для ранжирования всех научных школ базы по различным критериям:

Группа 1 — По размеру школы:
    - search_by_total_members      — общее число членов
    - search_by_members_in_period  — число защит за период (год от / год до)
    - search_by_members_in_year    — число защит за конкретный год
    - search_by_depth              — глубина дерева (число поколений)
    - search_by_supervisor_rate    — доля учеников, ставших научными руководителями

Группа 2 — По географии:
    - search_by_city               — число защит в указанном городе (нечёткий поиск)
    - search_by_geo_diversity      — географическое разнообразие (уникальных городов)

Группа 3 — По организациям (три отдельных режима):
    - search_by_institution_prepared  — организация выполнения
    - search_by_defense_location      — место (организация) защиты
    - search_by_leading_organization  — ведущая организация

Группа 4 — По тематике:
    - search_by_classifier_score   — средний балл по узлу классификатора

Группа 5 — По персонам:
    - search_by_opponent           — школы, где лицо выступает оппонентом
    - search_by_member             — школы, в которых лицо является учеником

Вспомогательные функции:
    - get_all_roots                — список всех уникальных научных руководителей
    - collect_subset               — сбор подмножества диссертаций школы
    - build_result_row             — формирование строки итоговой таблицы
    - build_excel_search_results   — Excel-отчёт по результатам поиска

Модуль не импортирует streamlit и не содержит UI-кода.
"""

from __future__ import annotations

import io
import re
from collections import deque
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS = ["supervisors_1.name", "supervisors_2.name"]
OPPONENT_COLUMNS = ["opponents_1.name", "opponents_2.name", "opponents_3.name"]

YEAR_COLUMN = "year"
CITY_COLUMN = "city"
INSTITUTION_PREPARED_COLUMN = "institution_prepared"
DEFENSE_LOCATION_COLUMN = "defense_location"
LEADING_ORG_COLUMN = "leading_organization"
SCORES_CODE_COLUMN = "Code"
FUZZY_THRESHOLD = 75

SearchRow = Dict

# ---------------------------------------------------------------------------
# Нормализация строк
# ---------------------------------------------------------------------------


def _norm_initials(s: str) -> str:
    """
    Канонизирует строку для нечёткого поиска (не для дедубликации):
      - нижний регистр, ё→е, схлопывание пробелов
      - убирает пробел между однобуквенными инициалами: «Е. А.» → «е.а.»
    """
    s = s.lower().replace('ё', 'е')
    s = re.sub(r'\s+', ' ', s).strip()
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'([а-яеa-z])\. ([а-яеa-z]\.)', r'\1.\2', s)
    return s


def _person_key(name: str) -> Optional[Tuple[str, str, str]]:
    """
    Извлекает ключ (фамилия, инициал_имени, инициал_отчества) для дедубликации.

    Поддерживает два формата:
      - «Фамилия И.О.»   / «Фамилия И. О.»  — инициальный формат
      - «Фамилия Имя Отчество»             — полный формат

    Возвращает None, если нельзя распознать структуру.
    Все части приводятся к нижнему регистру, ё→е.

    Примеры:
      _person_key("Рожков М. И.")           → ("рожков", "м", "и")
      _person_key("Рожков М.И.")            → ("рожков", "м", "и")
      _person_key("Рожков Михаил Иосифович") → ("рожков", "м", "и")
      _person_key("Третьяков Пётр Иванович")  → ("третьяков", "п", "и")
      _person_key("Третьяков П. И.")          → ("третьяков", "п", "и")
    """
    s = name.strip().lower().replace('ё', 'е')
    # Убираем лишние пробелы
    s = re.sub(r'\s+', ' ', s).strip()
    parts = s.split()
    if len(parts) < 2:
        return None

    surname = parts[0]
    rest = parts[1:]  # всё после фамилии

    # Соединяем остаток и убираем все пробелы/точки чтобы получить чистые буквы
    rest_joined = ''.join(rest).replace('.', '')

    if len(rest_joined) == 0:
        return None

    if len(rest_joined) <= 2:
        # Инициальный формат: "MИ" или "М" (только имя)
        first_i = rest_joined[0]
        patr_i = rest_joined[1] if len(rest_joined) > 1 else ""
    else:
        # Полный формат: берём первую букву каждого слова
        words = [w for w in rest if re.sub(r'[^\u0430-яеa-z]', '', w)]
        if len(words) == 0:
            return None
        first_i = words[0][0] if words[0] else ""
        patr_i = words[1][0] if len(words) > 1 and words[1] else ""

    if not first_i:
        return None

    return (surname, first_i, patr_i)


# ---------------------------------------------------------------------------
# Дедубликация результатов на финальном этапе
# ---------------------------------------------------------------------------


def _dedup_result_df(df: pd.DataFrame, metric_col: str) -> pd.DataFrame:
    """
    Схлопывает строки результирующей таблицы, которые относятся к одному
    руководителю (разные варианты написания).

    Ключ дедубликации = _person_key("Руководитель") = (фамилия, инициал_имени, инициал_отчества).
    Например, "Рожков М. И.", "Рожков М.И.", "Рожков Михаил Иосифович" — все дают ("рожков", "м", "и").
    Если ключ вычислить невозможно, фоллбэк — _norm_initials.

    Для каждой группы:
      - "Руководитель" → самое длинное имя (полное ФИО > инициалы)
      - числовая метрика → сумма по группе
      - "Всего членов" и др. числовые колонки → также сумма
      - строковые колонки → из строки с самым длинным именем
    """
    if df.empty or "Руководитель" not in df.columns:
        return df

    df = df.copy()

    # Вычисляем ключ дедубликации
    def _key(name: str) -> str:
        pk = _person_key(name)
        if pk is not None:
            return str(pk)  # e.g. "('\u0440\u043e\u0436\u043a\u043e\u0432', '\u043c', '\u0438')"
        return _norm_initials(name)  # фоллбэк

    df["_dedup_key"] = df["Руководитель"].astype(str).map(_key)
    df["_name_len"] = df["Руководитель"].str.len()

    # Сортируем: внутри каждой группы — самое длинное имя первым
    df = df.sort_values(["_dedup_key", "_name_len"], ascending=[True, False])

    metric_is_numeric = (
        pd.api.types.is_numeric_dtype(df[metric_col])
        if metric_col in df.columns else False
    )

    result_rows = []
    for _key_val, group in df.groupby("_dedup_key", sort=False):
        best = group.iloc[0].to_dict()
        if len(group) > 1:
            if metric_is_numeric:
                best[metric_col] = int(group[metric_col].sum())
            for num_col in (
                "Всего членов", "Уникальных городов",
                "Таких учеников", "Прямых учеников",
                "Диссертаций с оценками",
            ):
                if num_col in group.columns and num_col != metric_col:
                    best[num_col] = int(group[num_col].sum())
        result_rows.append(best)

    result = pd.DataFrame(result_rows).drop(
        columns=["_dedup_key", "_name_len"], errors="ignore"
    )
    result = result.reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _safe_year(val) -> Optional[int]:
    try:
        y = int(float(str(val).strip()))
        if 1900 < y < 2100:
            return y
    except (ValueError, TypeError):
        pass
    return None


def _years_series(subset: pd.DataFrame) -> pd.Series:
    if YEAR_COLUMN not in subset.columns or subset.empty:
        return pd.Series(dtype=int)
    return subset[YEAR_COLUMN].dropna().map(_safe_year).dropna().astype(int)


def _year_range_str(subset: pd.DataFrame) -> str:
    years = _years_series(subset)
    if years.empty:
        return "—"
    return f"{int(years.min())}–{int(years.max())}"


def _unique_cities(subset: pd.DataFrame) -> int:
    if CITY_COLUMN not in subset.columns or subset.empty:
        return 0
    return int(
        subset[CITY_COLUMN].dropna().astype(str).str.strip()
        .pipe(lambda s: s[s != ""]).nunique()
    )


# ---------------------------------------------------------------------------
# Получение списка всех корней
# ---------------------------------------------------------------------------


def get_all_roots(df: pd.DataFrame) -> List[str]:
    """
    Возвращает все варианты написания руководителей.
    Дедубликация происходит на финальном этапе (в _dedup_result_df).
    """
    roots: Set[str] = set()
    for col in SUPERVISOR_COLUMNS:
        if col in df.columns:
            roots.update(
                str(v).strip()
                for v in df[col].dropna().unique()
                if str(v).strip()
            )
    return sorted(roots)


# ---------------------------------------------------------------------------
# Сбор подмножества
# ---------------------------------------------------------------------------


def collect_subset(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    scope: str,
    lineage_func: Callable,
    rows_for_func: Callable,
) -> pd.DataFrame:
    if scope == "direct":
        return rows_for_func(df, index, root)
    else:
        _graph, subset = lineage_func(df, index, root)
        return subset


# ---------------------------------------------------------------------------
# Формирование строки
# ---------------------------------------------------------------------------


def build_result_row(
    rank: int,
    root: str,
    metric_value,
    subset: pd.DataFrame,
    metric_label: str,
) -> SearchRow:
    return {
        "#": rank,
        "Руководитель": root,
        metric_label: metric_value,
        "Всего членов": len(subset),
        "Годы активности": _year_range_str(subset),
        "Уникальных городов": _unique_cities(subset),
    }


# ---------------------------------------------------------------------------
# Нечёткий поиск
# ---------------------------------------------------------------------------


def _fuzzy_match(series: pd.Series, query: str) -> pd.Series:
    query_norm = _norm_initials(query.strip())
    norm_series = series.astype(str).map(_norm_initials)
    mask_contains = norm_series.str.contains(query_norm, na=False, regex=False)
    try:
        from rapidfuzz import fuzz  # type: ignore
        def _ratio(val: str) -> bool:
            return fuzz.partial_ratio(query_norm, val) >= FUZZY_THRESHOLD
        mask_fuzzy = norm_series.map(_ratio)
        return mask_contains | mask_fuzzy
    except ImportError:
        return mask_contains


def _fuzzy_count(subset: pd.DataFrame, col: str, query: str) -> Tuple[int, List[str]]:
    if col not in subset.columns or subset.empty:
        return 0, []
    col_series = subset[col].dropna().astype(str).str.strip()
    col_series = col_series[col_series != ""]
    mask = _fuzzy_match(col_series, query)
    matched_vals = col_series[mask].unique().tolist()
    full_mask = _fuzzy_match(subset[col].fillna("").astype(str), query)
    return int(full_mask.sum()), matched_vals


# ---------------------------------------------------------------------------
# ГРУППА 1
# ---------------------------------------------------------------------------


def search_by_total_members(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        count = len(subset)
        if count == 0:
            continue
        rows.append(build_result_row(0, root, count, subset, "Число членов"))
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Число членов")
    result = result.sort_values("Число членов", ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


def search_by_members_in_period(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    year_from: int,
    year_to: int,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty:
            continue
        years = _years_series(subset)
        if years.empty:
            count_in_period = 0
        else:
            year_idx = subset[YEAR_COLUMN].dropna().map(_safe_year).dropna()
            count_in_period = int(year_idx.between(year_from, year_to).sum())
        if count_in_period == 0:
            continue
        rows.append(build_result_row(0, root, count_in_period, subset, "Защит за период"))
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Защит за период")
    result = result.sort_values("Защит за период", ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


def search_by_members_in_year(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    year: int,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    metric = f"Защит в {year} г."
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty or YEAR_COLUMN not in subset.columns:
            continue
        year_vals = subset[YEAR_COLUMN].dropna().map(_safe_year).dropna()
        count = int((year_vals == year).sum())
        if count == 0:
            continue
        rows.append(build_result_row(0, root, count, subset, metric))
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, metric)
    result = result.sort_values(metric, ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


def search_by_depth(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    top_n: int = 10,
) -> pd.DataFrame:
    try:
        import networkx as nx
    except ImportError:
        return pd.DataFrame(columns=["#", "Руководитель", "Поколений", "Всего членов",
                                      "Годы активности", "Уникальных городов"])
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    for root in roots:
        graph, subset = lineage_func(df, index, root)
        if graph.number_of_nodes() < 2:
            continue
        depth = 0
        if nx.is_directed_acyclic_graph(graph):
            q: deque = deque([(root, 0)])
            seen: Set[str] = {root}
            while q:
                node, d = q.popleft()
                if d > depth:
                    depth = d
                for child in graph.successors(node):
                    if child not in seen:
                        seen.add(child)
                        q.append((child, d + 1))
        if depth == 0:
            continue
        rows.append(build_result_row(0, root, depth, subset, "Поколений"))
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Поколений")
    result = result.sort_values("Поколений", ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


def search_by_supervisor_rate(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    for root in roots:
        subset_direct = rows_for_func(df, index, root)
        if subset_direct.empty or AUTHOR_COLUMN not in subset_direct.columns:
            continue
        direct_count = len(subset_direct)
        supervisor_count = 0
        for name in subset_direct[AUTHOR_COLUMN].dropna().astype(str).unique():
            name = name.strip()
            if not name:
                continue
            if not rows_for_func(df, index, name).empty:
                supervisor_count += 1
        if direct_count == 0:
            continue
        rate = round(100.0 * supervisor_count / direct_count, 1)
        subset_full = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        row = build_result_row(0, root, f"{rate}%", subset_full, "Доля учеников-руководителей, %")
        row["Таких учеников"] = supervisor_count
        row["Прямых учеников"] = direct_count
        rows.append(row)
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Доля учеников-руководителей, %")
    result = result.sort_values(
        "Доля учеников-руководителей, %",
        key=lambda s: s.astype(str).str.replace("%", "", regex=False).apply(
            lambda x: float(x) if x.replace(".", "", 1).isdigit() else 0.0
        ),
        ascending=False,
    ).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


# ---------------------------------------------------------------------------
# ГРУППА 2
# ---------------------------------------------------------------------------


def search_by_city(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    city_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty:
            continue
        count, matched_vals = _fuzzy_count(subset, CITY_COLUMN, city_query)
        if count == 0:
            continue
        matched_map[root] = matched_vals
        row = build_result_row(0, root, count, subset, "Защит в городе")
        row["Найденные варианты"] = "; ".join(matched_vals)
        rows.append(row)
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Защит в городе")
    result = result.sort_values("Защит в городе", ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result, matched_map


def search_by_geo_diversity(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        n_cities = _unique_cities(subset)
        if n_cities == 0:
            continue
        rows.append(build_result_row(0, root, n_cities, subset, "Уникальных городов"))
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Уникальных городов")
    result = result.sort_values("Уникальных городов", ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


# ---------------------------------------------------------------------------
# ГРУППА 3
# ---------------------------------------------------------------------------


def _search_by_org_column(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    org_query: str,
    org_column: str,
    metric_label: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty:
            continue
        count, matched_vals = _fuzzy_count(subset, org_column, org_query)
        if count == 0:
            continue
        matched_map[root] = matched_vals
        row = build_result_row(0, root, count, subset, metric_label)
        row["Найденные варианты"] = "; ".join(matched_vals)
        rows.append(row)
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, metric_label)
    result = result.sort_values(metric_label, ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result, matched_map


def search_by_institution_prepared(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    org_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    return _search_by_org_column(
        df, index, lineage_func, rows_for_func,
        org_query=org_query, org_column=INSTITUTION_PREPARED_COLUMN,
        metric_label="Диссертаций (орг. выполнения)",
        scope=scope, top_n=top_n,
    )


def search_by_defense_location(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    org_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    return _search_by_org_column(
        df, index, lineage_func, rows_for_func,
        org_query=org_query, org_column=DEFENSE_LOCATION_COLUMN,
        metric_label="Диссертаций (место защиты)",
        scope=scope, top_n=top_n,
    )


def search_by_leading_organization(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    org_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    return _search_by_org_column(
        df, index, lineage_func, rows_for_func,
        org_query=org_query, org_column=LEADING_ORG_COLUMN,
        metric_label="Диссертаций (вед. организация)",
        scope=scope, top_n=top_n,
    )


# ---------------------------------------------------------------------------
# ГРУППА 4
# ---------------------------------------------------------------------------


def _is_child_of(code: str, parent: str) -> bool:
    return code == parent or code.startswith(parent + ".")


def search_by_classifier_score(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    classifier_node: str,
    scores_folder: str,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    base = Path(scores_folder).expanduser().resolve()
    files = sorted(base.glob("*.csv"))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frame = pd.read_csv(f)
            if SCORES_CODE_COLUMN in frame.columns:
                frames.append(frame)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    scores = pd.concat(frames, ignore_index=True)
    scores = scores.dropna(subset=[SCORES_CODE_COLUMN])
    scores[SCORES_CODE_COLUMN] = scores[SCORES_CODE_COLUMN].astype(str).str.strip()
    scores = scores[scores[SCORES_CODE_COLUMN].str.len() > 0]
    scores = scores.drop_duplicates(subset=[SCORES_CODE_COLUMN], keep="first")
    feature_cols = [c for c in scores.columns if c != SCORES_CODE_COLUMN]
    scores[feature_cols] = scores[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    node_features = [col for col in feature_cols if _is_child_of(col, classifier_node) or col == classifier_node]
    if not node_features:
        return pd.DataFrame()
    scores_indexed = scores.set_index(SCORES_CODE_COLUMN)
    metric_label = f"Средний балл ({classifier_node})"
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty or SCORES_CODE_COLUMN not in subset.columns:
            continue
        school_codes = (
            subset[SCORES_CODE_COLUMN].dropna().astype(str).str.strip()
            .pipe(lambda s: s[s != ""]).unique()
        )
        if len(school_codes) == 0:
            continue
        matched_scores = scores_indexed.loc[
            scores_indexed.index.intersection(school_codes), node_features
        ]
        if matched_scores.empty:
            continue
        avg = float(matched_scores.values.mean())
        row = build_result_row(0, root, round(avg, 3), subset, metric_label)
        row["Диссертаций с оценками"] = len(matched_scores)
        rows.append(row)
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, metric_label)
    result = result.sort_values(metric_label, ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result


# ---------------------------------------------------------------------------
# ГРУППА 5
# ---------------------------------------------------------------------------


def search_by_opponent(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    person_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty:
            continue
        total_count = 0
        all_matched: Set[str] = set()
        for col in OPPONENT_COLUMNS:
            count, matched_vals = _fuzzy_count(subset, col, person_query)
            total_count += count
            all_matched.update(matched_vals)
        if total_count > 0:
            combined_mask = pd.Series(False, index=subset.index)
            for col in OPPONENT_COLUMNS:
                if col in subset.columns:
                    combined_mask = combined_mask | _fuzzy_match(
                        subset[col].fillna("").astype(str), person_query
                    )
            row_count = int(combined_mask.sum())
            if row_count == 0:
                continue
            matched_map[root] = sorted(all_matched)
            row = build_result_row(0, root, row_count, subset, "Диссертаций с оппонентом")
            row["Найденные варианты"] = "; ".join(sorted(all_matched))
            rows.append(row)
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Диссертаций с оппонентом")
    result = result.sort_values("Диссертаций с оппонентом", ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result, matched_map


def search_by_member(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    person_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}
    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty or AUTHOR_COLUMN not in subset.columns:
            continue
        count, matched_vals = _fuzzy_count(subset, AUTHOR_COLUMN, person_query)
        if count == 0:
            continue
        matched_map[root] = matched_vals
        row = build_result_row(0, root, count, subset, "Диссертаций автора")
        row["Найденные варианты"] = "; ".join(matched_vals)
        rows.append(row)
    result = pd.DataFrame(rows)
    result = _dedup_result_df(result, "Диссертаций автора")
    result = result.sort_values("Диссертаций автора", ascending=False).head(top_n).reset_index(drop=True)
    result["#"] = range(1, len(result) + 1)
    return result, matched_map


# ---------------------------------------------------------------------------
# Excel-отчёт
# ---------------------------------------------------------------------------


def build_excel_search_results(
    result_df: pd.DataFrame,
    search_mode: str,
    search_params: Dict,
) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        if not result_df.empty:
            result_df.to_excel(writer, index=False, sheet_name="Результаты")
        meta_rows = [("Режим поиска", search_mode)]
        for k, v in search_params.items():
            meta_rows.append((str(k), str(v)))
        meta_df = pd.DataFrame(meta_rows, columns=["Параметр", "Значение"])
        meta_df.to_excel(writer, index=False, sheet_name="Параметры запроса")
    return buf.getvalue()
