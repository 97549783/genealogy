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
from typing import Callable, Dict, List, Optional, Set, Tuple

import pandas as pd
from core.db import load_dissertation_scores

# ---------------------------------------------------------------------------
# Константы (должны совпадать с именами колонок в db_lineages)
# ---------------------------------------------------------------------------

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS = ["supervisors_1.name", "supervisors_2.name"]
OPPONENT_COLUMNS = ["opponents_1.name", "opponents_2.name", "opponents_3.name"]

YEAR_COLUMN = "year"
CITY_COLUMN = "city"
INSTITUTION_PREPARED_COLUMN = "institution_prepared"
DEFENSE_LOCATION_COLUMN = "defense_location"
LEADING_ORG_COLUMN = "leading_organization"

# Колонки с тематическими профилями (basic_scores)
SCORES_CODE_COLUMN = "Code"

# Порог схожести для нечёткого поиска по строкам (rapidfuzz)
FUZZY_THRESHOLD = 75

# ---------------------------------------------------------------------------
# Вспомогательные типы
# ---------------------------------------------------------------------------

# Строка результирующей таблицы поиска
SearchRow = Dict

# ---------------------------------------------------------------------------
# Нормализация строк
# ---------------------------------------------------------------------------


def _norm_initials(s: str) -> str:
    """
    Канонизирует строку с именем:
      - приводит к нижнему регистру;
      - заменяет ё → е (чтобы «Пётр» == «Петр»);
      - схлопывает лишние пробелы;
      - убирает пробел между однобуквенными инициалами с точкой:
        «Е. А.» → «е.а.», «А. Б. В.» → «а.б.в.»
    """
    s = s.lower()
    s = s.replace('ё', 'е')
    s = re.sub(r'\s+', ' ', s).strip()
    # Итеративно убираем пробел между «х. у.» (однобуквенный инициал с точкой)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'([а-яеa-z])\. ([а-яеa-z]\.)', r'\1.\2', s)
    return s


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _safe_year(val) -> Optional[int]:
    """Конвертирует значение в целый год или None."""
    try:
        y = int(float(str(val).strip()))
        if 1900 < y < 2100:
            return y
    except (ValueError, TypeError):
        pass
    return None


def _years_series(subset: pd.DataFrame) -> pd.Series:
    """Возвращает Series целых годов из subset, без NaN."""
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
        subset[CITY_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
        .pipe(lambda s: s[s != ""])
        .nunique()
    )


# ---------------------------------------------------------------------------
# Получение списка всех корней (научных руководителей)
# ---------------------------------------------------------------------------


def get_all_roots(df: pd.DataFrame) -> List[str]:
    """
    Возвращает дедублированный отсортированный список научных руководителей.

    Разные варианты написания одного человека объединяются по нормализованному
    ключу (_norm_initials). Из группы вариантов выбирается «лучший»:
    сначала самое длинное имя (полное ФИО предпочтительнее инициалов),
    при равной длине — лексикографически первое.

    Примеры объединяемых вариантов:
        «Рожков М. И.», «Рожков М.И.», «Рожков Михаил Иосифович»  → один корень
        «Третьяков П.И.», «Третьяков Пётр Иванович»               → один корень
    """
    # Собираем все сырые значения из колонок руководителей
    raw_names: Set[str] = set()
    for col in SUPERVISOR_COLUMNS:
        if col in df.columns:
            raw_names.update(
                str(v).strip()
                for v in df[col].dropna().unique()
                if str(v).strip()
            )

    # Группируем по нормализованному ключу, выбираем «лучший» вариант
    groups: Dict[str, str] = {}  # norm_key → best raw name
    for name in raw_names:
        key = _norm_initials(name)
        if key not in groups:
            groups[key] = name
        else:
            current_best = groups[key]
            # Предпочитаем более длинное имя (полное ФИО > инициалы)
            if len(name) > len(current_best) or (
                len(name) == len(current_best) and name < current_best
            ):
                groups[key] = name

    return sorted(groups.values())


# ---------------------------------------------------------------------------
# Сбор подмножества диссертаций школы
# ---------------------------------------------------------------------------


