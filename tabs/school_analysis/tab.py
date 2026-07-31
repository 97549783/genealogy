"""
Модуль Streamlit-вкладки «Анализ научной школы».
Импортируйте и вызывайте render_school_analysis_tab() в основном приложении.
"""

from __future__ import annotations

from typing import Dict, List, Set

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from core.people import get_unique_supervisors
from core.classifier import get_classifier_by_profile_source
from core.domain.profile_sources import get_profile_summary_groups
from core.perf import perf_timer
from core.ui.science_filtering import get_science_filtered_lineage_context
from core.ui.filters import (
    hydrate_profile_source_from_query_params,
    hydrate_science_fields_from_query_params,
    render_profile_source_radio,
    render_science_field_filter,
    science_field_filter_caption,
    science_field_state_suffix,
    science_fields_to_query_params,
)

from core.lineage.graph import lineage, rows_for
from core.lineage.membership import get_school_branch_codes, get_school_generation_codes
from core.semantic.models import build_section_selection
from core.ui.links import share_params_button
from core.ui.table_display import build_dissertation_result_signature, render_dissertations_widget
from tabs.dissertation_characteristics.labels import SEARCHABLE_SECTION_KEYS, SECTION_LABELS_RU
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
    SUPERVISOR_COLUMNS,
)
from .exports import build_excel_report


# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================


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
    return get_unique_supervisors(df, supervisor_columns=supervisor_cols)



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


def _clear_school_cache(root: str, scope: str, sf_suffix: str, db_signature) -> None:
    """Очищает кэш школы из session_state."""
    db_sig = str(db_signature)
    for s in ("direct", "all"):
        key = f"school_subset_{db_sig}_{sf_suffix}_{root}_{s}"
        if key in st.session_state:
            del st.session_state[key]


