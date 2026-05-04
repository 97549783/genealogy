"""
Модуль вычислительной логики для вкладки «Анализ научной школы».

Содержит функции для:
- сбора подмножества диссертаций школы
- вычисления метрик (размер, плодовитость, фертильность, топологические)
- временно́й и географической статистики
- институциональных распределений
- топ оппонентов
- тематического профиля по таблице diss_scores_5_8
- преемственности (ученики, ставшие руководителями)

Экспорт/сборка отчетов вынесены в `tabs.school_analysis.exports`.
Модуль не импортирует streamlit и не содержит UI-кода.
"""

from __future__ import annotations

import io
import re
from collections import Counter, deque
from typing import Callable, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from core.db import get_all_feature_columns, load_dissertation_scores

# ---------------------------------------------------------------------------
# Константы основных колонок данных диссертаций
# ---------------------------------------------------------------------------

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS = ["supervisors_1.name", "supervisors_2.name"]
OPPONENT_COLUMNS = ["opponents_1.name", "opponents_2.name", "opponents_3.name"]

DEGREE_LEVEL_COLUMN = "degree.degree_level"
YEAR_COLUMN = "year"
CITY_COLUMN = "city"
INSTITUTION_PREPARED_COLUMN = "institution_prepared"
DEFENSE_LOCATION_COLUMN = "defense_location"
LEADING_ORG_COLUMN = "leading_organization"
SPECIALTY_COLUMNS = ["specialties_1.name", "specialties_2.name"]

DEGREE_CANDIDATE = "кандидат"
DEGREE_DOCTOR = "доктор"

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _degree_level(row: pd.Series) -> str:
    """Нормализует значение степени к 'кандидат' / 'доктор' / ''."""
    raw = str(row.get(DEGREE_LEVEL_COLUMN, "")).strip().lower()
    if raw.startswith("кан"):
        return DEGREE_CANDIDATE
    if raw.startswith("док"):
        return DEGREE_DOCTOR
    return ""


def _safe_year(val) -> Optional[int]:
    """Конвертирует значение в целый год или None."""
    try:
        y = int(float(str(val).strip()))
        if 1900 < y < 2100:
            return y
    except (ValueError, TypeError):
        pass
    return None


def _norm_name(s: str) -> str:
    """
    Нормализует ФИО для сравнения:
    - приводит к нижнему регистру
    - заменяет «ё» → «е»
    - заменяет точки пробелами (для инициалов вида «И.И.»)
    - сжимает множественные пробелы
    """
    s = s.lower().replace("ё", "е").replace(".", " ")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Сбор подмножества диссертаций
# ---------------------------------------------------------------------------


