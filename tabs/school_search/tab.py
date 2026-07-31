"""
Модуль Streamlit-вкладки «Поиск научных школ».
Импортируйте и вызывайте render_school_search_tab() в основном приложении.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import streamlit as st

from core.classifier import get_classifier_by_profile_source
from core.lineage.graph import lineage, rows_for, slug
from .search import (
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
from core.ui.table_display import build_dissertation_result_signature, render_dissertations_widget
from core.ui.tree_renderers import build_markmap_html
from core.ui.links import share_params_button
from core.search.text_matching import SEARCH_MODE_FAST, SEARCH_MODE_FUZZY, TEXT_SEARCH_MODE_LABELS
from core.ui.science_filtering import get_science_filtered_lineage_context
from core.ui.filters import (
    hydrate_profile_source_from_query_params,
    hydrate_science_fields_from_query_params,
    render_profile_source_radio,
    render_science_field_filter,
    science_field_filter_caption,
    science_fields_to_query_params,
)
from core.db import (
    get_score_columns_for_classifier_node,
)
from core.lineage.membership import get_cached_roots
from core.semantic.models import QueryRankingConfig, build_section_selection
from tabs.dissertation_characteristics.labels import SEARCHABLE_SECTION_KEYS, SECTION_LABELS_RU


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
    "semantic_query":     "🔎 5.2 Нейросетевой поиск научных школ",
    "semantic_similar":   "🧭 5.3 Поиск похожих научных школ",
}

# Режимы, для которых параметр scope не применяется
_SCOPE_INDEPENDENT_MODES = {"depth", "supervisor_rate"}
_TEXT_SEARCH_MODES = {"city", "org_prepared", "org_defense", "org_leading", "opponent"}


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


def _clean_optional_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "nat"}:
        return ""
    return text


def _normalize_name(name: str) -> str:
    return " ".join(_clean_optional_text(name).lower().replace("ё", "е").split())


def _build_reverse_lineage_rows(subset: pd.DataFrame) -> pd.DataFrame:
    if subset.empty or AUTHOR_COLUMN not in subset.columns:
        return pd.DataFrame(columns=["Диссертант", "Научный руководитель", "Научный руководитель 2"])

    rows: List[Dict[str, str]] = []
    for _, row in subset.iterrows():
        dissertation_name = _clean_optional_text(row.get(AUTHOR_COLUMN, ""))
        if not dissertation_name:
            continue
        sup_1 = (
            _clean_optional_text(row.get(SUPERVISOR_COLUMNS[0], ""))
            if SUPERVISOR_COLUMNS[0] in subset.columns
            else ""
        )
        sup_2 = (
            _clean_optional_text(row.get(SUPERVISOR_COLUMNS[1], ""))
            if SUPERVISOR_COLUMNS[1] in subset.columns
            else ""
        )
        if not sup_1 and not sup_2:
            continue
        rows.append(
            {
                "Диссертант": dissertation_name,
                "Научный руководитель": sup_1 or "—",
                "Научный руководитель 2": sup_2,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Диссертант", "Научный руководитель", "Научный руководитель 2"])

    result = pd.DataFrame(rows).drop_duplicates(ignore_index=True)
    if (
        "Научный руководитель 2" in result.columns
        and not result["Научный руководитель 2"].astype(str).str.strip().any()
    ):
        result = result.drop(columns=["Научный руководитель 2"])
    return result


def _build_reverse_lineage_graph(subset: pd.DataFrame, root_name: str) -> nx.DiGraph:
    graph = nx.DiGraph()
    root_name = _clean_optional_text(root_name)
    if not root_name:
        return graph

    graph.add_node(root_name)
    if subset.empty or AUTHOR_COLUMN not in subset.columns:
        return graph

    by_author_rows: Dict[str, List[pd.Series]] = {}
    for _, row in subset.iterrows():
        author = _clean_optional_text(row.get(AUTHOR_COLUMN, ""))
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
                    supervisor = _clean_optional_text(row.get(sup_col, ""))
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
        if "_school_search_pending_signature" in st.session_state:
            st.session_state["school_search_last_signature"] = st.session_state["_school_search_pending_signature"]
            st.session_state["school_search_last_payload"] = {
                "kind": "table",
                "result_df": result_df,
                "metric_col": metric_col,
                "chart_title": chart_title,
                "matched_map": matched_map,
                "key_prefix": key_prefix,
            }
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
        st.warning("Не удалось построить диаграмму для текущих результатов.")

    # Таблица
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    # Варианты написания
    if matched_map:
        _show_matched_variants(matched_map, result_df, key_prefix)

    excel_bytes = None
    payload = st.session_state.get("school_search_last_payload", {})
    pending_signature = st.session_state.get("_school_search_pending_signature")
    last_signature = st.session_state.get("school_search_last_signature")
    if isinstance(payload, dict) and pending_signature is not None and last_signature == pending_signature:
        excel_bytes = payload.get("excel_bytes")
    if excel_bytes is None:
        try:
            excel_bytes = build_excel_search_results(
                result_df=result_df,
                search_mode=search_mode,
                search_params=search_params,
            )
        except Exception:
            st.warning("Не удалось сформировать Excel-файл для результатов.")
            excel_bytes = None
    if excel_bytes is not None:
        st.download_button(
            label="📥 Скачать результаты (Excel)",
            data=excel_bytes,
            file_name="поиск_научных_школ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_dl_excel",
        )

    if "_school_search_pending_signature" in st.session_state:
        st.session_state["school_search_last_signature"] = st.session_state["_school_search_pending_signature"]
        st.session_state["school_search_last_payload"] = {
            "kind": "table",
            "result_df": result_df,
            "metric_col": metric_col,
            "chart_title": chart_title,
            "matched_map": matched_map,
            "key_prefix": key_prefix,
            "excel_bytes": excel_bytes,
            "search_mode": search_mode,
            "search_params": search_params,
        }


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ==============================================================================


def render_school_search_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    *,
    db_signature,
) -> None:
    """
    Отрисовывает вкладку «Поиск научных школ».

    Аргументы:
        df            — основной DataFrame с диссертациями
        idx           — индекс имён
    """
    st.subheader("Поиск научных школ")

    if not st.session_state.get("school_search_query_hydrated", False):
        mode_q = str(st.query_params.get("mode", "")).strip()
        if mode_q in SEARCH_MODES:
            st.session_state["school_search_mode"] = mode_q

        top_q = str(st.query_params.get("top_n", "")).strip()
        if top_q.isdigit() and int(top_q) in TOP_N_OPTIONS:
            st.session_state["school_search_top_n"] = int(top_q)

        scope_q = str(st.query_params.get("scope", "")).strip()
        scope_keys = list(SCOPE_LABELS.keys())
        if scope_q in scope_keys:
            st.session_state["school_search_scope"] = scope_keys.index(scope_q)

        year_from_q = str(st.query_params.get("year_from", "")).strip()
        if year_from_q.isdigit():
            st.session_state["school_search_year_from"] = int(year_from_q)
        year_to_q = str(st.query_params.get("year_to", "")).strip()
        if year_to_q.isdigit():
            st.session_state["school_search_year_to"] = int(year_to_q)
        year_q = str(st.query_params.get("year", "")).strip()
        if year_q.isdigit():
            st.session_state["school_search_year"] = int(year_q)

        city_q = str(st.query_params.get("city_query", "")).strip()
        if city_q:
            st.session_state["school_search_city"] = city_q

        org_q = str(st.query_params.get("org_query", "")).strip()
        if org_q:
            st.session_state["school_search_org_org_prepared"] = org_q
            st.session_state["school_search_org_org_defense"] = org_q
            st.session_state["school_search_org_org_leading"] = org_q

        person_q = str(st.query_params.get("person_query", "")).strip()
        if person_q:
            if mode_q == "member":
                st.session_state["school_search_person_member"] = person_q
            elif mode_q == "opponent":
                st.session_state["school_search_person_opponent"] = person_q
        text_search_mode_q = str(st.query_params.get("text_search_mode", "")).strip()
        if text_search_mode_q in {SEARCH_MODE_FAST, SEARCH_MODE_FUZZY}:
            st.session_state["school_search_text_search_mode"] = text_search_mode_q

        science_fields_q = hydrate_science_fields_from_query_params()
        if science_fields_q:
            st.session_state["school_search_science_fields_query"] = science_fields_q

        profile_source_q = str(st.query_params.get("profile_source", "")).strip()
        if profile_source_q:
            st.session_state["school_search_profile_source_query"] = profile_source_q

        classifier_node_q = str(st.query_params.get("classifier_node", "")).strip()
        if classifier_node_q:
            st.session_state["school_search_classifier_node_query"] = classifier_node_q

        for number in range(1, 4):
            value = str(st.query_params.get(f"semantic_query_{number}", "")).strip()
            if value:
                st.session_state[f"school_search_semantic_query_{number}"] = value
        semantic_source = str(st.query_params.get("semantic_source_root", "")).strip()
        if semantic_source:
            st.session_state["school_search_semantic_source_root_query"] = semantic_source
        ranking_q = str(st.query_params.get("semantic_ranking_mode", "")).strip()
        if ranking_q in {"broad", "focused"}:
            st.session_state["school_search_semantic_ranking_mode"] = ranking_q
        sections_mode_q = str(st.query_params.get("semantic_sections_mode", "")).strip()
        if sections_mode_q in {"all", "selected"}:
            target = "school_search_semantic_sections_mode" if mode_q == "semantic_query" else "school_search_similar_sections_mode"
            st.session_state[target] = sections_mode_q
        section_values = st.query_params.get_all("semantic_section")
        valid_sections = [key for key in section_values if key in SEARCHABLE_SECTION_KEYS]
        if valid_sections:
            target = "school_search_semantic_sections" if mode_q == "semantic_query" else "school_search_similar_sections"
            st.session_state[target] = valid_sections
        numeric_semantic_params = {
            "semantic_min_school_size": ("school_search_semantic_min_school" if mode_q == "semantic_query" else "school_search_similar_min_school", int),
            "semantic_min_profiled": ("school_search_semantic_min_profiled" if mode_q == "semantic_query" else "school_search_similar_min_profiled", int),
            "semantic_relevance_threshold": ("school_search_semantic_threshold", float),
            "semantic_year_from": ("school_search_semantic_year_from", int),
            "semantic_year_to": ("school_search_semantic_year_to", int),
            "semantic_duplicate_jaccard": ("school_search_similar_jaccard", float),
        }
        for query_name, (state_name, converter) in numeric_semantic_params.items():
            raw = str(st.query_params.get(query_name, "")).strip()
            try:
                if raw:
                    st.session_state[state_name] = converter(raw)
            except ValueError:
                pass
        coverage_q = str(st.query_params.get("semantic_min_coverage", "")).strip()
        try:
            if coverage_q:
                target = "school_search_semantic_min_coverage" if mode_q == "semantic_query" else "school_search_similar_coverage"
                st.session_state[target] = round(float(coverage_q) * 100)
        except ValueError:
            pass
        degrees_q = st.query_params.get_all("semantic_degree")
        if degrees_q:
            st.session_state["school_search_semantic_degrees"] = degrees_q
        hide_q = str(st.query_params.get("semantic_hide_duplicates", "")).casefold()
        if hide_q in {"1", "true", "yes", "да", "0", "false", "no", "нет"}:
            st.session_state["school_search_similar_hide_duplicates"] = hide_q in {"1", "true", "yes", "да"}

        if mode_q:
            st.session_state["school_search_run_state"] = True
        st.session_state["school_search_query_hydrated"] = True

    # ==========================================================================
    # 0. Общие параметры поиска
    # ==========================================================================
    st.markdown("### Фильтр отраслей наук")
    default_science_fields = st.session_state.pop(
        "school_search_science_fields_query",
        hydrate_science_fields_from_query_params(),
    )
    science_field_ids = render_science_field_filter(
        key_prefix="school_search",
        default_selected_ids=default_science_fields,
    )
    st.caption(science_field_filter_caption(science_field_ids))

    lineage_context = get_science_filtered_lineage_context(
        df=df,
        base_idx=idx,
        db_signature=db_signature,
        selected_ids=science_field_ids,
        supervisor_columns=SUPERVISOR_COLUMNS,
    )
    working_df = lineage_context.df
    working_idx = lineage_context.idx
    lineage_context_key = lineage_context.cache_key

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
        text_search_mode = st.radio(
            "Режим текстового поиска",
            options=[SEARCH_MODE_FAST, SEARCH_MODE_FUZZY],
            format_func=lambda value: TEXT_SEARCH_MODE_LABELS[value],
            index=0,
            key="school_search_text_search_mode",
        )
        st.caption("В быстром режиме ищется строгое вхождение введённого текста. Нечёткий поиск учитывает варианты написания, но может выполняться существенно дольше.")
        extra_params = {"city_query": city_query, "text_search_mode": text_search_mode}

    elif search_mode in ("org_prepared", "org_defense", "org_leading"):
        labels = {
            "org_prepared": "Название организации выполнения",
            "org_defense":  "Название организации (места) защиты",
            "org_leading":  "Название ведущей организации",
        }
        st.markdown("### 🏢 Организация")
        st.caption("В быстром режиме ищется строгое вхождение введённого текста. Нечёткий поиск учитывает варианты написания, но может выполняться существенно дольше.")
        org_query = st.text_input(
            labels[search_mode],
            placeholder="например, МГУ или Педагогический университет",
            key=f"school_search_org_{search_mode}",
        )
        text_search_mode = st.radio(
            "Режим текстового поиска",
            options=[SEARCH_MODE_FAST, SEARCH_MODE_FUZZY],
            format_func=lambda value: TEXT_SEARCH_MODE_LABELS[value],
            index=0,
            key="school_search_text_search_mode",
        )
        extra_params = {"org_query": org_query, "text_search_mode": text_search_mode}

    elif search_mode == "classifier_score":
        st.markdown("### 🔬 Узел классификатора")
        default_source_id = st.session_state.pop(
            "school_search_profile_source_query",
            None,
        ) or hydrate_profile_source_from_query_params()

        source = render_profile_source_radio(
            key="school_search_profile_source",
            default_id=default_source_id,
        )
        classifier = get_classifier_by_profile_source(source.id)
        st.caption(f"Активный профиль: {source.label}")

        selectable = []
        for code, title, _disabled in classifier:
            cols = get_score_columns_for_classifier_node(
                code,
                table_name=source.score_table,
                key_column=source.key_column,
            )
            if cols:
                selectable.append((code, title))

        if not selectable:
            st.warning("Нет доступных для выбора узлов классификатора.")
            return

        node_options = [f"{code} — {title}" for code, title in selectable]
        node_codes = [code for code, _ in selectable]
        choice_key = f"school_search_classifier_node_{source.id}"
        node_query = st.session_state.pop("school_search_classifier_node_query", None)
        if node_query in node_codes:
            query_label = node_options[node_codes.index(node_query)]
            if choice_key not in st.session_state:
                st.session_state[choice_key] = query_label

        chosen_label = st.selectbox(
            "Выберите узел классификатора",
            options=node_options,
            key=choice_key,
            help="Выберите узел — школы будут ранжированы по среднему баллу по всем признакам-потомкам этого узла.",
        )
        chosen_idx = node_options.index(chosen_label)
        classifier_node = node_codes[chosen_idx]
        extra_params = {
            "classifier_node": classifier_node,
            "profile_source": source.id,
        }

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
        if search_mode == "member":
            st.caption("Введите точное ФИО автора диссертации.")
            person_query = st.text_input(
                label_map[search_mode],
                placeholder=placeholder_map[search_mode],
                key="school_search_person_member",
            )
        else:
            person_query = st.text_input(
                label_map[search_mode],
                placeholder=placeholder_map[search_mode],
                key=f"school_search_person_{search_mode}",
            )
        if search_mode == "opponent":
            st.caption("В быстром режиме ищется строгое вхождение введённого текста. Нечёткий поиск учитывает варианты написания, но может выполняться существенно дольше.")
            text_search_mode = st.radio(
                "Режим текстового поиска",
                options=[SEARCH_MODE_FAST, SEARCH_MODE_FUZZY],
                format_func=lambda value: TEXT_SEARCH_MODE_LABELS[value],
                index=0,
                key="school_search_text_search_mode",
            )
            extra_params = {"person_query": person_query, "text_search_mode": text_search_mode}
        else:
            extra_params = {"person_query": person_query}

    elif search_mode == "semantic_query":
        st.markdown("### 🔎 Смысловой запрос")
        queries = [st.text_input(
            f"Запрос {number}", key=f"school_search_semantic_query_{number}",
            placeholder="Опишите тематику или направление исследования",
        ) for number in range(1, 4)]
        ranking_mode = st.radio(
            "Цель ранжирования", options=["broad", "focused"],
            format_func=lambda value: "Широкая специализация школы" if value == "broad" else "Сильное направление внутри школы",
            key="school_search_semantic_ranking_mode",
        )
        sections_mode = st.radio(
            "Разделы характеристик", options=["all", "selected"],
            format_func=lambda value: "Все доступные характеристики" if value == "all" else "Выбранные характеристики",
            key="school_search_semantic_sections_mode",
        )
        selected_sections = SEARCHABLE_SECTION_KEYS
        if sections_mode == "selected":
            selected_sections = st.multiselect(
                "Выберите разделы", SEARCHABLE_SECTION_KEYS,
                format_func=lambda key: SECTION_LABELS_RU[key],
                default=["research_goal", "research_methods", "scientific_novelty"],
                key="school_search_semantic_sections",
            )
        min_coverage = st.slider("Минимальное покрытие разделов, %", 0, 100, 60, 5, key="school_search_semantic_min_coverage") / 100
        col_a, col_b = st.columns(2)
        with col_a:
            min_school = st.number_input("Минимальный размер школы", 1, 1000, 3, key="school_search_semantic_min_school")
            year_from = st.number_input("Год от (0 — без ограничения)", 0, 2100, 0, key="school_search_semantic_year_from")
        with col_b:
            min_profiled = st.number_input("Минимум диссертаций с векторами", 1, 1000, 3, key="school_search_semantic_min_profiled")
            year_to = st.number_input("Год до (0 — без ограничения)", 0, 2100, 0, key="school_search_semantic_year_to")
        degree_column = next((name for name in ("degree.degree_level", "degree_level") if name in working_df.columns), None)
        degree_options = sorted(working_df[degree_column].dropna().astype(str).unique()) if degree_column else []
        degree_levels = st.multiselect("Уровни учёной степени", degree_options, key="school_search_semantic_degrees")
        threshold = st.slider("Порог релевантности", -1.0, 1.0, 0.50, 0.05, key="school_search_semantic_threshold")
        extra_params = {
            "queries": queries, "ranking_mode": ranking_mode, "sections_mode": sections_mode,
            "section_keys": tuple(selected_sections), "min_coverage": min_coverage,
            "minimum_school_size": int(min_school), "minimum_profiled": int(min_profiled),
            "year_from": int(year_from) or None, "year_to": int(year_to) or None,
            "degree_levels": tuple(degree_levels), "relevance_threshold": threshold,
        }

    elif search_mode == "semantic_similar":
        st.markdown("### 🧭 Исходная научная школа")
        roots = get_cached_roots(working_df, db_signature, context_key=lineage_context_key)
        source_query = st.session_state.pop("school_search_semantic_source_root_query", None)
        if source_query in roots and "school_search_semantic_source_root" not in st.session_state:
            st.session_state["school_search_semantic_source_root"] = source_query
        source_root = st.selectbox("Научный руководитель", roots, key="school_search_semantic_source_root") if roots else ""
        sections_mode = st.radio(
            "Разделы характеристик", ["all", "selected"],
            format_func=lambda value: "Все доступные характеристики" if value == "all" else "Выбранные характеристики",
            key="school_search_similar_sections_mode",
        )
        selected_sections = SEARCHABLE_SECTION_KEYS
        if sections_mode == "selected":
            selected_sections = st.multiselect(
                "Выберите разделы", SEARCHABLE_SECTION_KEYS, format_func=lambda key: SECTION_LABELS_RU[key],
                default=["research_goal", "research_methods", "scientific_novelty"], key="school_search_similar_sections",
            )
        min_coverage = st.slider("Минимальное покрытие разделов, %", 0, 100, 60, 5, key="school_search_similar_coverage") / 100
        min_school = st.number_input("Минимальный размер школы", 1, 1000, 3, key="school_search_similar_min_school")
        min_profiled = st.number_input("Минимум диссертаций с векторами", 1, 1000, 3, key="school_search_similar_min_profiled")
        hide_duplicates = st.checkbox("Скрывать почти совпадающие по составу школы", True, key="school_search_similar_hide_duplicates")
        duplicate_jaccard = st.slider("Порог пересечения Жаккара", 0.0, 1.0, 0.80, 0.05, key="school_search_similar_jaccard")
        extra_params = {
            "source_root": source_root, "sections_mode": sections_mode,
            "section_keys": tuple(selected_sections), "min_coverage": min_coverage,
            "minimum_school_size": int(min_school), "minimum_profiled": int(min_profiled),
            "hide_near_duplicates": hide_duplicates, "near_duplicate_jaccard": duplicate_jaccard,
        }

    # ==========================================================================
    # 2. Кнопка «Найти»
    # ==========================================================================
    st.markdown("---")

    with st.form("school_search_form", clear_on_submit=False):
        run_btn = st.form_submit_button("🔍 Найти", type="primary")
    if run_btn:
        st.session_state["school_search_run_state"] = True

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
    if search_mode == "semantic_query" and not any(str(value).strip() for value in extra_params["queries"]):
        st.warning("Введите хотя бы один непустой запрос.")
        return
    if search_mode.startswith("semantic_") and not extra_params.get("section_keys"):
        st.warning("Выберите хотя бы один раздел характеристики.")
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
        **science_fields_to_query_params(science_field_ids),
    }
    if search_mode == "semantic_query":
        share_params = {
            "tab": "school_search", "mode": search_mode, "scope": scope, "top_n": top_n,
            **{f"semantic_query_{number}": value for number, value in enumerate(extra_params["queries"], 1) if str(value).strip()},
            "semantic_ranking_mode": extra_params["ranking_mode"],
            "semantic_sections_mode": extra_params["sections_mode"],
            "semantic_section": list(extra_params["section_keys"]),
            "semantic_min_coverage": extra_params["min_coverage"],
            "semantic_min_school_size": extra_params["minimum_school_size"],
            "semantic_min_profiled": extra_params["minimum_profiled"],
            "semantic_relevance_threshold": extra_params["relevance_threshold"],
            "semantic_year_from": extra_params["year_from"], "semantic_year_to": extra_params["year_to"],
            "semantic_degree": list(extra_params["degree_levels"]),
            **science_fields_to_query_params(science_field_ids),
        }
    elif search_mode == "semantic_similar":
        share_params = {
            "tab": "school_search", "mode": search_mode, "scope": scope, "top_n": top_n,
            "semantic_source_root": extra_params["source_root"],
            "semantic_sections_mode": extra_params["sections_mode"],
            "semantic_section": list(extra_params["section_keys"]),
            "semantic_min_coverage": extra_params["min_coverage"],
            "semantic_min_school_size": extra_params["minimum_school_size"],
            "semantic_min_profiled": extra_params["minimum_profiled"],
            "semantic_hide_duplicates": extra_params["hide_near_duplicates"],
            "semantic_duplicate_jaccard": extra_params["near_duplicate_jaccard"],
            **science_fields_to_query_params(science_field_ids),
        }

    current_signature = {
        "mode": search_mode,
        "scope": scope,
        "top_n": top_n,
        "extra_params": extra_params,
        "science_field_ids": tuple(sorted(science_field_ids)),
        "db_signature": db_signature,
    }
    st.session_state["_school_search_pending_signature"] = current_signature

    if run_btn:
        st.session_state["school_search_execute_signature"] = current_signature
    if st.session_state.get("school_search_run_state", False) and "school_search_execute_signature" not in st.session_state:
        st.session_state["school_search_execute_signature"] = current_signature
    execute_signature = st.session_state.get("school_search_execute_signature")
    if execute_signature != current_signature:
        return

    if not st.session_state.get("school_search_run_state", False):
        return

    if search_mode in {"semantic_query", "semantic_similar"}:
        from core.db.dissertation_sections import (
            get_dissertation_sections_db_signature, load_dissertation_section_texts_by_ids,
            load_typed_vector_metadata,
        )
        from .exports import build_semantic_query_search_excel, build_similar_school_search_excel
        from .semantic import search_schools_by_semantic_query, search_similar_scientific_schools

        selection = build_section_selection(
            extra_params["sections_mode"], extra_params["section_keys"],
            min_coverage=extra_params["min_coverage"],
        )
        stored = st.session_state.get("school_search_semantic_result")
        current_metadata = load_typed_vector_metadata() if stored is not None else None
        stored_valid = bool(
            stored
            and stored.get("base_signature") == current_signature
            and current_metadata is not None
            and stored["result"].parameters.get("section_database_signature") == get_dissertation_sections_db_signature()
            and stored["result"].parameters.get("matrix_signature") == current_metadata.matrix_signature
            and stored["result"].parameters.get("model_name") == current_metadata.model_name
            and stored["result"].parameters.get("normalized") == current_metadata.normalized
        )
        if not stored_valid:
            stored = None
            st.session_state.pop("school_search_semantic_result", None)
        if stored is None:
          with st.spinner("Выполняется семантический анализ научных школ…"):
            if search_mode == "semantic_query":
                config = QueryRankingConfig(
                    extra_params["ranking_mode"], extra_params["relevance_threshold"], 5.0,
                    extra_params["minimum_school_size"], extra_params["minimum_profiled"],
                )
                result = search_schools_by_semantic_query(
                    queries=extra_params["queries"], df=working_df, idx=working_idx,
                    lineage_context_key=lineage_context_key, scope=scope, selection=selection,
                    ranking_config=config, top_n=top_n, year_from=extra_params["year_from"],
                    year_to=extra_params["year_to"], degree_levels=extra_params["degree_levels"],
                    main_db_signature=db_signature,
                )
                excel = build_semantic_query_search_excel(result)
                file_name = "семантический_поиск_научных_школ.xlsx"
            else:
                result = search_similar_scientific_schools(
                    source_root=extra_params["source_root"], df=working_df, idx=working_idx,
                    lineage_context_key=lineage_context_key, scope=scope, selection=selection,
                    minimum_school_size=extra_params["minimum_school_size"],
                    minimum_profiled_dissertations=extra_params["minimum_profiled"], top_n=top_n,
                    hide_near_duplicates=extra_params["hide_near_duplicates"],
                    near_duplicate_jaccard=extra_params["near_duplicate_jaccard"],
                    main_db_signature=db_signature,
                )
                excel = build_similar_school_search_excel(result)
                file_name = "поиск_похожих_научных_школ.xlsx"
          st.session_state["school_search_semantic_result"] = {
              "base_signature": current_signature, "result": result,
              "excel_bytes": excel, "file_name": file_name,
          }
        else:
            result = stored["result"]
            excel = stored["excel_bytes"]
            file_name = stored["file_name"]
        if search_mode == "semantic_query":
            columns = {
                "rank": "Ранг", "root": "Научный руководитель", "ranking_score": "Оценка ранжирования",
                "total_members": "Всего членов школы", "filtered_members": "Членов после фильтров",
                "covered_dissertations": "Диссертаций с векторами", "coverage_ratio": "Полнота данных, %",
                "mean_similarity": "Среднее сходство", "median_similarity": "Медианное сходство",
                "upper_quartile_similarity": "Верхний квартиль сходства", "top_20_percent_mean": "Среднее лучших 20 %",
                "share_above_threshold": "Доля выше порога, %", "maximum_similarity": "Максимальное сходство",
                "year_range": "Период активности",
            }
            display = pd.DataFrame({label: result.summary[key] for key, label in columns.items() if key in result.summary})
            for column in ("Полнота данных, %", "Доля выше порога, %"):
                if column in display:
                    display[column] *= 100.0
        else:
            columns = {
                "rank": "Ранг", "root": "Научный руководитель", "semantic_similarity": "Семантическое сходство",
                "common_section_count": "Общих разделов характеристик", "profiled_dissertations": "Диссертаций с векторами",
                "coverage_ratio": "Полнота данных, %", "jaccard_overlap": "Пересечение состава по Жаккару",
                "total_members": "Всего членов школы", "year_range": "Период активности",
            }
            display = pd.DataFrame({label: result.summary[key] for key, label in columns.items() if key in result.summary})
            if "Полнота данных, %" in display:
                display["Полнота данных, %"] *= 100.0
        for diagnostic in result.diagnostics:
            st.warning(diagnostic)
        if not display.empty:
            metric = "Оценка ранжирования" if search_mode == "semantic_query" else "Семантическое сходство"
            st.pyplot(_bar_chart(display, "Научный руководитель", metric, mode_label))
            st.dataframe(display, use_container_width=True, hide_index=True)
            for root, details in result.dissertation_details.items():
                with st.expander(f"Лучшие диссертации: {root}"):
                    if search_mode == "semantic_query":
                        detail_columns = {
                            "candidate_name": "Автор", "title": "Название", "year": "Год",
                            "degree.science_field": "Отрасль науки", "science_field": "Отрасль науки",
                            "semantic_score": "Семантическое сходство", "coverage": "Полнота характеристик, %",
                            "best_section_key": "Лучший раздел", "best_section_similarity": "Сходство лучшего раздела",
                        }
                    else:
                        detail_columns = {
                            "candidate_name": "Автор", "title": "Название", "year": "Год",
                            "distance_to_source": "Расстояние до профиля исходной школы",
                            "coverage": "Полнота характеристик, %", "representative": "Репрезентативная работа",
                        }
                    shown = pd.DataFrame({label: details[key] for key, label in detail_columns.items() if key in details})
                    if "Полнота характеристик, %" in shown:
                        shown["Полнота характеристик, %"] *= 100.0
                    if "Лучший раздел" in shown:
                        shown["Лучший раздел"] = shown["Лучший раздел"].map(SECTION_LABELS_RU)
                    st.dataframe(shown, use_container_width=True, hide_index=True)
                    contribution_rows = []
                    for record in details.to_dict("records"):
                        for section_key, score in (record.get("section_scores") or {}).items():
                            contribution_rows.append({
                                "Автор": record.get("candidate_name"),
                                "Раздел характеристики": SECTION_LABELS_RU.get(section_key, section_key),
                                "Сходство": score,
                            })
                    if contribution_rows:
                        st.markdown("##### Вклад разделов характеристик")
                        st.dataframe(pd.DataFrame(contribution_rows), use_container_width=True, hide_index=True)
                    if search_mode == "semantic_query" and st.button(
                        "Показать лучше всего совпавшие фрагменты", key=f"school_search_best_text_{slug(root)}",
                    ):
                        ids = [value for value in details.get("best_text_id", []) if pd.notna(value)]
                        texts = load_dissertation_section_texts_by_ids(ids)
                        for text_row in texts.itertuples(index=False):
                            with st.expander("Лучше всего совпавший фрагмент"):
                                st.markdown(f"**{SECTION_LABELS_RU.get(text_row.section_key, text_row.section_key)}**")
                                st.write(text_row.text)
                    if search_mode == "semantic_similar" and root in result.section_similarities:
                        st.markdown("##### Сходство по разделам характеристик")
                        st.dataframe(result.section_similarities[root], use_container_width=True, hide_index=True)
                    detail_codes = set(details.get("Code", pd.Series(dtype=str)).astype(str))
                    detail_subset = working_df[working_df.get("Code", pd.Series(index=working_df.index, dtype=str)).astype(str).isin(detail_codes)]
                    if not detail_subset.empty:
                        render_dissertations_widget(
                            subset=detail_subset, key=f"school_search_semantic_details_{slug(root)}",
                            title="Чтение и скачивание авторефератов", expanded=False,
                            file_name_prefix=f"семантический_поиск_{slug(root)}",
                            result_signature=build_dissertation_result_signature(
                                detail_subset, context_parts=(current_signature, root),
                            ),
                        )
            st.download_button("Скачать результаты в Excel", excel, file_name=file_name,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key=f"school_search_semantic_download_{search_mode}")
            share_params_button(share_params, key=f"school_search_share_{search_mode}")
        return
    if (
        st.session_state.get("school_search_last_signature") == current_signature
        and "school_search_last_payload" in st.session_state
    ):
        payload = st.session_state["school_search_last_payload"]
        if payload.get("kind") == "table":
            _render_results(
                payload["result_df"],
                metric_col=payload["metric_col"],
                chart_title=payload["chart_title"],
                matched_map=payload.get("matched_map"),
                key_prefix=payload["key_prefix"],
                search_mode=mode_label,
                search_params=params_for_excel,
            )
            if not payload["result_df"].empty:
                share_params_button(share_params, key=f"school_search_share_cached_{search_mode}")
            return
        if payload.get("kind") == "member":
            member_results = payload.get("member_results", [])
            if not member_results:
                st.warning("По заданным параметрам ничего не найдено.")
                return
            st.success(f"Найдено вариантов ФИО авторов: {len(member_results)}")
            for i, item in enumerate(member_results, start=1):
                author_name = str(item["author_name"])
                chain_names = item["chain_names"]
                subset = item["subset"]
                reverse_table = _build_reverse_lineage_rows(subset)
                reverse_graph = _build_reverse_lineage_graph(subset, author_name)
                st.markdown(f"#### {i}. {author_name}")
                st.caption(" → ".join(chain_names) if chain_names else "Цепочка не найдена.")
                if not reverse_table.empty:
                    st.table(reverse_table)
                if reverse_graph.number_of_edges() > 0:
                    html_str, height_px = build_markmap_html(reverse_graph, author_name, branching_mode="unidirectional")
                    st.components.v1.html(html_str, height=height_px + 20, scrolling=False)
                render_dissertations_widget(
                    subset=subset,
                    key=f"ss_member_cached_{i}_{slug(author_name)}",
                    title="Результаты",
                    expanded=False,
                    file_name_prefix=f"поиск_школ_по_персоне_{slug(author_name)}",
                    result_signature=build_dissertation_result_signature(
                        subset,
                        context_parts=(current_signature, "member_cached", i, author_name),
                    ),
                )
            share_params_button(share_params, key="school_search_share_member_cached")
            return

    # --------------------------------------------------------------------------
    # ГРУППА 1: По размеру школы
    # --------------------------------------------------------------------------
    if search_mode == "total_members":
        with st.spinner(spinner_msg):
            result_df = search_by_total_members(
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                scope=scope, top_n=top_n,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                year_from=extra_params["year_from"],
                year_to=extra_params["year_to"],
                scope=scope, top_n=top_n,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                year=year_val, scope=scope, top_n=top_n,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                top_n=top_n,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                scope=scope, top_n=top_n,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                city_query=extra_params["city_query"],
                scope=scope, top_n=top_n,
                use_fuzzy=extra_params.get("text_search_mode") == SEARCH_MODE_FUZZY,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                scope=scope, top_n=top_n,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                org_query=extra_params["org_query"],
                scope=scope, top_n=top_n,
                use_fuzzy=extra_params.get("text_search_mode") == SEARCH_MODE_FUZZY,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                org_query=extra_params["org_query"],
                scope=scope, top_n=top_n,
                use_fuzzy=extra_params.get("text_search_mode") == SEARCH_MODE_FUZZY,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                org_query=extra_params["org_query"],
                scope=scope, top_n=top_n,
                use_fuzzy=extra_params.get("text_search_mode") == SEARCH_MODE_FUZZY,
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                classifier_node=classifier_node,
                scope=scope, top_n=top_n,
                profile_source_id=extra_params["profile_source"],
                lineage_context_key=lineage_context_key,
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
                df=working_df, index=working_idx,
                lineage_func=lineage, rows_for_func=rows_for,
                person_query=extra_params["person_query"],
                scope=scope, top_n=top_n,
                use_fuzzy=extra_params.get("text_search_mode") == SEARCH_MODE_FUZZY,
                lineage_context_key=lineage_context_key,
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
                df=working_df,
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
                result_signature=build_dissertation_result_signature(
                    subset,
                    context_parts=(current_signature, "member", i, author_name),
                ),
            )
        st.session_state["school_search_last_signature"] = current_signature
        st.session_state["school_search_last_payload"] = {
            "kind": "member",
            "member_results": member_results,
        }
        share_params_button(share_params, key="school_search_share_member")