def _render_school_semantics(
    *, root: str, scope: str, subset: pd.DataFrame, working_df: pd.DataFrame,
    working_idx: dict, lineage_context_key, db_signature, science_field_ids: list[str],
) -> dict[str, pd.DataFrame]:
    """Отрисовывает лениво запускаемый семантический анализ выбранной школы."""
    st.markdown("### 8. Семантическая структура научной школы")
    st.caption("Анализ использует отдельные нейросетевые центры целей, методов, новизны и других характеристик.")
    sections_mode = st.radio(
        "Характеристики для анализа", ["all", "selected"],
        format_func=lambda value: "Все доступные характеристики" if value == "all" else "Выбранные разделы характеристик",
        key="school_analysis_semantic_sections_mode",
    )
    section_keys = tuple(SEARCHABLE_SECTION_KEYS)
    if sections_mode == "selected":
        section_keys = tuple(st.multiselect(
            "Выберите разделы характеристик", SEARCHABLE_SECTION_KEYS,
            format_func=lambda key: SECTION_LABELS_RU[key],
            default=["research_goal", "research_methods", "scientific_novelty"],
            key="school_analysis_semantic_sections",
        ))
    minimum_coverage = st.slider(
        "Минимальное покрытие характеристик, %", 0, 100, 60, 5,
        key="school_analysis_semantic_coverage",
    ) / 100.0
    run = st.button(
        "Рассчитать семантическую структуру", type="primary", disabled=not bool(section_keys),
        key="school_analysis_semantic_run",
    )
    base_signature = {
        "database_signature": db_signature, "root": root, "scope": scope,
        "science_fields": tuple(sorted(science_field_ids)), "sections_mode": sections_mode,
        "section_keys": section_keys, "minimum_coverage": minimum_coverage,
    }
    state_key = "school_analysis_semantic_result"
    selection = build_section_selection(sections_mode, section_keys, min_coverage=minimum_coverage) if section_keys else None
    if run and selection is not None:
        from core.db.dissertation_sections import (
            get_dissertation_sections_db_signature, load_dissertation_section_index_for_selection,
            load_typed_vector_metadata,
        )
        from tabs.dissertation_characteristics.search import load_dissertation_embedding_matrix
        from .semantic import (
            build_school_semantic_dataset, compute_branch_semantics,
            compute_generation_semantics, compute_school_heterogeneity,
            compute_school_semantic_center,
        )

        metadata = load_typed_vector_metadata()
        if metadata is None:
            st.error("Матрица векторов характеристик недоступна или имеет неверный формат.")
            return {}
        try:
            member_codes = {str(code).strip() for code in subset["Code"] if str(code).strip()}
            section_index = load_dissertation_section_index_for_selection(
                allowed_codes=member_codes, section_keys=selection.section_keys, include_text=False,
            )
            matrix = load_dissertation_embedding_matrix(metadata.matrix_signature)
            dissertation_metadata = working_df.copy()
            generation_codes = {}
            branch_codes = {}
            if scope == "all":
                generation_codes = get_school_generation_codes(
                    working_df, working_idx, root, db_signature, context_key=lineage_context_key,
                )
                branch_codes = get_school_branch_codes(
                    working_df, working_idx, root, db_signature, context_key=lineage_context_key,
                )
                generation_by_code = {code: generation for generation, codes in generation_codes.items() for code in codes}
                dissertation_metadata["Поколение"] = dissertation_metadata["Code"].astype(str).map(generation_by_code)
            dataset = build_school_semantic_dataset(
                root=root, member_codes=member_codes, section_index=section_index, matrix=matrix,
                selection=selection, normalized=metadata.normalized,
                dissertation_metadata=dissertation_metadata,
            )
            center = compute_school_semantic_center(dataset, selection)
            heterogeneity = compute_school_heterogeneity(dataset, center, selection)
            generations = compute_generation_semantics(dataset, generation_codes, selection) if scope == "all" else None
            branches = compute_branch_semantics(dataset, branch_codes, selection) if scope == "all" else None
        except Exception:
            st.error("Не удалось рассчитать семантическую структуру научной школы.")
            return {}
        complete_signature = {
            **base_signature, "section_database_signature": get_dissertation_sections_db_signature(),
            "matrix_signature": metadata.matrix_signature, "model_name": metadata.model_name,
            "normalized": metadata.normalized,
        }
        st.session_state[state_key] = {
            "signature": complete_signature, "metadata": metadata, "dataset": dataset,
            "heterogeneity": heterogeneity, "generations": generations, "branches": branches,
        }
    stored = st.session_state.get(state_key)
    if stored is None:
        return {}
    if any(stored["signature"].get(key) != value for key, value in base_signature.items()):
        st.session_state.pop(state_key, None)
        return {}
    from core.db.dissertation_sections import get_dissertation_sections_db_signature, load_typed_vector_metadata
    current_metadata = load_typed_vector_metadata()
    if (
        current_metadata is None
        or stored["signature"].get("section_database_signature") != get_dissertation_sections_db_signature()
        or stored["signature"].get("matrix_signature") != current_metadata.matrix_signature
        or stored["signature"].get("model_name") != current_metadata.model_name
        or stored["signature"].get("normalized") != current_metadata.normalized
    ):
        st.session_state.pop(state_key, None)
        st.warning("Семантические данные изменились. Выполните расчёт повторно.")
        return {}
    dataset = stored["dataset"]
    heterogeneity = stored["heterogeneity"]
    st.markdown(f"**Модель:** `{stored['metadata'].model_name}` · **Размерность:** {stored['metadata'].dimensions}")
    st.markdown("#### Тематический центр и неоднородность")
    st.dataframe(heterogeneity.summary, use_container_width=True, hide_index=True)
    for diagnostic in heterogeneity.diagnostics:
        st.warning(diagnostic)
    if heterogeneity.medoid_code:
        st.markdown("#### Наиболее репрезентативная диссертация")
        representative = subset[subset["Code"].astype(str) == heterogeneity.medoid_code]
        if not representative.empty:
            render_dissertations_widget(
                subset=representative, key="school_analysis_semantic_medoid",
                title="Репрезентативная диссертация и автореферат", expanded=True,
                file_name_prefix="репрезентативная_диссертация",
                result_signature=build_dissertation_result_signature(
                    representative, context_parts=(stored["signature"], "medoid"),
                ),
            )
    st.markdown("#### Тематическое ядро и периферийные направления")
    st.caption("Удалённые работы могут представлять новые, междисциплинарные или слабо представленные направления и не считаются ошибочными.")
    display_distances = heterogeneity.dissertation_distances.drop(columns=["Code"], errors="ignore")
    st.dataframe(display_distances, use_container_width=True, hide_index=True)
    generations = stored["generations"]
    branches = stored["branches"]
    if scope == "all" and generations is not None:
        st.markdown("#### Семантическая динамика поколений")
        st.dataframe(generations.summary, use_container_width=True, hide_index=True)
        for diagnostic in generations.diagnostics:
            st.caption(diagnostic)
        if not generations.summary.empty:
            chart = generations.summary.set_index("Поколение")[[
                "Расстояние от первого поколения", "Тематическая неоднородность",
            ]]
            st.line_chart(chart, x_label="Поколение", y_label="Значение")
    if scope == "all" and branches is not None:
        st.markdown("#### Естественные генеалогические ветви")
        st.dataframe(branches.summary, use_container_width=True, hide_index=True)
        st.markdown("##### Сходство ветвей")
        st.dataframe(branches.similarity_matrix, use_container_width=True, hide_index=True)
        st.caption("Для силуэта ветвей диссертации с несколькими ветвями исключаются, поскольку каждой работе требуется единственная метка.")
        if branches.silhouette_overall is not None:
            st.metric("Общий коэффициент силуэта ветвей", f"{branches.silhouette_overall:.3f}")
            st.dataframe(branches.silhouette_by_branch, use_container_width=True, hide_index=True)
            from tabs.school_comparison.comparison import create_silhouette_plot
            branch_order = branches.silhouette_by_branch["Ветвь"].tolist()
            positions = {branch: index for index, branch in enumerate(branch_order)}
            fig = create_silhouette_plot(
                branches.dissertation_silhouettes["Коэффициент силуэта"].to_numpy(),
                branches.dissertation_silhouettes["Ветвь"].map(positions).to_numpy(),
                branch_order, branches.silhouette_overall, "Составное косинусное расстояние",
                title="Тематическая различимость генеалогических ветвей",
            )
            st.pyplot(fig); plt.close(fig)
        for diagnostic in branches.diagnostics:
            st.warning(diagnostic)
        if not branches.ambiguous_dissertations.empty:
            with st.expander("Неоднозначно назначенные диссертации"):
                st.dataframe(branches.ambiguous_dissertations, use_container_width=True, hide_index=True)
    if not dataset.excluded.empty:
        with st.expander("Исключённые из семантического анализа диссертации"):
            st.dataframe(dataset.excluded, use_container_width=True, hide_index=True)
    return {
        "semantic_summary": heterogeneity.summary,
        "semantic_dissertations": heterogeneity.dissertation_distances,
        "semantic_generations": generations.summary if generations is not None else pd.DataFrame(),
        "semantic_branches": branches.summary if branches is not None else pd.DataFrame(),
        "semantic_branch_similarity": branches.similarity_matrix if branches is not None else pd.DataFrame(),
        "semantic_branch_silhouette": branches.silhouette_by_branch if branches is not None else pd.DataFrame(),
        "semantic_excluded": pd.concat([
            dataset.excluded,
            branches.ambiguous_dissertations if branches is not None else pd.DataFrame(),
        ], ignore_index=True),
    }


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ==============================================================================