def collect_subset(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    scope: str,
    lineage_func: Callable,
    rows_for_func: Callable,
) -> pd.DataFrame:
    """
    Возвращает DataFrame диссертаций научной школы.

    scope='direct' — только прямые ученики руководителя;
    scope='all'    — все поколения (полное дерево).
    """
    if scope == "direct":
        return rows_for_func(df, index, root)
    else:
        _graph, subset = lineage_func(df, index, root)
        return subset


# ---------------------------------------------------------------------------
# Формирование строки итоговой таблицы
# ---------------------------------------------------------------------------


def build_result_row(
    rank: int,
    root: str,
    metric_value,
    subset: pd.DataFrame,
    metric_label: str,
) -> SearchRow:
    """
    Формирует словарь-строку для итоговой таблицы результатов поиска.

    Общие столбцы:
        # | Руководитель | [metric_label] | Всего членов | Годы активности | Уникальных городов
    """
    return {
        "#": rank,
        "Руководитель": root,
        metric_label: metric_value,
        "Всего членов": len(subset),
        "Годы активности": _year_range_str(subset),
        "Уникальных городов": _unique_cities(subset),
    }


# ---------------------------------------------------------------------------
# Нечёткий поиск по строке
# ---------------------------------------------------------------------------


def _fuzzy_match(series: pd.Series, query: str) -> pd.Series:
    """
    Возвращает булеву маску: True для строк, содержащих query
    (сначала простой contains, затем rapidfuzz при его наличии).

    Пробелы между инициалами нормализуются перед сравнением,
    ё и е считаются одинаковыми.
    Регистр игнорируется. Применяется к одному столбцу.
    """
    query_norm = _norm_initials(query.strip())

    # Нормализуем серию
    norm_series = series.astype(str).map(_norm_initials)

    # Быстрый проход через str.contains
    mask_contains = norm_series.str.contains(query_norm, na=False, regex=False)

    # Нечёткий проход через rapidfuzz (если доступен)
    try:
        from rapidfuzz import fuzz  # type: ignore

        def _ratio(val: str) -> bool:
            return fuzz.partial_ratio(query_norm, val) >= FUZZY_THRESHOLD

        mask_fuzzy = norm_series.map(_ratio)
        return mask_contains | mask_fuzzy
    except ImportError:
        return mask_contains


def _fuzzy_count(subset: pd.DataFrame, col: str, query: str) -> Tuple[int, List[str]]:
    """
    Считает число строк в subset, где значение колонки col совпадает с query
    (нечёткий поиск с нормализацией инициалов и ё→е).

    Возвращает:
        count   — число совпавших строк
        matched — список уникальных найденных вариантов написания (оригинальных)
    """
    if col not in subset.columns or subset.empty:
        return 0, []
    col_series = subset[col].dropna().astype(str).str.strip()
    col_series = col_series[col_series != ""]
    mask = _fuzzy_match(col_series, query)
    matched_vals = col_series[mask].unique().tolist()  # оригинальные варианты
    # Считаем по исходному subset (включая строки где col был NaN → пустая строка)
    full_mask = _fuzzy_match(
        subset[col].fillna("").astype(str), query
    )
    return int(full_mask.sum()), matched_vals


# ---------------------------------------------------------------------------
# ГРУППА 1: По размеру школы
# ---------------------------------------------------------------------------