def collect_school_subset(
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
# Обзорная карточка (плитки)
# ---------------------------------------------------------------------------


def compute_overview(
    subset: pd.DataFrame,
    root: str,
    index: Dict[str, Set[int]],
    lineage_func: Callable,
    df_full: pd.DataFrame,
    scope: str,
) -> Dict:
    """
    Возвращает словарь с базовыми показателями для плиток st.metric.

    Ключи:
        total, candidates, doctors, cities, year_min, year_max, generations
    """
    total = len(subset)

    candidates = 0
    doctors = 0
    if not subset.empty and DEGREE_LEVEL_COLUMN in subset.columns:
        for _, row in subset.iterrows():
            d = _degree_level(row)
            if d == DEGREE_CANDIDATE:
                candidates += 1
            elif d == DEGREE_DOCTOR:
                doctors += 1

    # FIX #1: явное приведение к int, чтобы избежать случайной подмены типа
    cities: int = 0
    if not subset.empty and CITY_COLUMN in subset.columns:
        cities = int(
            subset[CITY_COLUMN]
            .dropna()
            .astype(str)
            .str.strip()
            .pipe(lambda s: s[s != ""])
            .nunique()
        )

    year_min: Optional[int] = None
    year_max: Optional[int] = None
    if not subset.empty and YEAR_COLUMN in subset.columns:
        years = subset[YEAR_COLUMN].dropna().map(_safe_year).dropna()
        if not years.empty:
            year_min = int(years.min())
            year_max = int(years.max())

    # Глубина дерева (число поколений) — только для scope='all'
    generations: Optional[int] = None
    if scope == "all":
        graph, _ = lineage_func(df_full, index, root)
        if graph.number_of_nodes() > 0:
            try:
                import networkx as nx
                if nx.is_directed_acyclic_graph(graph):
                    lengths = nx.single_source_shortest_path_length(graph, root)
                    generations = max(lengths.values()) if lengths else 0
            except Exception:
                generations = None

    return {
        "total": total,
        "candidates": candidates,
        "doctors": doctors,
        "cities": cities,
        "year_min": year_min,
        "year_max": year_max,
        "generations": generations,
    }


# ---------------------------------------------------------------------------
# Метрики научной школы
# ---------------------------------------------------------------------------


def compute_metrics(
    df_full: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    lineage_func: Callable,
    rows_for_func: Callable,
    subset_direct: pd.DataFrame,
    subset_all: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Вычисляет все метрики научной школы.

    Возвращает:
        metrics_df  — таблица «Метрика / Значение» для отображения
        generations_df — распределение по поколениям (поколение → число учеников)
    """
    # ── Размер школы ───────────────────────────────────────────────────────
    direct_count = len(subset_direct)
    all_count = len(subset_all)

    # Фертильность: ученики, которые сами имеют учеников в базе
    fertile: List[str] = []
    if not subset_direct.empty and AUTHOR_COLUMN in subset_direct.columns:
        for name in subset_direct[AUTHOR_COLUMN].dropna().astype(str).unique():
            name = name.strip()
            if not name:
                continue
            pupils = rows_for_func(df_full, index, name)
            if not pupils.empty:
                fertile.append(name)

    fertility_count = len(fertile)
    fertility_pct = (
        round(100 * fertility_count / direct_count, 1) if direct_count > 0 else 0.0
    )

    # ── Топологические метрики ─────────────────────────────────────────────
    graph, _ = lineage_func(df_full, index, root)

    max_depth = 0
    max_width = 0
    num_levels = 0
    generations_rows: List[Dict] = []

    if graph.number_of_nodes() > 1:
        try:
            import networkx as nx

            if nx.is_directed_acyclic_graph(graph):
                # BFS — считаем уровни
                level_map: Dict[str, int] = {root: 0}
                q = deque([root])
                while q:
                    node = q.popleft()
                    for child in graph.successors(node):
                        if child not in level_map:
                            level_map[child] = level_map[node] + 1
                            q.append(child)

                # Убираем корень из подсчёта учеников
                student_levels = {
                    n: d for n, d in level_map.items() if n != root
                }

                if student_levels:
                    counter: Counter = Counter(student_levels.values())
                    max_depth = max(student_levels.values())
                    max_width = max(counter.values())
                    num_levels = len(counter)

                    for gen in sorted(counter.keys()):
                        generations_rows.append(
                            {"Поколение": gen, "Число учеников": counter[gen]}
                        )
        except Exception:
            pass

    # ── Динамика роста ─────────────────────────────────────────────────────
    year_first: Optional[int] = None
    year_last: Optional[int] = None
    avg_per_year: Optional[float] = None
    peak_year: Optional[int] = None

    if not subset_all.empty and YEAR_COLUMN in subset_all.columns:
        years_series = subset_all[YEAR_COLUMN].dropna().map(_safe_year).dropna()
        if not years_series.empty:
            year_first = int(years_series.min())
            year_last = int(years_series.max())
            span = year_last - year_first + 1
            avg_per_year = round(len(years_series) / span, 2) if span > 0 else float(len(years_series))
            peak_year = int(years_series.value_counts().idxmax())

    # ── Сборка таблицы метрик ──────────────────────────────────────────────
    rows = [
        # Размер
        ("Число прямых учеников", direct_count),
        ("Число всех потомков (все поколения)", all_count),
        ("Ученики, ставшие научными руководителями", fertility_count),
        (
            "Доля учеников, ставших научными руководителями, %",
            f"{fertility_pct}%",
        ),
        # Структура
        ("Число поколений (макс. глубина)", max_depth if max_depth else "—"),
        ("Ширина дерева (макс. учеников на одном уровне)", max_width if max_width else "—"),
        ("Число уровней в дереве", num_levels if num_levels else "—"),
        # Динамика
        ("Год первой защиты", year_first if year_first else "—"),
        ("Год последней защиты", year_last if year_last else "—"),
        (
            "Среднее число защит в год",
            avg_per_year if avg_per_year is not None else "—",
        ),
        ("Пиковый год (наибольшее число защит)", peak_year if peak_year else "—"),
    ]

    metrics_df = pd.DataFrame(rows, columns=["Метрика", "Значение"])
    generations_df = pd.DataFrame(generations_rows) if generations_rows else pd.DataFrame(
        columns=["Поколение", "Число учеников"]
    )

    return metrics_df, generations_df


# ---------------------------------------------------------------------------
# Временно́е распределение (по годам)
# ---------------------------------------------------------------------------


def compute_yearly_stats(subset: pd.DataFrame) -> pd.DataFrame:
    """
    Возвращает таблицу: Год | Всего | Кандидатских | Докторских
    Отсортировано по году.
    """
    if subset.empty or YEAR_COLUMN not in subset.columns:
        return pd.DataFrame(columns=["Год", "Всего", "Кандидатских", "Докторских"])

    rows: List[Dict] = []
    for _, row in subset.iterrows():
        y = _safe_year(row.get(YEAR_COLUMN))
        if y is None:
            continue
        d = _degree_level(row)
        rows.append({"year": y, "degree": d})

    if not rows:
        return pd.DataFrame(columns=["Год", "Всего", "Кандидатских", "Докторских"])

    tmp = pd.DataFrame(rows)

    # FIX #2: include_groups=False предотвращает DeprecationWarning в pandas >= 2.2
    grouped = (
        tmp.groupby("year")
        .apply(
            lambda g: pd.Series(
                {
                    "Всего": len(g),
                    "Кандидатских": (g["degree"] == DEGREE_CANDIDATE).sum(),
                    "Докторских": (g["degree"] == DEGREE_DOCTOR).sum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
        .rename(columns={"year": "Год"})
        .sort_values("Год")
    )
    grouped["Год"] = grouped["Год"].astype(int)
    return grouped.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Географическое распределение
# ---------------------------------------------------------------------------


def compute_city_stats(subset: pd.DataFrame) -> pd.DataFrame:
    """Возвращает таблицу: Город | Число защит, отсортированную по убыванию."""
    if subset.empty or CITY_COLUMN not in subset.columns:
        return pd.DataFrame(columns=["Город", "Число защит"])

    counts = (
        subset[CITY_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
        .pipe(lambda s: s[s != ""])
        .value_counts()
        .reset_index()
    )
    counts.columns = ["Город", "Число защит"]
    return counts.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Институциональные распределения
# ---------------------------------------------------------------------------


def compute_institutional_stats(subset: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Возвращает словарь из четырёх таблиц (название → число).

    Ключи:
        'institution_prepared', 'defense_location',
        'leading_organization', 'specialties'
    """

    def _count_column(col: str, label: str) -> pd.DataFrame:
        if col not in subset.columns:
            return pd.DataFrame(columns=[label, "Число"])
        counts = (
            subset[col]
            .dropna()
            .astype(str)
            .str.strip()
            .pipe(lambda s: s[s != ""])
            .value_counts()
            .reset_index()
        )
        counts.columns = [label, "Число"]
        return counts.reset_index(drop=True)

    # Специальности — объединяем два столбца
    specialties_series: List[pd.Series] = []
    for col in SPECIALTY_COLUMNS:
        if col in subset.columns:
            specialties_series.append(
                subset[col].dropna().astype(str).str.strip().pipe(lambda s: s[s != ""])
            )

    if specialties_series:
        combined = pd.concat(specialties_series, ignore_index=True)
        spec_counts = combined.value_counts().reset_index()
        spec_counts.columns = ["Специальность", "Число"]
    else:
        spec_counts = pd.DataFrame(columns=["Специальность", "Число"])

    return {
        "institution_prepared": _count_column(
            INSTITUTION_PREPARED_COLUMN, "Организация выполнения"
        ),
        "defense_location": _count_column(
            DEFENSE_LOCATION_COLUMN, "Место защиты"
        ),
        "leading_organization": _count_column(
            LEADING_ORG_COLUMN, "Ведущая организация"
        ),
        "specialties": spec_counts,
    }


# ---------------------------------------------------------------------------
# Топ оппонентов
# ---------------------------------------------------------------------------


def compute_top_opponents(subset: pd.DataFrame, top_n: Optional[int] = 5) -> pd.DataFrame:
    """
    Возвращает таблицу топ-N оппонентов: Оппонент | Число появлений.

    Имена нормализуются через _norm_name() перед подсчётом, чтобы
    «Иванов И.И.» и «Иванов Иван Иванович» не считались разными людьми
    при незначительных вариациях написания.
    Для отображения используется наиболее часто встречающаяся форма имени.
    """
    # norm_key → список оригинальных написаний
    norm_to_originals: Dict[str, List[str]] = {}
    for col in OPPONENT_COLUMNS:
        if col not in subset.columns:
            continue
        for val in subset[col].dropna().astype(str):
            raw = val.strip()
            if not raw:
                continue
            key = _norm_name(raw)
            norm_to_originals.setdefault(key, []).append(raw)

    if not norm_to_originals:
        return pd.DataFrame(columns=["Оппонент", "Число появлений"])

    # Подсчёт по нормализованному ключу
    counter: Counter = Counter({k: len(v) for k, v in norm_to_originals.items()})

    # Для отображения берём самую частую оригинальную форму
    rows = []
    most_common = counter.most_common(top_n) if top_n is not None else counter.most_common()
    for key, count in most_common:
        originals = norm_to_originals[key]
        display_name = Counter(originals).most_common(1)[0][0]
        rows.append({"Оппонент": display_name, "Число появлений": count})

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Тематический профиль школы
# ---------------------------------------------------------------------------


def _is_child_of(code: str, parent: str) -> bool:
    """Проверяет, является ли code прямым или косвенным потомком parent."""
    return code == parent or code.startswith(parent + ".")


def compute_thematic_profile(
    subset: pd.DataFrame,
    classifier: List[Tuple[str, str, bool]],
    group_prefix_level: str = "",
    group_prefix_education: str = "1.1.1",
    group_prefix_knowledge: str = "1.1.2",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Вычисляет средние баллы по тематическим группам для всей школы.

    Параметры:
        subset                  — диссертации школы
        classifier              — THEMATIC_CLASSIFIER из streamlit_app.py
        group_prefix_level      — не используется (оставлен для совместимости)
        group_prefix_education  — префикс группы «Уровень образования» (1.1.1)
        group_prefix_knowledge  — префикс группы «Область знания» (1.1.2)

    Возвращает:
        education_df  — таблица: Название | Средний балл  (группа 1.1.1)
        knowledge_df  — таблица: Название | Средний балл  (группа 1.1.2)
    """
    if subset.empty or "Code" not in subset.columns:
        empty = pd.DataFrame(columns=["Название", "Средний балл"])
        return empty, empty

    # Загружаем оценки из SQLite
    scores = load_dissertation_scores()
    scores = scores.dropna(subset=["Code"])
    scores["Code"] = scores["Code"].astype(str).str.strip()
    scores = scores[scores["Code"].str.len() > 0]
    scores = scores.drop_duplicates(subset=["Code"], keep="first")

    feature_cols = get_all_feature_columns(scores, key_column="Code")
    scores[feature_cols] = scores[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    # Оставляем только коды, присутствующие в выборке школы
    school_codes = (
        subset["Code"].dropna().astype(str).str.strip().pipe(lambda s: s[s != ""]).unique()
    )
    school_scores = scores[scores["Code"].isin(school_codes)]

    if school_scores.empty:
        empty = pd.DataFrame(columns=["Название", "Средний балл"])
        return empty, empty

    # Среднее по всем диссертациям школы для каждого признака
    means: Dict[str, float] = {col: float(school_scores[col].mean()) for col in feature_cols}

    # Словарь: код → название
    code_to_name = {code: title for code, title, _ in classifier}

    def _build_group_df(prefix: str) -> pd.DataFrame:
        rows: List[Dict] = []
        for col, avg in means.items():
            if _is_child_of(col, prefix) and col != prefix:
                name = code_to_name.get(col, col)
                if avg >= 2:
                    rows.append({"Название": name, "Средний балл": round(avg, 2)})
        if not rows:
            return pd.DataFrame(columns=["Название", "Средний балл"])
        result = pd.DataFrame(rows).sort_values("Средний балл", ascending=False)
        return result.reset_index(drop=True)

    education_df = _build_group_df(group_prefix_education)
    knowledge_df = _build_group_df(group_prefix_knowledge)

    return education_df, knowledge_df


# ---------------------------------------------------------------------------
# Преемственность
# ---------------------------------------------------------------------------


def compute_continuity(
    df_full: pd.DataFrame,
    index: Dict[str, Set[int]],
    subset_direct: pd.DataFrame,
    rows_for_func: Callable,
) -> pd.DataFrame:
    """
    Возвращает таблицу: Ученик | Число его учеников в базе.
    Только строки с числом учеников > 0, отсортированные по убыванию.

    Считает уникальных учеников (по AUTHOR_COLUMN), а не число диссертаций,
    чтобы не завышать результат для лиц с несколькими защитами.
    """
    if subset_direct.empty or AUTHOR_COLUMN not in subset_direct.columns:
        return pd.DataFrame(columns=["Ученик", "Число учеников в базе"])

    rows: List[Dict] = []
    for name in subset_direct[AUTHOR_COLUMN].dropna().astype(str).unique():
        name = name.strip()
        if not name:
            continue
        pupils = rows_for_func(df_full, index, name)
        # FIX #3: считаем уникальных учеников, а не строки (диссертации)
        if not pupils.empty and AUTHOR_COLUMN in pupils.columns:
            count = int(
                pupils[AUTHOR_COLUMN].dropna().astype(str).str.strip()
                .pipe(lambda s: s[s != ""]).nunique()
            )
        else:
            count = 0
        if count > 0:
            rows.append({"Ученик": name, "Число учеников в базе": count})

    if not rows:
        return pd.DataFrame(columns=["Ученик", "Число учеников в базе"])

    return (
        pd.DataFrame(rows)
        .sort_values("Число учеников в базе", ascending=False)
        .reset_index(drop=True)
    )