def render_school_analysis_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    *,
    db_signature,
) -> None:
    """
    Отрисовывает вкладку «Анализ научной школы».

    Аргументы:
        df              — основной DataFrame с диссертациями
        idx             — индекс имён
    """
    st.subheader("Анализ научной школы")

    st.markdown("### Фильтр отраслей наук")
    default_science_fields = st.session_state.pop(
        "school_analysis_science_fields_query",
        hydrate_science_fields_from_query_params(),
    )
    science_field_ids = render_science_field_filter(
        key_prefix="school_analysis",
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
    sf_suffix = science_field_state_suffix(science_field_ids)

    # =========================================================================
    # 0. Входные параметры
    # =========================================================================
    st.markdown("### \U0001f464 Выбор научной школы")

    all_supervisors = _get_all_supervisors(working_df)
    if not all_supervisors:
        st.error("В данных не найдены научные руководители.")
        return

    if not st.session_state.get("school_analysis_query_hydrated", False):
        science_fields_q = hydrate_science_fields_from_query_params()
        if science_fields_q:
            st.session_state["school_analysis_science_fields_query"] = science_fields_q

        root_q = str(st.query_params.get("analysis_root", "")).strip()
        if root_q and root_q in all_supervisors:
            st.session_state["school_analysis_root"] = root_q
        source_q = str(st.query_params.get("analysis_profile_source", "")).strip()
        if source_q:
            st.session_state["school_analysis_profile_source_query"] = source_q
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
            _clear_school_cache(root, scope, sf_suffix, db_signature)
            st.rerun()

    if run_clicked:
        st.session_state["school_analysis_run_state"] = True

    if not st.session_state.get("school_analysis_run_state", False):
        db_sig = str(db_signature)
        if f"school_subset_{db_sig}_{sf_suffix}_{root}_direct" not in st.session_state:
            return

    # =========================================================================
    # Сбор данных с кэшированием в session_state
    # =========================================================================
    db_sig = str(db_signature)
    key_direct = f"school_subset_{db_sig}_{sf_suffix}_{root}_direct"
    key_all = f"school_subset_{db_sig}_{sf_suffix}_{root}_all"

    with st.spinner("Сбор диссертаций школы..."):
        if key_direct not in st.session_state:
            with perf_timer("school_analysis.collect_direct_subset"):
                try:
                    st.session_state[key_direct] = collect_school_subset(
                        working_df, working_idx, root, "direct", lineage, rows_for, lineage_context_key=lineage_context_key
                    )
                except TypeError:
                    st.session_state[key_direct] = collect_school_subset(
                        working_df, working_idx, root, "direct", lineage, rows_for
                    )
        if key_all not in st.session_state:
            with perf_timer("school_analysis.collect_all_subset"):
                try:
                    st.session_state[key_all] = collect_school_subset(
                        working_df, working_idx, root, "all", lineage, rows_for, lineage_context_key=lineage_context_key
                    )
                except TypeError:
                    st.session_state[key_all] = collect_school_subset(
                        working_df, working_idx, root, "all", lineage, rows_for
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

    with perf_timer("school_analysis.compute_overview"):
        overview = compute_overview(
            subset=subset,
            root=root,
            index=working_idx,
            lineage_func=lineage,
            df_full=working_df,
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
        with perf_timer("school_analysis.compute_metrics"):
            metrics_df, generations_df = compute_metrics(
                df_full=working_df,
                index=working_idx,
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

    with perf_timer("school_analysis.compute_yearly_stats"):
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

    with perf_timer("school_analysis.compute_city_stats"):
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

    with perf_timer("school_analysis.compute_institutional_stats"):
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

    with perf_timer("school_analysis.compute_top_opponents"):
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
        "Средние баллы по всем диссертациям школы по выбранной таблице тематических профилей."
    )

    default_source_id = st.session_state.pop(
        "school_analysis_profile_source_query",
        None,
    ) or hydrate_profile_source_from_query_params(param_name="analysis_profile_source")
    source = render_profile_source_radio(
        key="school_analysis_profile_source",
        default_id=default_source_id,
    )
    classifier = get_classifier_by_profile_source(source.id)
    groups = get_profile_summary_groups(source.id)

    st.caption(f"Активный профиль: {source.label}")

    with st.spinner("Вычисление тематического профиля..."):
        with perf_timer("school_analysis.compute_thematic_profile"):
            thematic_groups = compute_thematic_profile(
                subset=subset,
                classifier=classifier,
                profile_source_id=source.id,
                groups=groups,
            )

    for group_label, group_df in thematic_groups.items():
        with st.expander(group_label, expanded=False):
            if group_df.empty:
                st.info(f"Нет данных для группы {group_label}.")
            else:
                st.dataframe(group_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    semantic_exports = _render_school_semantics(
        root=root, scope=scope, subset=subset, working_df=working_df,
        working_idx=working_idx, lineage_context_key=lineage_context_key,
        db_signature=db_signature, science_field_ids=science_field_ids,
    )

    st.markdown("---")

    # =========================================================================
    # 9. Преемственность
    # =========================================================================
    st.markdown("### 9. Ученики, ставшие научными руководителями")
    st.caption("Ученики из первого поколения, сами ставшие научными руководителями.")

    with st.spinner("Поиск учеников-руководителей..."):
        with perf_timer("school_analysis.compute_continuity"):
            continuity_df = compute_continuity(
                df_full=working_df,
                index=working_idx,
                subset_direct=subset_direct,
                rows_for_func=rows_for,
            )

    if continuity_df.empty:
        st.info("Среди прямых учеников не найдено ни одного ставшего научным руководителем.")
    else:
        st.dataframe(continuity_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =========================================================================
    # 10. Скачивание Excel-отчёта
    # =========================================================================
    st.markdown("### \U0001f4e5 Скачать полный отчёт")

    semantic_signature = st.session_state.get("school_analysis_semantic_result", {}).get("signature")
    excel_signature = f"{db_sig}::{root}::{scope}::{sf_suffix}::{source.id}::{semantic_signature}"
    if st.button("Сформировать Excel-отчёт", key="school_analysis_build_excel"):
        with st.spinner("Формируем Excel-файл..."):
            with perf_timer("school_analysis.build_excel"):
                excel_bytes = build_excel_report(
                    metrics_df=metrics_df,
                    generations_df=generations_df,
                    yearly_df=yearly_df if not yearly_df.empty else pd.DataFrame(),
                    city_df=city_df if not city_df.empty else pd.DataFrame(),
                    institutional=institutional,
                    opponents_df=compute_top_opponents(subset, top_n=None),
                    continuity_df=continuity_df if not continuity_df.empty else pd.DataFrame(),
                    thematic_groups=thematic_groups,
                    **semantic_exports,
                )
        st.session_state["school_analysis_excel_bytes"] = excel_bytes
        st.session_state["school_analysis_excel_signature"] = excel_signature

    if (
        "school_analysis_excel_bytes" in st.session_state
        and st.session_state.get("school_analysis_excel_signature") == excel_signature
    ):
        safe_name = root.replace(" ", "_").replace("/", "-")[:60]
        st.download_button(
            label="\U0001f4e5 Скачать полный отчёт (Excel)",
            data=st.session_state["school_analysis_excel_bytes"],
            file_name=f"анализ_научной_школы_{safe_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="school_analysis_download_excel",
        )

    share_params_button(
        {
            "tab": "school_analysis",
            "analysis_root": root,
            "analysis_scope": scope,
            "analysis_profile_source": source.id,
            **science_fields_to_query_params(science_field_ids),
        },
        key="school_analysis_share",
    )