def search_by_total_members(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Топ-N школ по общему числу членов.

    Возвращает DataFrame с колонками:
        # | Руководитель | Число членов | Всего членов | Годы активности | Уникальных городов
    """
    roots = get_all_roots(df)
    rows: List[SearchRow] = []

    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        count = len(subset)
        if count == 0:
            continue
        rows.append(build_result_row(0, root, count, subset, "Число членов"))

    rows.sort(key=lambda r: r["Число членов"], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n])


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
    """
    Топ-N школ по числу защит в диапазоне [year_from, year_to].

    Возвращает DataFrame с колонками:
        # | Руководитель | Защит за период | Всего членов | Годы активности | Уникальных городов
    """
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
            count_in_period = int(
                year_idx.between(year_from, year_to).sum()
            )
        if count_in_period == 0:
            continue
        rows.append(
            build_result_row(0, root, count_in_period, subset, "Защит за период")
        )

    rows.sort(key=lambda r: r["Защит за период"], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n])


def search_by_members_in_year(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    year: int,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Топ-N школ по числу защит в конкретный год.

    Возвращает DataFrame с колонками:
        # | Руководитель | Защит в [год] г. | Всего членов | Годы активности | Уникальных городов
    """
    roots = get_all_roots(df)
    rows: List[SearchRow] = []

    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty:
            continue
        if YEAR_COLUMN not in subset.columns:
            continue
        year_vals = subset[YEAR_COLUMN].dropna().map(_safe_year).dropna()
        count = int((year_vals == year).sum())
        if count == 0:
            continue
        rows.append(
            build_result_row(0, root, count, subset, f"Защит в {year} г.")
        )

    rows.sort(key=lambda r: r[f"Защит в {year} г."], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n])


def search_by_depth(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Топ-N школ по глубине дерева (числу поколений).

    Глубина вычисляется как максимальная длина пути от корня в BFS.
    Всегда используется scope='all'.

    Возвращает DataFrame с колонками:
        # | Руководитель | Поколений | Всего членов | Годы активности | Уникальных городов
    """
    try:
        import networkx as nx
    except ImportError:
        return pd.DataFrame(
            columns=["#", "Руководитель", "Поколений", "Всего членов",
                     "Годы активности", "Уникальных городов"]
        )

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

    rows.sort(key=lambda r: r["Поколений"], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n])


def search_by_supervisor_rate(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Топ-N школ по доле учеников, ставших научными руководителями
    (имеющих собственных учеников в базе).

    Доля вычисляется относительно прямых учеников (1-е поколение).
    Возвращает DataFrame с колонками:
        # | Руководитель | Доля учеников-руководителей, % | Таких учеников |
          Прямых учеников | Всего членов | Годы активности | Уникальных городов
    """
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
            pupils = rows_for_func(df, index, name)
            if not pupils.empty:
                supervisor_count += 1

        if direct_count == 0:
            continue

        rate = round(100.0 * supervisor_count / direct_count, 1)

        subset_full = collect_subset(
            df, index, root, scope, lineage_func, rows_for_func
        )

        row = build_result_row(0, root, f"{rate}%", subset_full,
                               "Доля учеников-руководителей, %")
        row["Таких учеников"] = supervisor_count
        row["Прямых учеников"] = direct_count
        rows.append(row)

    rows.sort(
        key=lambda r: float(str(r["Доля учеников-руководителей, %"]).replace("%", "")),
        reverse=True,
    )
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n])


# ---------------------------------------------------------------------------
# ГРУППА 2: По географии
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
    """
    Топ-N школ по числу защит в указанном городе (нечёткий поиск).

    Возвращает:
        result_df   — DataFrame с колонками:
                      # | Руководитель | Защит в городе | Найденные варианты |
                        Всего членов | Годы активности | Уникальных городов
        matched_map — словарь {root: [список найденных вариантов написания]}
    """
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

    rows.sort(key=lambda r: r["Защит в городе"], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n]), matched_map


