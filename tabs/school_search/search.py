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
from collections import deque
from typing import Callable, Dict, List, Optional, Set, Tuple

import pandas as pd
from core.db import (
    get_db_signature,
    fetch_dissertation_codes_by_year,
    fetch_dissertation_codes_by_year_range,
    fetch_dissertation_text_candidates,
    fetch_dissertation_node_score_by_codes,
)
from core.search.text_matching import FUZZY_THRESHOLD, fuzzy_match_series, normalize_text
from core.perf import perf_timer
from core.lineage.membership import (
    get_cached_roots,
    get_school_subset,
    get_school_lineage,
    get_all_school_member_codes,
    get_school_basic_stats,
    get_supervisor_rate_stats,
)

# ---------------------------------------------------------------------------
# Константы основных колонок данных диссертаций
# ---------------------------------------------------------------------------

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS = ["supervisors_1.name", "supervisors_2.name"]
OPPONENT_COLUMNS = ["opponents_1.name", "opponents_2.name", "opponents_3.name"]

YEAR_COLUMN = "year"
CITY_COLUMN = "city"
INSTITUTION_PREPARED_COLUMN = "institution_prepared"
DEFENSE_LOCATION_COLUMN = "defense_location"
LEADING_ORG_COLUMN = "leading_organization"

# Колонка ключа в таблице тематических профилей
SCORES_CODE_COLUMN = "Code"

# ---------------------------------------------------------------------------
# Вспомогательные типы
# ---------------------------------------------------------------------------

# Строка результирующей таблицы поиска
SearchRow = Dict

# ---------------------------------------------------------------------------
# Нормализация строк
# ---------------------------------------------------------------------------


def _norm_initials(s: str) -> str:
    """Нормализует строку для совместимости со старым кодом."""
    return normalize_text(s)


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
    return get_cached_roots(df, get_db_signature())


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
    _ = lineage_func, rows_for_func
    return get_school_subset(df, index, root, scope, get_db_signature())


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


def _result_row_from_stats(
    rank: int,
    root: str,
    metric_value,
    metric_label: str,
    stats: dict,
) -> SearchRow:
    """Формирует строку результата по кэшированной статистике школы."""
    return {
        "#": rank,
        "Руководитель": root,
        metric_label: metric_value,
        "Всего членов": stats["n_members"],
        "Годы активности": stats["year_range"],
        "Уникальных городов": stats["n_cities"],
    }


def _rank_by_matching_codes(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    matching_codes: set[str],
    scope: str,
    top_n: int,
    metric_label: str,
) -> pd.DataFrame:
    """Ранжирует школы по пересечению состава школы с заданным набором Code."""
    if not matching_codes:
        return pd.DataFrame()
    sig = get_db_signature()
    with perf_timer("school_search.rank_by_matching_codes.get_all_school_member_codes"):
        school_codes = get_all_school_member_codes(df, index, scope, sig)
    with perf_timer("school_search.rank_by_matching_codes.get_school_basic_stats"):
        stats = get_school_basic_stats(df, index, scope, sig)
    rows: List[SearchRow] = []
    with perf_timer("school_search.rank_by_matching_codes.rank"):
        for root, codes in school_codes.items():
            count = len(codes & matching_codes)
            if count == 0:
                continue
            rows.append(_result_row_from_stats(0, root, count, metric_label, stats[root]))
        rows.sort(key=lambda r: r[metric_label], reverse=True)
    for i, row in enumerate(rows[:top_n], 1):
        row["#"] = i
    return pd.DataFrame(rows[:top_n])


# ---------------------------------------------------------------------------
# Нечёткий поиск по строке
# ---------------------------------------------------------------------------


