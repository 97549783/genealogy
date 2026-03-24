"""
Модуль Streamlit-вкладки «Анализ научной школы».
Импортируйте и вызывайте render_school_analysis_tab() в основном приложении.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from school_analysis import (
    collect_school_subset,
    compute_overview,
    compute_metrics,
    compute_yearly_stats,
    compute_city_stats,
    compute_institutional_stats,
    compute_top_opponents,
    compute_thematic_profile,
    compute_continuity,
    build_excel_report,
)


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
    all_supervisors: Set[str] = set()
    for col in supervisor_cols:
        if col in df.columns:
            all_supervisors.update(
                str(v).strip() for v in df[col].dropna().unique() if str(v).strip()
            )
    return sorted(all_supervisors)


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
    ax.set_ylabel(Число защит", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ==============================================================================


def render_school_analysis_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
    classifier: Optional[List[Tuple[str, str, bool]]] = None,
    scores_folder: str = DEFAULT_SCORES_FOLDER,
) -> None:
    """
    Отрисовывает вкладку «Анализ научной школы».

    Аргументы:
        df              — основной DataFrame с диссертациями
        idx             — индекс имён
        lineage_func    — функция построения дерева преемственности
        rows_for_func   — функция поиска строк по имени
        classifier      — THEMATIC_CLASSIFIER из streamlit_app.py (пара (code, name, leaf))
        scores_folder   — путь к basic_scores
    """
    st.subheader("Анализ научной школы")

    # =========================================================================
    # 0. Входные параметры
    # =========================================================================
    st.markdown("### 👤 Выбор научной школы")

    all_supervisors = _get_all_supervisors(df)
    if not all_supervisors:
        st.error("В данных не найдены научные руководители.")
        return

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

    if not st.button("Построить анализ", key="school_analysis_run", type="primary"):
        return

    # =========================================================================
    # Сбор данных
    # =========================================================================
    with st.spinner("Сбор диссертаций школы..."):
        subset = collect_school_subset(df, idx, root, scope, lineage_func, rows_for_func)
        subset_direct = collect_school_subset(df, idx, root, "direct", lineage_func, rows_for_func)
        subset_all = collect_school_subset(df, idx, root, "all", lineage_func, rows_for_func)

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
        lineage_func=lineage_func,
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
            lineage_func=lineage_func,
            rows_for_func=rows_for_func,
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
        "institution_prepared": "🏢 Организация выполнения",
        "defense_location":     "🏛️ Место защиты",
        "leading_organization": "🎓 Ведущая организация",
        "specialties":          "🔬 Специальности",
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

    scores_path = Path(scores_folder)
    scores_available = scores_path.exists() and any(scores_path.glob("*.csv"))

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
                group_prefix_level="",
                group_prefix_education="1.1.1",
                group_prefix_knowledge="1.1.2",
            )

        with st.expander("🎓 Уровень образования (1.1.1)", expanded=False):
            if education_df.empty:
                st.info("Нет данных для группы 1.1.1.")
            else:
                st.dataframe(education_df, use_container_width=True, hide_index=True)

        with st.expander("🔬 Область знания (1.1.2)", expanded=False):
            if knowledge_df.empty:
                st.info("Нет данных для группы 1.1.2.")
            else:
                st.dataframe(knowledge_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 8. Преемственность
    # =========================================================================
    st.markdown("### 8. Преемственность")
    st.caption("Ученики из первого поколения, сами ставшие научными руководителями.")

    with st.spinner("Поиск учеников-руководителей..."):
        continuity_df = compute_continuity(
            df_full=df,
            index=idx,
            subset_direct=subset_direct,
            rows_for_func=rows_for_func,
        )

    if continuity_df.empty:
        st.info("Среди прямых учеников не найдено ни одного ставшего научным руководителем.")
    else:
        st.dataframe(continuity_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 9. Скачивание Excel-отчёта
    # =========================================================================
    st.markdown("### 📥 Скачать полный отчёт")

    with st.spinner("Формируем Excel-файл..."):
        excel_bytes = build_excel_report(
            metrics_df=metrics_df,
            generations_df=generations_df,
            yearly_df=yearly_df if not yearly_df.empty else pd.DataFrame(),
            city_df=city_df if not city_df.empty else pd.DataFrame(),
            institutional=institutional,
            opponents_df=opponents_df if not opponents_df.empty else pd.DataFrame(),
            education_df=education_df if not education_df.empty else pd.DataFrame(),
            knowledge_df=knowledge_df if not knowledge_df.empty else pd.DataFrame(),
            continuity_df=continuity_df if not continuity_df.empty else pd.DataFrame(),
        )

    safe_name = root.replace(" ", "_").replace("/", "-")[:60]
    st.download_button(
        label="📥 Скачать полный отчёт (Excel)",
        data=excel_bytes,
        file_name=f"school_analysis_{safe_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="school_analysis_download_excel",
    )