def search_by_geo_diversity(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Топ-N школ по числу уникальных городов защит (географическое разнообразие).

    Возвращает DataFrame с колонками:
        # | Руководитель | Уникальных городов | Всего членов | Годы активности | Уникальных городов
    """
    roots = get_all_roots(df)
    rows: List[SearchRow] = []

    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        n_cities = _unique_cities(subset)
        if n_cities == 0:
            continue
        rows.append(
            build_result_row(0, root, n_cities, subset, "Уникальных городов")
        )

    rows.sort(key=lambda r: r["Уникальных городов"], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    result = pd.DataFrame(rows[:top_n])
    return result


# ---------------------------------------------------------------------------
# ГРУППА 3: По организациям
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
    """
    Внутренняя функция: топ-N школ по числу диссертаций,
    в которых в указанном org_column найдена строка org_query (нечёткий поиск).

    Возвращает:
        result_df   — DataFrame результатов
        matched_map — словарь {root: [список найденных вариантов написания]}
    """
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

    rows.sort(key=lambda r: r[metric_label], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n]), matched_map


def search_by_institution_prepared(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    org_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """
    Топ-N школ по числу диссертаций с указанной организацией выполнения.
    """
    return _search_by_org_column(
        df, index, lineage_func, rows_for_func,
        org_query=org_query,
        org_column=INSTITUTION_PREPARED_COLUMN,
        metric_label="Диссертаций (орг. выполнения)",
        scope=scope,
        top_n=top_n,
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
    """
    Топ-N школ по числу диссертаций с указанным местом (организацией) защиты.
    """
    return _search_by_org_column(
        df, index, lineage_func, rows_for_func,
        org_query=org_query,
        org_column=DEFENSE_LOCATION_COLUMN,
        metric_label="Диссертаций (место защиты)",
        scope=scope,
        top_n=top_n,
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
    """
    Топ-N школ по числу диссертаций с указанной ведущей организацией.
    """
    return _search_by_org_column(
        df, index, lineage_func, rows_for_func,
        org_query=org_query,
        org_column=LEADING_ORG_COLUMN,
        metric_label="Диссертаций (вед. организация)",
        scope=scope,
        top_n=top_n,
    )


# ---------------------------------------------------------------------------
# ГРУППА 4: По тематике
# ---------------------------------------------------------------------------


def _is_child_of(code: str, parent: str) -> bool:
    """Проверяет, является ли code дочерним (или равным) узлу parent."""
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
    """
    Топ-N школ по среднему баллу по узлу классификатора.
    """
    scores = load_dissertation_scores()
    scores = scores.dropna(subset=[SCORES_CODE_COLUMN])
    scores[SCORES_CODE_COLUMN] = scores[SCORES_CODE_COLUMN].astype(str).str.strip()
    scores = scores[scores[SCORES_CODE_COLUMN].str.len() > 0]
    scores = scores.drop_duplicates(subset=[SCORES_CODE_COLUMN], keep="first")

    feature_cols = [c for c in scores.columns if c != SCORES_CODE_COLUMN]
    scores[feature_cols] = scores[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    node_features = [
        col for col in feature_cols
        if _is_child_of(col, classifier_node) or col == classifier_node
    ]
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
            subset[SCORES_CODE_COLUMN]
            .dropna()
            .astype(str)
            .str.strip()
            .pipe(lambda s: s[s != ""])
            .unique()
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

    rows.sort(key=lambda r: r[metric_label], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n])


# ---------------------------------------------------------------------------
# ГРУППА 5: По персонам
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
    """
    Топ-N школ, в диссертациях которых указанное лицо выступает оппонентом
    (нечёткий поиск с нормализацией инициалов и ё→е по OPPONENT_COLUMNS).

    Логика подсчёта:
      - Строится объединённая булева маска по всем OPPONENT_COLUMNS (OR).
      - row_count = число уникальных диссертаций (строк), где хотя бы в одном
        столбце оппонентов найдено совпадение.
      - Это исключает двойной счёт одной диссертации при совпадении сразу
        в нескольких столбцах оппонентов.
    """
    roots = get_all_roots(df)
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}

    for root in roots:
        subset = collect_subset(df, index, root, scope, lineage_func, rows_for_func)
        if subset.empty:
            continue

        # Строим объединённую маску по всем колонкам оппонентов (OR)
        combined_mask = pd.Series(False, index=subset.index)
        all_matched: Set[str] = set()

        for col in OPPONENT_COLUMNS:
            if col not in subset.columns:
                continue
            col_series = subset[col].fillna("").astype(str)
            col_mask = _fuzzy_match(col_series, person_query)
            combined_mask = combined_mask | col_mask

            # Собираем оригинальные варианты написания из совпавших строк
            matched_vals = (
                col_series[col_mask]
                .str.strip()
                .pipe(lambda s: s[s != ""])
                .unique()
                .tolist()
            )
            all_matched.update(matched_vals)

        # row_count — число диссертаций (уникальных строк) с оппонентом
        row_count = int(combined_mask.sum())
        if row_count == 0:
            continue

        matched_map[root] = sorted(all_matched)
        row = build_result_row(0, root, row_count, subset, "Диссертаций с оппонентом")
        row["Найденные варианты"] = "; ".join(sorted(all_matched))
        rows.append(row)

    rows.sort(key=lambda r: r["Диссертаций с оппонентом"], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n]), matched_map


def search_by_member(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    person_query: str,
    scope: str = "all",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """
    Топ-N школ, в которых указанное лицо является учеником (автором диссертации)
    (нечёткий поиск с нормализацией инициалов и ё→е по AUTHOR_COLUMN).
    """
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

    rows.sort(key=lambda r: r["Диссертаций автора"], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i

    return pd.DataFrame(rows[:top_n]), matched_map


def search_member_lineage_chains(
    df: pd.DataFrame,
    person_query: str,
    max_depth: int = 25,
) -> List[Dict[str, object]]:
    """
    Ищет всех авторов диссертаций, совпадающих с person_query, и для каждого
    собирает «цепочку вверх» по научным руководителям.

    Returns:
        Список словарей формата:
        {
            "author_name": str,              # написание ФИО как в колонке автора
            "chain_names": list[str],        # автор + руководители по цепочке вверх
            "subset": pd.DataFrame,          # диссертации всех лиц из chain_names
        }
    """
    if AUTHOR_COLUMN not in df.columns:
        return []

    author_series = df[AUTHOR_COLUMN].fillna("").astype(str)
    matched_mask = _fuzzy_match(author_series, person_query)
    if not matched_mask.any():
        return []

    # Фиксируем варианты написания ровно так, как они стоят у авторов в базе.
    matched_authors = sorted(
        set(
            author_series[matched_mask]
            .str.strip()
            .loc[lambda s: s != ""]
            .tolist()
        )
    )
    if not matched_authors:
        return []

    # Нормализованное имя автора -> индексы строк с его диссертациями.
    by_author_norm: Dict[str, Set[int]] = {}
    for idx, raw in author_series.items():
        name = str(raw).strip()
        if not name:
            continue
        by_author_norm.setdefault(_norm_initials(name), set()).add(int(idx))

    results: List[Dict[str, object]] = []
    for start_name in matched_authors:
        visited: Set[str] = set()
        queue: deque[Tuple[str, int]] = deque([(start_name, 0)])
        chain_names: List[str] = []

        while queue:
            current_name, depth = queue.popleft()
            cur_key = _norm_initials(current_name)
            if not cur_key or cur_key in visited or depth > max_depth:
                continue
            visited.add(cur_key)
            chain_names.append(current_name)

            dissertation_rows = df.loc[list(by_author_norm.get(cur_key, set()))]
            if dissertation_rows.empty:
                continue

            for sup_col in SUPERVISOR_COLUMNS:
                if sup_col not in dissertation_rows.columns:
                    continue
                sup_vals = (
                    dissertation_rows[sup_col]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .loc[lambda s: s != ""]
                    .unique()
                    .tolist()
                )
                for supervisor_name in sup_vals:
                    sup_key = _norm_initials(supervisor_name)
                    if sup_key and sup_key not in visited:
                        queue.append((supervisor_name, depth + 1))

        selected_indices: Set[int] = set()
        for chain_name in chain_names:
            selected_indices.update(by_author_norm.get(_norm_initials(chain_name), set()))

        subset = (
            df.loc[sorted(selected_indices)].copy()
            if selected_indices
            else df.iloc[0:0].copy()
        )
        if YEAR_COLUMN in subset.columns:
            subset = subset.sort_values(by=YEAR_COLUMN, na_position="last")

        results.append(
            {
                "author_name": start_name,
                "chain_names": chain_names,
                "subset": subset,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Excel-отчёт по результатам поиска
# ---------------------------------------------------------------------------


def build_excel_search_results(
    result_df: pd.DataFrame,
    search_mode: str,
    search_params: Dict,
) -> bytes:
    """
    Формирует Excel-файл с результатами поиска школ.

    Параметры:
        result_df    — итоговая таблица (результат одной из функций search_by_*)
        search_mode  — название режима поиска (строка, для мета-листа)
        search_params — словарь параметров запроса (для мета-листа)

    Возвращает bytes для передачи в st.download_button.
    """
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