def _fuzzy_match(series: pd.Series, query: str) -> pd.Series:
    """Возвращает булеву маску нечёткого совпадения."""
    return fuzzy_match_series(series, query, threshold=FUZZY_THRESHOLD)


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
    with perf_timer("school_search.total_members.get_school_basic_stats"):
        stats = get_school_basic_stats(df, index, scope, get_db_signature())
    rows: List[SearchRow] = []
    for root, stat in stats.items():
        count = stat["n_members"]
        if count == 0:
            continue
        rows.append(_result_row_from_stats(0, root, count, "Число членов", stat))

    with perf_timer("school_search.total_members.rank"):
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
    with perf_timer("school_search.members_in_period.fetch_codes"):
        matching_codes = fetch_dissertation_codes_by_year_range(year_from, year_to)
    with perf_timer("school_search.members_in_period.rank_by_matching_codes"):
        return _rank_by_matching_codes(df, index, matching_codes, scope, top_n, "Защит за период")


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
    with perf_timer("school_search.members_in_year.fetch_codes"):
        matching_codes = fetch_dissertation_codes_by_year(year)
    with perf_timer("school_search.members_in_year.rank_by_matching_codes"):
        return _rank_by_matching_codes(df, index, matching_codes, scope, top_n, f"Защит в {year} г.")


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

    with perf_timer("school_search.depth.all_roots"):
        roots = get_all_roots(df)
    rows: List[SearchRow] = []

    with perf_timer("school_search.depth.lineage_loop"):
        for root in roots:
            graph, subset = get_school_lineage(df, index, root, None, get_db_signature())
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

    with perf_timer("school_search.depth.rank"):
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
    _ = lineage_func, rows_for_func, scope
    sig = get_db_signature()
    with perf_timer("school_search.supervisor_rate.get_supervisor_rate_stats"):
        rate_stats = get_supervisor_rate_stats(df, index, sig)
    with perf_timer("school_search.supervisor_rate.get_school_basic_stats"):
        school_stats = get_school_basic_stats(df, index, "all", sig)
    rows: List[SearchRow] = []
    for root, stat in rate_stats.items():
        direct_count = stat["direct_count"]
        if direct_count == 0:
            continue
        row = _result_row_from_stats(
            0,
            root,
            f"{stat['rate']}%",
            "Доля учеников-руководителей, %",
            school_stats.get(root, {"n_members": direct_count, "year_range": "—", "n_cities": 0}),
        )
        supervisor_count = stat["supervisor_count"]
        row["Таких учеников"] = supervisor_count
        row["Прямых учеников"] = direct_count
        rows.append(row)

    with perf_timer("school_search.supervisor_rate.rank"):
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
    use_fuzzy: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """
    Топ-N школ по числу защит в указанном городе (нечёткий поиск).

    Возвращает:
        result_df   — DataFrame с колонками:
                      # | Руководитель | Защит в городе | Найденные варианты |
                        Всего членов | Годы активности | Уникальных городов
        matched_map — словарь {root: [список найденных вариантов написания]}
    """
    with perf_timer("school_search.city.fetch_candidates"):
        candidates = fetch_dissertation_text_candidates([CITY_COLUMN], city_query, use_like_prefilter=not use_fuzzy)
    if candidates.empty:
        return pd.DataFrame(), {}
    with perf_timer("school_search.city.match_candidates"):
        matched = candidates[_fuzzy_match(candidates["value"], city_query)] if use_fuzzy else candidates
    if matched.empty:
        return pd.DataFrame(), {}
    matching_codes = set(matched["Code"].astype(str).str.strip())
    with perf_timer("school_search.city.get_all_school_member_codes"):
        codes_by_root = get_all_school_member_codes(df, index, scope, get_db_signature())
    with perf_timer("school_search.city.get_school_basic_stats"):
        stats = get_school_basic_stats(df, index, scope, get_db_signature())
    matched_by_code = matched.groupby("Code")["value"].apply(lambda s: sorted(set(s.astype(str)))).to_dict()
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}
    with perf_timer("school_search.city.rank"):
        for root, codes in codes_by_root.items():
            root_codes = codes & matching_codes
            if not root_codes:
                continue
            vals = sorted({v for c in root_codes for v in matched_by_code.get(c, [])})
            matched_map[root] = vals
            row = _result_row_from_stats(0, root, len(root_codes), "Защит в городе", stats[root])
            row["Найденные варианты"] = "; ".join(vals)
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
    stats = get_school_basic_stats(df, index, scope, get_db_signature())
    rows: List[SearchRow] = []
    for root, stat in stats.items():
        n_cities = stat["n_cities"]
        if n_cities == 0:
            continue
        rows.append(_result_row_from_stats(0, root, n_cities, "Уникальных городов", stat))

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
    use_fuzzy: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """
    Внутренняя функция: топ-N школ по числу диссертаций,
    в которых в указанном org_column найдена строка org_query (нечёткий поиск).

    Возвращает:
        result_df   — DataFrame результатов
        matched_map — словарь {root: [список найденных вариантов написания]}
    """
    with perf_timer("school_search.org.fetch_candidates"):
        candidates = fetch_dissertation_text_candidates([org_column], org_query, use_like_prefilter=not use_fuzzy)
    if candidates.empty:
        return pd.DataFrame(), {}
    with perf_timer("school_search.org.match_candidates"):
        matched = candidates[_fuzzy_match(candidates["value"], org_query)] if use_fuzzy else candidates
    if matched.empty:
        return pd.DataFrame(), {}
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}
    matching_codes = set(matched["Code"].astype(str).str.strip())
    with perf_timer("school_search.org.get_all_school_member_codes"):
        codes_by_root = get_all_school_member_codes(df, index, scope, get_db_signature())
    with perf_timer("school_search.org.get_school_basic_stats"):
        stats = get_school_basic_stats(df, index, scope, get_db_signature())
    matched_by_code = matched.groupby("Code")["value"].apply(lambda s: sorted(set(s.astype(str)))).to_dict()
    with perf_timer("school_search.org.rank"):
        for root, codes in codes_by_root.items():
            root_codes = codes & matching_codes
            if not root_codes:
                continue
            vals = sorted({v for c in root_codes for v in matched_by_code.get(c, [])})
            matched_map[root] = vals
            row = _result_row_from_stats(0, root, len(root_codes), metric_label, stats[root])
            row["Найденные варианты"] = "; ".join(vals)
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

    use_fuzzy: bool = False,) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
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
        use_fuzzy=use_fuzzy,
    )


