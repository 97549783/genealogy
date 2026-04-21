"""
Модуль вкладки интерфейса «Анализ научной школы».
Импортируйте и вызывайте render_school_analysis_tab() в основном приложении.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from core.people import get_unique_supervisors
from utils.graph import lineage, rows_for
from utils.urls import share_params_button
from .analysis import (
    collect_school_subset,
    compute_overview,
    compute_metrics,
    compute_yearly_stats,
    compute_city_stats,
    compute_institutional_stats,
    compute_top_opponents,
    compute_thematic_profile,
    compute_continuity,

)
from .exports import build_excel_report



# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================

DEFAULT_SCORES_FOLDER = "basic_scores"

SCOPE_LABELS: Dict[str, str] = {
    "direct": "Только первое поколение (прямые ученики)",
    "all": "Все поколения (полное дерево)",
}


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================


def _get_all_supervisors(df: pd.DataFrame) -> List[str]:
    """Собирает сортированный список всех научных руководителей."""
    supervisor_cols = [
        col for col in df.columns
        if "supervisor" in col.lower() and "name" in col.lower()
    ]
    return get_unique_supervisors(df=df, supervisor_columns=supervisor_cols)


def _scores_folder_available(scores_folder: str) -> bool:
    """
    Проверяет наличие папки basic_scores с CSV-файлами.

    Проверяет оба варианта расположения:
    1. Текущая рабочая директория (CWD) — работает локально и в облачном развёртывании.
    2. Рядом с файлом самого модуля — запасной вариант.
    """
    p1 = Path(scores_folder)
    if p1.exists() and any(p1.glob("*.csv")):
        return True
    p2 = Path(__file__).parent / scores_folder
    if p2.exists() and any(p2.glob("*.csv")):
        return True
    return False


def _bar_chart(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> plt.Figure:
    """Столбчатая диаграмма для защит по годам с разбивкой по степени."""
    fig, ax = plt.subplots(figsize=(max(8, len(df) * 0.45), 4))

    candidate_col = "Кандидатских"
    doctor_col = "Докторских"
    xs = df[x_col].astype(str)

    if candidate_col in df.columns and doctor_col in df.columns:
        ax.bar(xs, df[candidate_col], label="Кандидатские", color="#4C9BE8")
        ax.bar(xs, df[doctor_col], bottom=df[candidate_col], label="Докторские", color="#E8834C")
        ax.legend(fontsize=9)
    else:
        ax.bar(xs, df[y_col], color="#4C9BE8")

    ax.set_xlabel(x_col, fontsize=10)
    ax.set_ylabel("Число защит", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig


def _clear_school_cache(root: str, scope: str) -> None:
    """Очищает кэш школы из session_state."""
    for s in ("direct", "all"):
        key = f"school_subset_{root}_{s}"
        if key in st.session_state:
            del st.session_state[key]


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ==============================================================================


def render_school_analysis_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    classifier: Optional[List[Tuple[str, str, bool]]] = None,
    scores_folder: str = DEFAULT_SCORES_FOLDER,
) -> None:
    """
    Отрисовывает вкладку «Анализ научной школы».

    Аргументы:
        df              — основной DataFrame с диссертациями
        idx             — индекс имён
        classifier      — THEMATIC_CLASSIFIER из streamlit_app.py
        scores_folder   — путь к basic_scores
    """
    st.subheader("Анализ научной школы")

    # =========================================================================
    # 0. Входные параметры
    # =========================================================================
    st.markdown("### \U0001f464 Выбор научной школы")

    all_supervisors = _get_all_supervisors(df)
    if not all_supervisors:
        st.error("В данных не найдены научные руководители.")
        return

    if not st.session_state.get("school_analysis_query_hydrated", False):
        root_q = str(st.query_params.get("analysis_root", "")).strip()
        if root_q and root_q in all_supervisors:
            st.session_state["school_analysis_root"] = root_q
        scope_q = str(st.query_params.get("analysis_scope", "")).strip()
        scope_keys = list(SCOPE_LABELS.keys())
        if scope_q in scope_keys:
            st.session_state["school_analysis_scope"] = scope_keys.index(scope_q)
        if root_q:
            st.session_state["school_analysis_run_state"] = True
        st.session_state["school_analysis_query_hydrated"] = True

    col_sel, col_scope = st.columns([2, 1])

    with col_sel:
        root = st.selectbox(
            "Научный руководитель (корень дерева)",
            options=all_supervisors,
            key="school_analysis_root",
            help="Школа анализируется от этого руководителя.",
        )

    with col_scope:
        scope_options = list(SCOPE_LABELS.keys())
        scope_idx = st.radio(
            "Глубина анализа",
            options=range(len(scope_options)),
            format_func=lambda i: SCOPE_LABELS[scope_options[i]],
            key="school_analysis_scope",
        )
        scope: str = scope_options[scope_idx]

    st.markdown("---")

    col_run, col_reset = st.columns([3, 1])
    with col_run:
        run_clicked = st.button("Построить анализ", key="school_analysis_run", type="primary")
    with col_reset:
        if st.button("Сбросить кэш", key="school_analysis_reset",
                     help="Очистить сохранённые результаты и пересчитать"):
            _clear_school_cache(root, scope)
            st.rerun()

    if run_clicked:
        st.session_state["school_analysis_run_state"] = True

    if not st.session_state.get("school_analysis_run_state", False):
        if f"school_subset_{root}_direct" not in st.session_state:
            return

    # =========================================================================
    # Сбор данных с кэшированием в session_state
    # =========================================================================
    key_direct = f"school_subset_{root}_direct"
    key_all = f"school_subset_{root}_all"

    with st.spinner("Сбор диссертаций школы..."):
        if key_direct not in st.session_state:
            st.session_state[key_direct] = collect_school_subset(
                df, idx, root, "direct", lineage, rows_for
            )
        if key_all not in st.session_state:
            st.session_state[key_all] = collect_school_subset(
                df, idx, root, "all", lineage, rows_for
            )

    subset_direct: pd.DataFrame = st.session_state[key_direct]
    subset_all: pd.DataFrame = st.session_state[key_all]
    subset: pd.DataFrame = subset_direct if scope == "direct" else subset_all

    if subset.empty:
        st.warning("Диссертаций для выбранной школы не найдено.")
        return

    # =========================================================================
    # 1. Обзорная карточка
    # =========================================================================
    st.markdown("### 1. Обзор")

    overview = compute_overview(
        subset=subset,
        root=root,
        index=idx,
        lineage_func=lineage,
        df_full=df,
        scope=scope,
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Всего диссертаций", overview["total"])
    c2.metric("Кандидатских", overview["candidates"])
    c3.metric("Докторских", overview["doctors"])
    c4.metric("Уникальных городов", overview["cities"])

    year_range = (
        f"{overview['year_min']}–{overview['year_max']}"
        if overview["year_min"] and overview["year_max"]
        else "—"
    )
    c5.metric("Период активности", year_range)

    if scope == "all" and overview["generations"] is not None:
        c6.metric("Поколений", overview["generations"])
    else:
        c6.metric("Поколений", "—")

    st.markdown("---")

    # =========================================================================
    # 2. Метрики
    # =========================================================================
    st.markdown("### 2. Метрики научной школы")

    with st.spinner("Вычисление метрик..."):
        metrics_df, generations_df = compute_metrics(
            df_full=df,
            index=idx,
            root=root,
            lineage_func=lineage,
            rows_for_func=rows_for,
            subset_direct=subset_direct,
            subset_all=subset_all,
        )

    st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    if not generations_df.empty:
        with st.expander("Распределение по поколениям", expanded=False):
            st.dataframe(generations_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 3. Защиты по годам
    # =========================================================================
    st.markdown("### 3. Защиты по годам")

    yearly_df = compute_yearly_stats(subset)

    if yearly_df.empty:
        st.info("Данные о годах защит отсутствуют.")
    else:
        fig_years = _bar_chart(
            yearly_df,
            x_col="Год",
            y_col="Всего",
            title=f"Динамика защит школы «{root}»",
        )
        st.pyplot(fig_years)
        plt.close(fig_years)

        with st.expander("Таблица: защиты по годам", expanded=False):
            st.dataframe(yearly_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 4. География
    # =========================================================================
    st.markdown("### 4. Географическое распределение")

    city_df = compute_city_stats(subset)

    if city_df.empty:
        st.info("Данные о городах защит отсутствуют.")
    else:
        st.dataframe(city_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 5. Институциональные распределения
    # =========================================================================
    st.markdown("### 5. Институциональные распределения")

    institutional = compute_institutional_stats(subset)

    _INST_LABELS = {
        "institution_prepared": "\U0001f3e2 Организация выполнения",
        "defense_location":     "\U0001f3db️ Место защиты",
        "leading_organization": "\U0001f393 Ведущая организация",
        "specialties":          "\U0001f52c Специальности",
    }

    for key, label in _INST_LABELS.items():
        tbl = institutional.get(key, pd.DataFrame())
        if tbl.empty:
            continue
        with st.expander(f"{label} — {len(tbl)} записей", expanded=False):
            st.dataframe(tbl, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 6. Топ-5 оппонентов
    # =========================================================================
    st.markdown("### 6. Топ-5 оппонентов")

    opponents_df = compute_top_opponents(subset, top_n=5)

    if opponents_df.empty:
        st.info("Данные об оппонентах отсутствуют.")
    else:
        st.dataframe(opponents_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 7. Тематический профиль
    # =========================================================================
    st.markdown("### 7. Тематический профиль школы")
    st.caption(
        "Средние баллы по всем диссертациям школы, для которых доступны оценки в basic_scores."
    )

    scores_available = _scores_folder_available(scores_folder)

    if not scores_available:
        st.info(
            f"Папка '{scores_folder}' не найдена или пуста. "
            "Тематический профиль недоступен."
        )
        education_df = pd.DataFrame()
        knowledge_df = pd.DataFrame()
    elif classifier is None:
        st.info("Классификатор не передан. Тематический профиль недоступен.")
        education_df = pd.DataFrame()
        knowledge_df = pd.DataFrame()
    else:
        with st.spinner("Вычисление тематического профиля..."):
            education_df, knowledge_df = compute_thematic_profile(
                subset=subset,
                scores_folder=scores_folder,
                classifier=classifier,
                group_prefix_education="1.1.1",
                group_prefix_knowledge="1.1.2",
            )

        with st.expander("\U0001f393 Уровень образования (1.1.1)", expanded=False):
            if education_df.empty:
                st.info("Нет данных для группы 1.1.1.")
            else:
                st.dataframe(education_df, use_container_width=True, hide_index=True)

        with st.expander("\U0001f52c Область знания (1.1.2)", expanded=False):
            if knowledge_df.empty:
                st.info("Нет данных для группы 1.1.2.")
            else:
                st.dataframe(knowledge_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 8. Преемственность
    # =========================================================================
    st.markdown("### 8. Ученики, ставшие научными руководителями")
    st.caption("Ученики из первого поколения, сами ставшие научными руководителями.")

    with st.spinner("Поиск учеников-руководителей..."):
        continuity_df = compute_continuity(
            df_full=df,
            index=idx,
            subset_direct=subset_direct,
            rows_for_func=rows_for,
        )

    if continuity_df.empty:
        st.info("Среди прямых учеников не найдено ни одного ставшего научным руководителем.")
    else:
        st.dataframe(continuity_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 9. Скачивание Excel-отчёта
    # =========================================================================
    st.markdown("### \U0001f4e5 Скачать полный отчёт")

    with st.spinner("Формируем Excel-файл..."):
        excel_bytes = build_excel_report(
            metrics_df=metrics_df,
            generations_df=generations_df,
            yearly_df=yearly_df if not yearly_df.empty else pd.DataFrame(),
            city_df=city_df if not city_df.empty else pd.DataFrame(),
            institutional=institutional,
            opponents_df=compute_top_opponents(subset, top_n=None),
            education_df=education_df if not education_df.empty else pd.DataFrame(),
            knowledge_df=knowledge_df if not knowledge_df.empty else pd.DataFrame(),
            continuity_df=continuity_df if not continuity_df.empty else pd.DataFrame(),
        )

    safe_name = root.replace(" ", "_").replace("/", "-")[:60]
    st.download_button(
        label="\U0001f4e5 Скачать полный отчёт (Excel)",
        data=excel_bytes,
        file_name=f"анализ_научной_школы_{safe_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="school_analysis_download_excel",
    )

    share_params_button(
        {
            "tab": "school_analysis",
            "analysis_root": root,
            "analysis_scope": scope,
        },
        key="school_analysis_share",
    )
