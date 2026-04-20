"""
Модуль Streamlit-вкладки «Поиск научных школ».
Импортируйте и вызывайте render_school_search_tab() в основном приложении.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import streamlit as st

from utils.graph import lineage, rows_for, slug
from school_search import (
    AUTHOR_COLUMN,
    FUZZY_THRESHOLD,
    SUPERVISOR_COLUMNS,
    build_excel_search_results,
    collect_subset,
    get_all_roots,
    search_by_city,
    search_by_classifier_score,
    search_by_defense_location,
    search_by_depth,
    search_by_geo_diversity,
    search_by_institution_prepared,
    search_by_leading_organization,
    search_member_lineage_chains,
    search_by_members_in_period,
    search_by_members_in_year,
    search_by_opponent,
    search_by_supervisor_rate,
    search_by_total_members,
)
from utils.table_display import render_dissertations_widget
from utils.tree_renderers import build_markmap_html
from utils.urls import share_params_button


# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================

SCOPE_LABELS: Dict[str, str] = {
    "all": "Все поколения (полное дерево)",
    "direct": "Только первое поколение (прямые ученики)",
}

TOP_N_OPTIONS: List[int] = [5, 10, 20, 50]

# Группы режимов поиска
SEARCH_MODES: Dict[str, str] = {
    # Группа 1 — по персонам
    "member":             "👤 1.1 Школы, к которой искомое лицо принадлежит",
    "opponent":           "👤 1.2 Школы, где лицо выступает оппонентом",
    # Группа 2 — по размеру школы
    "total_members":      "📊 2.1 Общее число членов школы",
    "members_in_period":  "📊 2.2 Число защит за период (год от / год до)",
    "members_in_year":    "📊 2.3 Число защит за конкретный год",
    "depth":              "🌳 2.4 Глубина дерева (число поколений)",
    "supervisor_rate":    "🎓 2.5 Доля учеников, ставших научными руководителями",
    # Группа 3 — география
    "city":               "🏙️ 3.1 Число защит в указанном городе",
    "geo_diversity":      "🗺️ 3.2 Географическое разнообразие (число уникальных городов)",
    # Группа 4 — организации
    "org_prepared":       "🏢 4.1 По организации выполнения",
    "org_defense":        "🏩 4.2 По месту (организации) защиты",
    "org_leading":        "🏦 4.3 По ведущей организации",
    # Группа 5 — тематика
    "classifier_score":   "🔬 5.1 Средний балл по узлу классификатора",
}

# Режимы, для которых параметр scope не применяется
_SCOPE_INDEPENDENT_MODES = {"depth", "supervisor_rate"}


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================


def _bar_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    color: str = "#4C9BE8",
) -> plt.Figure:
    """Горизонтальная бар-чарт — наглядная диаграмма результатов."""
    fig, ax = plt.subplots(figsize=(8, max(3, len(df) * 0.45)))
    xs = df[x_col].astype(str)
    ax.barh(xs[::-1], df[y_col][::-1], color=color)
    ax.set_xlabel(y_col, fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig


def _show_matched_variants(
    matched_map: Dict[str, List[str]],
    result_df: pd.DataFrame,
    key_prefix: str,
) -> None:
    """
    Отображает expander со списком найденных вариантов написания
    организаций/городов/персон для каждой школы в результате.
    """
    if not matched_map:
        return
    with st.expander("🔍 Найденные варианты написания", expanded=False):
        st.caption(
            "Слова и фразы, защитанные в колонке данных и совпавшие с вашим запросом через прямое "
            f"совпадение или нечёткий поиск (порог схожести: {FUZZY_THRESHOLD}%)."
        )
        rows_for_expander = []
        for root, variants in matched_map.items():
            if root in result_df["Руководитель"].values:
                rows_for_expander.append({
                    "Руководитель": root,
                    "Найденные варианты": "; ".join(variants),
                })
        if rows_for_expander:
            st.dataframe(
                pd.DataFrame(rows_for_expander),
                use_container_width=True,
                hide_index=True,
            )


def _normalize_name(name: str) -> str:
    return " ".join(str(name).strip().lower().replace("ё", "е").split())


def _build_reverse_lineage_rows(subset: pd.DataFrame) -> pd.DataFrame:
    if subset.empty or AUTHOR_COLUMN not in subset.columns:
        return pd.DataFrame(columns=["Диссертант", "Научный руководитель", "Научный руководитель 2"])

    rows: List[Dict[str, str]] = []
    for _, row in subset.iterrows():
        dissertation_name = str(row.get(AUTHOR_COLUMN, "")).strip()
        if not dissertation_name:
            continue
        sup_1 = str(row.get(SUPERVISOR_COLUMNS[0], "")).strip() if SUPERVISOR_COLUMNS[0] in subset.columns else ""
        sup_2 = str(row.get(SUPERVISOR_COLUMNS[1], "")).strip() if SUPERVISOR_COLUMNS[1] in subset.columns else ""
        if not sup_1 and not sup_2:
            continue
        rows.append(
            {
                "Диссертант": dissertation_name,
                "Научный руководитель": sup_1 or "—",
                "Научный руководитель 2": sup_2 or "—",
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Диссертант", "Научный руководитель", "Научный руководитель 2"])

    return pd.DataFrame(rows).drop_duplicates(ignore_index=True)


def _build_reverse_lineage_graph(subset: pd.DataFrame, root_name: str) -> nx.DiGraph:
    graph = nx.DiGraph()
    root_name = str(root_name).strip()
    if not root_name:
        return graph

    graph.add_node(root_name)
    if subset.empty or AUTHOR_COLUMN not in subset.columns:
        return graph

    by_author_rows: Dict[str, List[pd.Series]] = {}
    for _, row in subset.iterrows():
        author = str(row.get(AUTHOR_COLUMN, "")).strip()
        if not author:
            continue
        by_author_rows.setdefault(_normalize_name(author), []).append(row)

    queue: List[str] = [root_name]
    visited: Set[str] = set()
    max_depth = 25
    depth = 0

    while queue and depth <= max_depth:
        next_queue: List[str] = []
        for current_name in queue:
            cur_norm = _normalize_name(current_name)
            if not cur_norm or cur_norm in visited:
                continue
            visited.add(cur_norm)
            for row in by_author_rows.get(cur_norm, []):
                for sup_col in SUPERVISOR_COLUMNS:
                    supervisor = str(row.get(sup_col, "")).strip()
                    if not supervisor:
                        continue
                    graph.add_edge(current_name, supervisor)
                    if _normalize_name(supervisor) not in visited:
                        next_queue.append(supervisor)
        queue = next_queue
        depth += 1

    return graph


def _render_results(
    result_df: pd.DataFrame,
    metric_col: str,
    chart_title: str,
    matched_map: Optional[Dict[str, List[str]]],
    key_prefix: str,
    search_mode: str,
    search_params: Dict,
) -> None:
    """
    Унифицированный рендеринг результатов:
      - bar chart
      - таблица с результатами
      - expander с вариантами написания
      - кнопка скачивания Excel
    """
    if result_df.empty:
        st.warning("По заданным параметрам ничего не найдено.")
        return

    st.success(f"Найдено школ: {len(result_df)}")

    # Диаграмма
    try:
        y_vals = pd.to_numeric(result_df[metric_col].astype(str).str.replace("%", ""), errors="coerce")
        if y_vals.notna().any():
            plot_df = result_df.copy()
            plot_df["_y"] = y_vals
            fig = _bar_chart(plot_df, x_col="Руководитель", y_col="_y", title=chart_title)
            st.pyplot(fig)
            plt.close(fig)
    except Exception:
        pass

    # Таблица
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    # Варианты написания
    if matched_map:
        _show_matched_variants(matched_map, result_df, key_prefix)

    # Скачивание Excel
    try:
        excel_bytes = build_excel_search_results(
            result_df=result_df,
            search_mode=search_mode,
            search_params=search_params,
        )
        st.download_button(
            label="📥 Скачать результаты (Excel)",
            data=excel_bytes,
            file_name="поиск_научных_школ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_dl_excel",
        )
    except Exception:
        pass


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ==============================================================================


def render_school_search_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    classifier: Optional[List[Tuple[str, str, bool]]] = None,
    scores_folder: str = "basic_scores",
) -> None:
    """
    Отрисовывает вкладку «Поиск научных школ».

    Аргументы:
        df            — основной DataFrame с диссертациями
        idx           — индекс имён
        classifier    — THEMATIC_CLASSIFIER из streamlit_app.py
        scores_folder — путь к basic_scores
    """
    st.subheader("Поиск научных школ")

    # ==========================================================================
    # 0. Общие параметры поиска
    # ==========================================================================
    st.markdown("### ⚙️ Параметры поиска")

    col_topn, col_scope, col_mode = st.columns([1, 2, 3])

    with col_topn:
        top_n = st.selectbox(
            "Кол-во школ в результате",
            options=TOP_N_OPTIONS,
            index=1,
            key="school_search_top_n",
        )

    with col_scope:
        scope_keys = list(SCOPE_LABELS.keys())
        scope_idx = st.radio(
            "Поколения",
            options=range(len(scope_keys)),
            format_func=lambda i: SCOPE_LABELS[scope_keys[i]],
            key="school_search_scope",
        )
        scope: str = scope_keys[scope_idx]

    with col_mode:
        mode_keys = list(SEARCH_MODES.keys())
        search_mode = st.selectbox(
            "Режим поиска",
            options=mode_keys,
            format_func=lambda k: SEARCH_MODES[k],
            key="school_search_mode",
        )

    if search_mode in _SCOPE_INDEPENDENT_MODES:
        st.caption(
            "ℹ️ Для этого режима параметр «Поколения» не имеет значения: всегда используется полное дерево."
        )

    st.markdown("---")

    # ==========================================================================
    # 1. Дополнительные параметры (появляются динамически)
    # ==========================================================================
    extra_params: Dict = {}

    if search_mode == "members_in_period":
        st.markdown("### 📅 Диапазон лет")
        col_y1, col_y2 = st.columns(2)
        with col_y1:
            year_from = st.number_input(
                "Год от",
                min_value=1900, max_value=2100, value=2000,
                step=1, key="school_search_year_from",
            )
        with col_y2:
            year_to = st.number_input(
                "Год до",
                min_value=1900, max_value=2100, value=2024,
                step=1, key="school_search_year_to",
            )
        extra_params = {"year_from": year_from, "year_to": year_to}

    elif search_mode == "members_in_year":
        st.markdown("### 📅 Год")
        year = st.number_input(
            "Год защиты",
            min_value=1900, max_value=2100, value=2010,
            step=1, key="school_search_year",
        )
        extra_params = {"year": year}

    elif search_mode == "city":
        st.markdown("### 🏙️ Город")
        city_query = st.text_input(
            "Введите название города (полностью или частично)",
            placeholder="например, Москва",
            key="school_search_city",
        )
        extra_params = {"city_query": city_query}

    elif search_mode in ("org_prepared", "org_defense", "org_leading"):
        labels = {
            "org_prepared": "Название организации выполнения",
            "org_defense":  "Название организации (места) защиты",
            "org_leading":  "Название ведущей организации",
        }
        st.markdown("### 🏢 Организация")
        st.caption(
            "Поиск нечёткий: сначала проверяется вхождение строки (без учёта регистра), затем нечёткое "
            f"совпадение через rapidfuzz (порог: {FUZZY_THRESHOLD}%). Помогает найти разные варианты "
            "написания (например, «МГУ» и «Московский государственный университет»)."
        )
        org_query = st.text_input(
            labels[search_mode],
            placeholder="например, МГУ или Педагогический университет",
            key=f"school_search_org_{search_mode}",
        )
        extra_params = {"org_query": org_query}

    elif search_mode == "classifier_score":
        st.markdown("### 🔬 Узел классификатора")
        if classifier is None:
            st.warning("Классификатор не передан. Режим недоступен.")
            return

        selectable = [
            (code, title)
            for code, title, disabled in classifier
            if not disabled
        ]
        if not selectable:
            st.warning("Нет доступных для выбора узлов классификатора.")
            return

        node_options = [f"{code} — {title}" for code, title in selectable]
        node_codes = [code for code, _ in selectable]

        chosen_label = st.selectbox(
            "Выберите узел классификатора",
            options=node_options,
            key="school_search_classifier_node",
            help="Выберите узел — школы будут ранжированы по среднему баллу по всем признакам-потомкам этого узла.",
        )
        chosen_idx = node_options.index(chosen_label)
        classifier_node = node_codes[chosen_idx]
        extra_params = {"classifier_node": classifier_node}

    elif search_mode in ("opponent", "member"):
        label_map = {
            "opponent": "ФИО оппонента",
            "member":   "ФИО автора диссертации",
        }
        placeholder_map = {
            "opponent": "например, Иванов Иван Иванович",
            "member":   "например, Петрова Наталья Сергеевна",
        }
        st.markdown("### 👤 Лицо")
        st.caption(
            "Поиск нечёткий: поддерживаются частичные совпадения и инициалы. "
            "Пробел между инициалами не важен: «Е. А.» и «Е.А.» считаются одинаковыми. "
            f"Порог rapidfuzz: {FUZZY_THRESHOLD}%."
        )
        if search_mode == "member" and "candidate_name" in df.columns:
            candidate_options = sorted(
                set(
                    df["candidate_name"]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .loc[lambda s: s != ""]
                    .tolist()
                )
            )
            person_query = st.selectbox(
                label_map[search_mode],
                options=[""] + candidate_options,
                index=0,
                key=f"school_search_person_{search_mode}_select",
                placeholder="Начните вводить ФИО и выберите вариант из списка",
            )
        else:
            person_query = st.text_input(
                label_map[search_mode],
                placeholder=placeholder_map[search_mode],
                key=f"school_search_person_{search_mode}",
            )
        extra_params = {"person_query": person_query}

    # ==========================================================================
    # 2. Кнопка «Найти»
    # ==========================================================================
    st.markdown("---")

    run_btn = st.button("🔍 Найти", key="school_search_run", type="primary")
    if not run_btn:
        return

    _text_modes = {"city", "org_prepared", "org_defense", "org_leading", "opponent", "member"}
    if search_mode in _text_modes:
        query_val = (
            extra_params.get("city_query") or
            extra_params.get("org_query") or
            extra_params.get("person_query") or ""
        ).strip()
        if not query_val:
            st.warning("Пожалуйста, заполните поле поиска.")
            return

    # ==========================================================================
    # 3. Запуск поиска
    # ==========================================================================
    st.markdown("### 🏆 Результаты")

    mode_label = SEARCH_MODES[search_mode]
    scope_label = SCOPE_LABELS[scope]
    params_for_excel = {"Режим": mode_label, "Поколения": scope_label, "Топ-N": top_n}
    params_for_excel.update({str(k): str(v) for k, v in extra_params.items()})

    spinner_msg = f"Поиск по режиму \u00ab{mode_label}\u00bb в базе..."
    share_params = {
        "tab": "school_search",
        "mode": search_mode,
        "scope": scope,
        "top_n": top_n,
        **extra_params,
    }

    # --------------------------------------------------------------------------
    # ГРУППА 1: По размеру школы
    # --------------------------------------------------------------------------
    if search_mode == "total_members":
        with st.spinner(spinner_msg):
            result_df = search_by_total_members(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Число членов",
            chart_title=f"Топ-{top_n} школ по числу членов",
            matched_map=None, key_prefix="ss_total",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_total")

    elif search_mode == "members_in_period":
        with st.spinner(spinner_msg):
            result_df = search_by_members_in_period(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                year_from=extra_params["year_from"],
                year_to=extra_params["year_to"],
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Защит за период",
            chart_title=(
                f"Топ-{top_n}: защит за {extra_params['year_from']}–{extra_params['year_to']}"
            ),
            matched_map=None, key_prefix="ss_period",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_period")

    elif search_mode == "members_in_year":
        year_val = extra_params["year"]
        with st.spinner(spinner_msg):
            result_df = search_by_members_in_year(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                year=year_val, scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col=f"Защит в {year_val} г.",
            chart_title=f"Топ-{top_n}: защит в {year_val} г.",
            matched_map=None, key_prefix="ss_year",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_year")

    elif search_mode == "depth":
        with st.spinner(spinner_msg):
            result_df = search_by_depth(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Поколений",
            chart_title=f"Топ-{top_n} школ по глубине дерева",
            matched_map=None, key_prefix="ss_depth",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_depth")

    elif search_mode == "supervisor_rate":
        with st.spinner(spinner_msg):
            result_df = search_by_supervisor_rate(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Доля учеников-руководителей, %",
            chart_title=f"Топ-{top_n}: доля учеников, ставших научными руководителями",
            matched_map=None, key_prefix="ss_suprate",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_suprate")

    # --------------------------------------------------------------------------
    # ГРУППА 2: По географии
    # --------------------------------------------------------------------------
    elif search_mode == "city":
        with st.spinner(spinner_msg):
            result_df, matched_map = search_by_city(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                city_query=extra_params["city_query"],
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Защит в городе",
            chart_title=f"Топ-{top_n}: защит в «{extra_params['city_query']}»",
            matched_map=matched_map, key_prefix="ss_city",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_city")

    elif search_mode == "geo_diversity":
        with st.spinner(spinner_msg):
            result_df = search_by_geo_diversity(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Уникальных городов",
            chart_title=f"Топ-{top_n}: географическое разнообразие",
            matched_map=None, key_prefix="ss_geo",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_geo")

    # --------------------------------------------------------------------------
    # ГРУППА 3: По организациям
    # --------------------------------------------------------------------------
    elif search_mode == "org_prepared":
        with st.spinner(spinner_msg):
            result_df, matched_map = search_by_institution_prepared(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                org_query=extra_params["org_query"],
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Диссертаций (орг. выполнения)",
            chart_title=f"Топ-{top_n}: орг. выполнения «{extra_params['org_query']}»",
            matched_map=matched_map, key_prefix="ss_org_prep",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_org_prep")

    elif search_mode == "org_defense":
        with st.spinner(spinner_msg):
            result_df, matched_map = search_by_defense_location(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                org_query=extra_params["org_query"],
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Диссертаций (место защиты)",
            chart_title=f"Топ-{top_n}: место защиты «{extra_params['org_query']}»",
            matched_map=matched_map, key_prefix="ss_org_def",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_org_def")

    elif search_mode == "org_leading":
        with st.spinner(spinner_msg):
            result_df, matched_map = search_by_leading_organization(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                org_query=extra_params["org_query"],
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Диссертаций (вед. организация)",
            chart_title=f"Топ-{top_n}: вед. орг. «{extra_params['org_query']}»",
            matched_map=matched_map, key_prefix="ss_org_lead",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_org_lead")

    # --------------------------------------------------------------------------
    # ГРУППА 4: По тематике
    # --------------------------------------------------------------------------
    elif search_mode == "classifier_score":
        classifier_node = extra_params["classifier_node"]
        with st.spinner(spinner_msg):
            result_df = search_by_classifier_score(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                classifier_node=classifier_node,
                scores_folder=scores_folder,
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df,
            metric_col=f"Средний балл ({classifier_node})",
            chart_title=(
                f"Топ-{top_n}: средний балл по «{classifier_node}»"
            ),
            matched_map=None, key_prefix="ss_cls",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_cls")

    # --------------------------------------------------------------------------
    # ГРУППА 5: По персонам
    # --------------------------------------------------------------------------
    elif search_mode == "opponent":
        with st.spinner(spinner_msg):
            result_df, matched_map = search_by_opponent(
                df=df, index=idx,
                lineage_func=lineage, rows_for_func=rows_for,
                person_query=extra_params["person_query"],
                scope=scope, top_n=top_n,
            )
        _render_results(
            result_df, metric_col="Диссертаций с оппонентом",
            chart_title=(
                f"Топ-{top_n}: школы с оппонентом «{extra_params['person_query']}»"
            ),
            matched_map=matched_map, key_prefix="ss_opp",
            search_mode=mode_label, search_params=params_for_excel,
        )
        if not result_df.empty:
            share_params_button(share_params, key="school_search_share_opp")

    elif search_mode == "member":
        with st.spinner(spinner_msg):
            member_results = search_member_lineage_chains(
                df=df,
                person_query=extra_params["person_query"],
            )

        if not member_results:
            st.warning("По заданным параметрам ничего не найдено.")
            return

        st.success(f"Найдено вариантов ФИО авторов: {len(member_results)}")
        st.caption(
            "Для каждого найденного варианта показана цепочка научных руководителей вверх "
            "и список диссертаций автора вместе с диссертациями руководителей из цепочки."
        )

        for i, item in enumerate(member_results, start=1):
            author_name = str(item["author_name"])
            chain_names = item["chain_names"]
            subset = item["subset"]
            reverse_table = _build_reverse_lineage_rows(subset)
            reverse_graph = _build_reverse_lineage_graph(subset, author_name)

            st.markdown(f"#### {i}. {author_name}")
            st.caption(" → ".join(chain_names) if chain_names else "Цепочка не найдена.")

            st.markdown("##### Таблица цепочки научных руководителей")
            if reverse_table.empty:
                st.info("Для этого автора не найдено связей «диссертант → научный руководитель».")
            else:
                st.markdown(
                    """
                    <style>
                    .reverse-lineage-table table {
                        font-size: 1.02rem;
                    }
                    .reverse-lineage-table th {
                        font-size: 1.02rem;
                        font-weight: 700;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown('<div class="reverse-lineage-table">', unsafe_allow_html=True)
                st.table(reverse_table)
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("##### 🌳 Цепь научных руководителей")
            st.caption(
                "Это дерево научных руководителей, а не учеников, т.е. это дерево, "
                "обратное тому, что представлено на вкладке «Построение деревьев»."
            )
            if reverse_graph.number_of_edges() == 0:
                st.info("Для построения обратного дерева недостаточно данных.")
            else:
                html_str, height_px = build_markmap_html(
                    reverse_graph,
                    author_name,
                    branching_mode="unidirectional",
                )
                st.components.v1.html(html_str, height=height_px + 20, scrolling=False)
                st.caption(
                    "💡 Показан только режим «Одностороннее ветвление» для цепочки научных руководителей."
                )

            render_dissertations_widget(
                subset=subset,
                key=f"ss_member_{i}_{slug(author_name)}",
                title="Результаты",
                expanded=False,
                file_name_prefix=f"поиск_школ_по_персоне_{slug(author_name)}",
            )
        share_params_button(share_params, key="school_search_share_member")