def search_by_defense_location(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    org_query: str,
    scope: str = "all",
    top_n: int = 10,

    use_fuzzy: bool = False,) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
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
        use_fuzzy=use_fuzzy,
    )


def search_by_leading_organization(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    org_query: str,
    scope: str = "all",
    top_n: int = 10,

    use_fuzzy: bool = False,) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
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
        use_fuzzy=use_fuzzy,
    )


# ---------------------------------------------------------------------------
# ГРУППА 4: По тематике
# ---------------------------------------------------------------------------


def search_by_classifier_score(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    classifier_node: str,
    scope: str = "all",
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Топ-N школ по среднему баллу по узлу классификатора.
    """
    sig = get_db_signature()
    with perf_timer("school_search.classifier.get_all_school_member_codes"):
        school_codes = get_all_school_member_codes(df, index, scope, sig)
    with perf_timer("school_search.classifier.get_school_basic_stats"):
        stats = get_school_basic_stats(df, index, scope, sig)
    all_codes = {code for codes in school_codes.values() for code in codes if str(code).strip()}
    if not all_codes:
        return pd.DataFrame()
    with perf_timer("school_search.classifier.fetch_node_scores"):
        node_scores = fetch_dissertation_node_score_by_codes(all_codes, classifier_node)
    if node_scores.empty:
        return pd.DataFrame()
    score_by_code = (
        node_scores.dropna(subset=["Code"])
        .assign(Code=lambda x: x["Code"].astype(str).str.strip())
        .set_index("Code")["node_score"]
    )
    metric_label = f"Средний балл ({classifier_node})"
    rows: List[SearchRow] = []
    with perf_timer("school_search.classifier.rank"):
        for root, codes in school_codes.items():
            root_codes = [code for code in codes if code in score_by_code.index]
            if not root_codes:
                continue
            avg_score = score_by_code.loc[root_codes].mean()
            if pd.isna(avg_score):
                continue
            rows.append(_result_row_from_stats(0, root, round(float(avg_score), 3), metric_label, stats[root]))
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

    use_fuzzy: bool = False,) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
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
    with perf_timer("school_search.opponent.fetch_candidates"):
        candidates = fetch_dissertation_text_candidates(OPPONENT_COLUMNS, person_query, use_like_prefilter=not use_fuzzy)
    if candidates.empty:
        return pd.DataFrame(), {}
    with perf_timer("school_search.opponent.match_candidates"):
        matched = candidates[_fuzzy_match(candidates["value"], person_query)] if use_fuzzy else candidates
    if matched.empty:
        return pd.DataFrame(), {}
    rows: List[SearchRow] = []
    matched_map: Dict[str, List[str]] = {}
    matching_codes = set(matched["Code"].astype(str).str.strip())
    with perf_timer("school_search.opponent.get_all_school_member_codes"):
        codes_by_root = get_all_school_member_codes(df, index, scope, get_db_signature())
    with perf_timer("school_search.opponent.get_school_basic_stats"):
        stats = get_school_basic_stats(df, index, scope, get_db_signature())
    matched_by_code = matched.groupby("Code")["value"].apply(lambda s: sorted(set(s.astype(str)))).to_dict()
    with perf_timer("school_search.opponent.rank"):
        for root, codes in codes_by_root.items():
            root_codes = codes & matching_codes
            if not root_codes:
                continue
            vals = sorted({v for c in root_codes for v in matched_by_code.get(c, [])})
            matched_map[root] = vals
            row = _result_row_from_stats(0, root, len(root_codes), "Диссертаций с оппонентом", stats[root])
            row["Найденные варианты"] = "; ".join(vals)
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
