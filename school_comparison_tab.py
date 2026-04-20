"""
Модуль Streamlit-вкладки сравнения научных школ.
Импортируйте и вызывайте render_school_comparison_tab() в основном приложении.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Set

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from utils.graph import lineage, rows_for
from utils.ui import download_data_dialog
from utils.urls import share_params_button
from school_comparison import (
    DistanceMetric,
    ComparisonScope,
    DISTANCE_METRIC_LABELS,
    SCOPE_LABELS,
    load_scores_from_folder,
    get_feature_columns,
    get_nodes_at_level,
    get_selectable_nodes,
    filter_columns_by_nodes,
    get_code_depth,
    compute_silhouette_analysis,
    create_silhouette_plot,
    create_comparison_summary,
    create_node_scores_table,
    interpret_silhouette_score,
    gather_school_dataset,
)


# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================

DEFAULT_SCORES_FOLDER = "basic_scores"
AUTHOR_COLUMN = "candidate_name"

# Ключ в session_state для хранения результатов анализа
_RESULTS_KEY = "school_comp_results"

# ==============================================================================
# ИНСТРУКЦИЯ ДЛЯ ВКЛАДКИ
# ==============================================================================

INSTRUCTION_SCHOOL_COMPARISON = """
## 🔬 Сравнение научных школ по тематическим профилям

Этот инструмент позволяет оценить, насколько различаются тематические направления 
диссертаций, защищённых под руководством разных учёных.

---

### 📋 Основные возможности

- **Сравнение тематических профилей** нескольких научных школ
- **Визуализация различий** с помощью графика силуэта
- **Таблица средних баллов** по узлам классификатора для каждой школы
- **Гибкий выбор параметров**: охват диссертаций, метрика расстояния, базис сравнения

---

### 🚀 Как использовать

1. **Выберите научные школы** — укажите минимум 2 руководителей для сравнения
2. **Настройте параметры анализа**:
   - *Охват*: только прямые диссертанты или все поколения
   - *Метрика*: евклидово или косинусное расстояние
   - *Базис*: прямоугольный (стандартный) или косоугольный (учитывающий иерархическую структуру элементов классификатора)
3. **Выберите тематический базис**: весь классификатор или конкретные разделы
4. **Запустите анализ** и изучите результаты

---

### 📊 Интерпретация коэффициента силуэта

| Значение | Интерпретация |
|----------|---------------|
| **0.71 – 1.00** | Отличное разделение — школы чётко различаются |
| **0.51 – 0.70** | Хорошее разделение |
| **0.26 – 0.50** | Умеренное разделение — есть пересечения |
| **0.00 – 0.25** | Слабое разделение — школы похожи |
| **< 0.00** | Плохое разделение — у школ общая тематика исследований |

---

### 💡 Рекомендации

- Для **общей картины** используйте весь базис и прямоугольную метрику
- Для **детального анализа** выберите конкретные разделы классификатора
- **Косоугольный базис** учитывает иерархию тем и может дать более точные результаты
- При сравнении **крупных школ** (много поколений) анализ может занять время
"""


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def get_all_supervisors(df: pd.DataFrame) -> List[str]:
    """Получает список всех научных руководителей из DataFrame."""
    supervisor_cols = [
        col for col in df.columns
        if "supervisor" in col.lower() and "name" in col.lower()
    ]

    all_supervisors: Set[str] = set()
    for col in supervisor_cols:
        all_supervisors.update(
            str(v).strip() for v in df[col].dropna().unique()
            if str(v).strip()
        )

    return sorted(all_supervisors)


def show_instruction_dialog() -> None:
    """Показывает диалог с инструкцией."""
    @st.dialog("Инструкция", width="large")
    def _show():
        st.markdown(INSTRUCTION_SCHOOL_COMPARISON)
    _show()


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ РЕНДЕРИНГА ВКЛАДКИ
# ==============================================================================

def render_school_comparison_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    scores_folder: str = DEFAULT_SCORES_FOLDER,
    specific_files: Optional[List[str]] = None,
    classifier_labels: Optional[Dict[str, str]] = None,
) -> None:
    """
    Отрисовывает вкладку сравнения научных школ.

    Args:
        df: Основной DataFrame с диссертациями
        idx: Индекс для поиска по именам
        scores_folder: Папка с CSV-профилями
        specific_files: Список конкретных CSV-файлов (None = все из папки)
        classifier_labels: Словарь {код: название} для подписей узлов
    """
    if classifier_labels is None:
        classifier_labels = {}

    if not st.session_state.get("school_comp_query_hydrated", False):
        schools_q = [s.strip() for s in st.query_params.get_all("school_comp_schools") if str(s).strip()]
        if schools_q:
            st.session_state["school_comp_selection_query"] = schools_q

        scope_q = str(st.query_params.get("school_comp_scope", "")).strip()
        if scope_q in SCOPE_LABELS:
            scope_options = list(SCOPE_LABELS.keys())
            st.session_state["school_comp_scope"] = scope_options.index(scope_q)

        metric_q = str(st.query_params.get("school_comp_metric", "")).strip()
        metric_options = list(DISTANCE_METRIC_LABELS.keys())
        if metric_q in metric_options:
            st.session_state["school_comp_metric"] = metric_options.index(metric_q)

        basis_q = str(st.query_params.get("school_comp_basis", "")).strip()
        if basis_q in {"full", "selected"}:
            st.session_state["school_comp_basis_choice"] = basis_q

        nodes_q = [n.strip() for n in st.query_params.get_all("school_comp_nodes") if str(n).strip()]
        if nodes_q:
            st.session_state["school_comp_nodes_prefill_query"] = nodes_q

        decay_q = str(st.query_params.get("school_comp_decay", "")).strip()
        if decay_q:
            try:
                decay_val = float(decay_q)
                if 0.1 <= decay_val <= 0.9:
                    st.session_state["school_comp_decay"] = decay_val
            except ValueError:
                pass
        st.session_state["school_comp_query_hydrated"] = True

    # --- Кнопка инструкции ---
    if st.button("📖 Инструкция", key="instruction_school_comparison"):
        show_instruction_dialog()

    st.subheader("🔬 Сравнение научных школ по тематическим профилям")
    st.markdown("""
    Сравните тематические профили диссертаций разных научных школ.
    Основная метрика — **коэффициент силуэта**, показывающий степень различия
    тематических направлений.
    """)

    # =========================================================================
    # ЗАГРУЗКА ДАННЫХ ПРОФИЛЕЙ
    # =========================================================================
    try:
        scores_df = load_scores_from_folder(
            folder_path=scores_folder,
            specific_files=specific_files
        )
        all_feature_columns = get_feature_columns(scores_df)
        st.success(
            f"✅ Загружено {len(scores_df)} профилей, "
            f"{len(all_feature_columns)} признаков"
        )
    except FileNotFoundError as e:
        st.error(f"❌ Папка или файлы не найдены: {e}")
        st.info(
            f"Убедитесь, что папка '{scores_folder}' существует и содержит CSV-файлы "
            "с тематическими профилями."
        )
        return
    except Exception as e:
        st.error(f"❌ Ошибка загрузки данных: {e}")
        return

    st.markdown("---")

    # =========================================================================
    # ВЫБОР НАУЧНЫХ ШКОЛ
    # =========================================================================
    st.markdown("### 👥 Выбор научных школ для сравнения")

    all_supervisors_sorted = get_all_supervisors(df)
    if not all_supervisors_sorted:
        st.error("❌ В данных не найдено научных руководителей")
        return

    if "school_comp_selection_query" in st.session_state:
        requested = st.session_state.get("school_comp_selection_query", [])
        valid_selected = [s for s in requested if s in all_supervisors_sorted]
        st.session_state["school_comp_selection"] = valid_selected
        if len(valid_selected) >= 2:
            st.session_state["school_comp_run_state"] = True
        st.session_state.pop("school_comp_selection_query", None)

    selected_schools = st.multiselect(
        "Выберите руководителей научных школ (минимум 2)",
        options=all_supervisors_sorted,
        default=[],
        key="school_comp_selection",
        help="Выберите 2 или более научных руководителей для сравнения их школ"
    )

    if len(selected_schools) < 2:
        st.warning("⚠️ Выберите минимум 2 научных руководителя для сравнения")
        # Если школы сменились, сбрасываем кэшированные результаты
        st.session_state.pop(_RESULTS_KEY, None)
        return

    st.markdown("---")

    # =========================================================================
    # ПАРАМЕТРЫ АНАЛИЗА
    # =========================================================================
    col_params1, col_params2 = st.columns(2)

    with col_params1:
        st.markdown("### 📐 Параметры анализа")

        scope_options = list(SCOPE_LABELS.keys())
        scope_labels_list = [SCOPE_LABELS[s] for s in scope_options]
        scope_idx = st.radio(
            "Охват диссертаций",
            options=range(len(scope_options)),
            format_func=lambda i: scope_labels_list[i],
            key="school_comp_scope",
            help=(
                "**Прямые диссертанты** — только защитившиеся под непосредственным "
                "руководством выбранного учёного.\n\n"
                "**Все поколения** — включая диссертантов диссертантов и далее."
            )
        )
        selected_scope: ComparisonScope = scope_options[scope_idx]

        metric_options = list(DISTANCE_METRIC_LABELS.keys())
        metric_labels_list = [DISTANCE_METRIC_LABELS[m] for m in metric_options]
        metric_idx = st.selectbox(
            "Метрика расстояния",
            options=range(len(metric_options)),
            format_func=lambda i: metric_labels_list[i],
            key="school_comp_metric",
            help=(
                "**Прямоугольный базис** — стандартное вычисление расстояний.\n\n"
                "**Косоугольный базис** — учитывает иерархическую структуру "
                "тематического классификатора."
            )
        )
        selected_metric: DistanceMetric = metric_options[metric_idx]

    with col_params2:
        st.markdown("### 🎯 Выбор тематического базиса")

        basis_choice = st.radio(
            "Базис для сравнения",
            options=["full", "selected"],
            format_func=lambda x: "Весь базис (все темы)" if x == "full" else "Конкретные разделы",
            key="school_comp_basis_choice",
            help=(
                "**Весь базис** — используются все тематические признаки.\n\n"
                "**Конкретные разделы** — выберите узлы классификатора."
            )
        )

        selected_nodes: Optional[List[str]] = None

        if basis_choice == "selected":
            selectable = get_selectable_nodes(all_feature_columns, max_level=3)
            if not selectable:
                st.warning("Нет доступных узлов для выбора")
            else:
                level1_nodes = [n for n in selectable if get_code_depth(n) == 1]
                level2_nodes = [n for n in selectable if get_code_depth(n) == 2]
                level3_nodes = [n for n in selectable if get_code_depth(n) == 3]
                all_selectable_nodes = set(selectable)
                if "school_comp_nodes_prefill_query" in st.session_state:
                    raw_nodes = st.session_state.get("school_comp_nodes_prefill_query", [])
                    st.session_state["school_comp_nodes_prefill"] = [
                        n for n in raw_nodes if n in all_selectable_nodes
                    ]
                    st.session_state.pop("school_comp_nodes_prefill_query", None)

                st.caption("Выберите разделы классификатора:")
                selected_nodes = []

                if level1_nodes:
                    st.markdown("Уровень 1:")
                    cols_l1 = st.columns(min(4, len(level1_nodes)))
                    for i, node in enumerate(level1_nodes):
                        with cols_l1[i % len(cols_l1)]:
                            node_prefill = st.session_state.get("school_comp_nodes_prefill", [])
                            node_key = f"node_l1_{node}"
                            if node in node_prefill and node_key not in st.session_state:
                                st.session_state[node_key] = True
                            label = classifier_labels.get(node, "")
                            display = f"{node}" + (f" — {label}" if label else "")
                            if st.checkbox(display, key=node_key):
                                selected_nodes.append(node)

                if level2_nodes:
                    with st.expander("Уровень 2", expanded=False):
                        cols_l2 = st.columns(3)
                        for i, node in enumerate(level2_nodes):
                            with cols_l2[i % 3]:
                                node_prefill = st.session_state.get("school_comp_nodes_prefill", [])
                                node_key = f"node_l2_{node}"
                                if node in node_prefill and node_key not in st.session_state:
                                    st.session_state[node_key] = True
                                label = classifier_labels.get(node, "")
                                display = f"{node}" + (f" ({label})" if label else "")
                                if st.checkbox(display, key=node_key):
                                    selected_nodes.append(node)

                if level3_nodes:
                    with st.expander("Уровень 3", expanded=False):
                        cols_l3 = st.columns(3)
                        for i, node in enumerate(level3_nodes):
                            with cols_l3[i % 3]:
                                node_prefill = st.session_state.get("school_comp_nodes_prefill", [])
                                node_key = f"node_l3_{node}"
                                if node in node_prefill and node_key not in st.session_state:
                                    st.session_state[node_key] = True
                                label = classifier_labels.get(node, "")
                                display = f"{node}" + (f" ({label})" if label else "")
                                if st.checkbox(display, key=node_key):
                                    selected_nodes.append(node)

                if selected_nodes:
                    filtered_cols = filter_columns_by_nodes(all_feature_columns, selected_nodes)
                    st.info(
                        f"✓ Выбрано {len(selected_nodes)} узлов → "
                        f"{len(filtered_cols)} признаков"
                    )
                else:
                    st.warning("⚠️ Выберите хотя бы один раздел")

    # Параметры косоугольного базиса
    decay_factor = 0.5
    if "oblique" in selected_metric:
        with st.expander("🔧 Параметры косоугольного базиса", expanded=False):
            decay_factor = st.slider(
                "Коэффициент затухания",
                min_value=0.1,
                max_value=0.9,
                value=0.5,
                step=0.1,
                key="school_comp_decay",
                help="Сила влияния родительских узлов на дочерние (0.5 — сбалансированно)"
            )

    st.markdown("---")

    ready_to_run = not (basis_choice == "selected" and not selected_nodes)

    # =========================================================================
    # ЗАПУСК АНАЛИЗА
    # =========================================================================
    run_clicked = st.button(
        "🚀 Запустить анализ",
        key="school_comp_run",
        type="primary",
        disabled=not ready_to_run
    )
    if run_clicked:
        st.session_state["school_comp_run_state"] = True

    run_requested = run_clicked or (
        st.session_state.get("school_comp_run_state", False)
        and st.session_state.get(_RESULTS_KEY) is None
    )

    if run_requested:
        datasets: Dict[str, pd.DataFrame] = {}
        missing_info_all: Dict[str, pd.DataFrame] = {}
        stats_info = []

        with st.spinner("📥 Сбор данных научных школ..."):
            progress_bar = st.progress(0)
            for i, school_name in enumerate(selected_schools):
                try:
                    dataset, missing_info, total_count = gather_school_dataset(
                        df=df,
                        index=idx,
                        root=school_name,
                        scores=scores_df,
                        scope=selected_scope,
                        lineage_func=lineage,
                        rows_for_func=rows_for,
                        author_column=AUTHOR_COLUMN,
                    )
                    datasets[school_name] = dataset
                    if not missing_info.empty:
                        missing_info_all[school_name] = missing_info
                    stats_info.append({
                        "Школа": school_name,
                        "Найдено диссертаций": total_count,
                        "С профилями": len(dataset),
                        "Без профилей": len(missing_info) if not missing_info.empty else 0,
                    })
                except Exception as e:
                    st.warning(f"⚠️ Ошибка для школы '{school_name}': {e}")
                progress_bar.progress((i + 1) / len(selected_schools))
            progress_bar.empty()

        valid_datasets = {k: v for k, v in datasets.items() if not v.empty}

        if len(valid_datasets) < 2:
            st.error(
                "❌ Недостаточно данных для анализа. "
                "Нужно минимум 2 школы с тематическими профилями."
            )
            return

        with st.spinner("🔬 Вычисление анализа силуэта..."):
            try:
                nodes_for_analysis = selected_nodes if basis_choice == "selected" else None
                (
                    overall_score,
                    sample_scores,
                    labels,
                    school_order,
                    used_columns,
                ) = compute_silhouette_analysis(
                    datasets=valid_datasets,
                    feature_columns=all_feature_columns,
                    metric=selected_metric,
                    selected_nodes=nodes_for_analysis,
                    decay_factor=decay_factor,
                )
            except ValueError as e:
                st.error(f"❌ Ошибка анализа: {e}")
                return
            except Exception as e:
                st.error(f"❌ Неожиданная ошибка: {e}")
                return

        # Сохраняем все результаты в session_state
        nodes_for_table = selected_nodes if basis_choice == "selected" else None
        node_scores_df_full = create_node_scores_table(
            datasets=valid_datasets,
            feature_columns=used_columns,
            school_order=school_order,
            classifier_labels=classifier_labels,
            selected_nodes=nodes_for_table,
            threshold=0.0,
        )
        summary_df = create_comparison_summary(
            datasets=valid_datasets,
            feature_columns=used_columns,
            school_order=school_order,
        )
        buf_silhouette = io.BytesIO()
        fig_save = create_silhouette_plot(
            sample_scores=sample_scores,
            labels=labels,
            school_order=school_order,
            overall_score=overall_score,
            metric_label=DISTANCE_METRIC_LABELS[selected_metric],
        )
        fig_save.savefig(buf_silhouette, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig_save)

        st.session_state[_RESULTS_KEY] = {
            "stats_info": stats_info,
            "valid_datasets": valid_datasets,
            "overall_score": overall_score,
            "sample_scores": sample_scores,
            "labels": labels,
            "school_order": school_order,
            "used_columns": used_columns,
            "node_scores_df_full": node_scores_df_full,
            "summary_df": summary_df,
            "silhouette_png": buf_silhouette.getvalue(),
            "missing_info_all": missing_info_all,
            "selected_metric": selected_metric,
            "basis_choice": basis_choice,
            "selected_nodes": selected_nodes,
            "classifier_labels": classifier_labels,
        }

    # =========================================================================
    # ОТОБРАЖЕНИЕ РЕЗУЛЬТАТОВ (читаем из session_state, не из блока if-button)
    # =========================================================================
    results = st.session_state.get(_RESULTS_KEY)
    if results is None:
        return

    # Сбрасываем кэш, если школы изменились
    if set(results["school_order"]) != set(selected_schools):
        st.session_state.pop(_RESULTS_KEY, None)
        return

    stats_info = results["stats_info"]
    valid_datasets = results["valid_datasets"]
    overall_score = results["overall_score"]
    sample_scores = results["sample_scores"]
    labels = results["labels"]
    school_order = results["school_order"]
    used_columns = results["used_columns"]
    node_scores_df_full = results["node_scores_df_full"]
    summary_df = results["summary_df"]
    silhouette_png = results["silhouette_png"]
    missing_info_all = results["missing_info_all"]
    selected_metric_res = results["selected_metric"]
    basis_choice_res = results["basis_choice"]
    selected_nodes_res = results["selected_nodes"]
    classifier_labels_res = results["classifier_labels"]

    st.markdown("---")
    st.markdown("## 📈 Результаты анализа")

    if stats_info:
        st.markdown("#### 📊 Статистика сбора данных")
        st.dataframe(pd.DataFrame(stats_info), use_container_width=True, hide_index=True)

    # =====================================================================
    # ТАБЛИЦА ТЕМАТИЧЕСКИХ ПРОФИЛЕЙ
    # =====================================================================
    st.markdown("### 📋 Тематические профили по узлам классификатора")
    st.markdown(
        "Средний балл по каждому узлу классификатора — среднее значение "
        "по потомкам узла, усреднённое по диссертациям школы."
    )

    threshold_value = st.slider(
        "Порог отсечения строк",
        min_value=0,
        max_value=10,
        value=2,
        step=1,
        key="school_comp_node_threshold",
        help=(
            "Узел классификатора скрывается, если для ВСЕХ школ значение ≤ порога. "
            "Строка показывается, если хотя бы одна школа превышает порог."
        ),
    )

    nodes_for_table_res = selected_nodes_res if basis_choice_res == "selected" else None
    node_scores_df = create_node_scores_table(
        datasets=valid_datasets,
        feature_columns=used_columns,
        school_order=school_order,
        classifier_labels=classifier_labels_res,
        selected_nodes=nodes_for_table_res,
        threshold=float(threshold_value),
    )

    if not node_scores_df_full.empty:
        display_cols = ["Раздел"] + school_order
        display_df = node_scores_df[display_cols] if not node_scores_df.empty else pd.DataFrame(columns=display_cols)
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=600,
        )
        # Кнопки скачивания рендерятся прямо через download_data_dialog (inline, без диалога)
        download_data_dialog(
            df=node_scores_df_full,
            file_base="оценки_узлов_школ",
            key_prefix="school_comp_node_scores",
        )
    else:
        st.info("Узлы с ненулевыми значениями не найдены.")

    # =====================================================================
    # МЕТРИКА СИЛУЭТА
    # =====================================================================
    st.markdown("---")
    col_score, col_interp = st.columns([1, 2])
    with col_score:
        st.metric(
            label="Коэффициент силуэта",
            value=f"{overall_score:.3f}",
            help="Диапазон от -1 до 1. Чем выше, тем лучше разделение школ."
        )
    with col_interp:
        st.info(interpret_silhouette_score(overall_score))

    basis_info = (
        "весь базис"
        if basis_choice_res == "full"
        else f"узлы: {', '.join(selected_nodes_res or [])}"
    )
    st.caption(
        f"📌 Базис: {basis_info} | "
        f"Признаков: {len(used_columns)} | "
        f"Метрика: {DISTANCE_METRIC_LABELS[selected_metric_res]}"
    )

    # =====================================================================
    # ГРАФИК СИЛУЭТА
    # =====================================================================
    st.markdown("### 📊 График силуэта")
    fig = create_silhouette_plot(
        sample_scores=sample_scores,
        labels=labels,
        school_order=school_order,
        overall_score=overall_score,
        metric_label=DISTANCE_METRIC_LABELS[selected_metric_res],
    )
    st.pyplot(fig)
    plt.close(fig)

    st.download_button(
        label="📥 Скачать график силуэта (PNG)",
        data=silhouette_png,
        file_name="график_силуэта.png",
        mime="image/png",
        key="school_comp_download_png"
    )

    # =====================================================================
    # СВОДНАЯ СТАТИСТИКА
    # =====================================================================
    st.markdown("---")
    st.markdown("### 📋 Сводная статистика по школам")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    csv_summary = summary_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="📥 Скачать сводку (CSV)",
        data=csv_summary.encode("utf-8-sig"),
        file_name="сводка_сравнения_школ.csv",
        mime="text/csv",
        key="school_comp_download_csv"
    )

    # =====================================================================
    # ДЕТАЛИ
    # =====================================================================
    with st.expander(
        f"📝 Использовано признаков: {len(used_columns)}",
        expanded=False
    ):
        by_level: Dict[int, List[str]] = {}
        for col in used_columns:
            lv = get_code_depth(col)
            by_level.setdefault(lv, []).append(col)
        for lv in sorted(by_level.keys()):
            cols = by_level[lv]
            st.markdown(f"**Уровень {lv}** ({len(cols)} признаков)")
            display_cols_list = []
            for c in sorted(cols)[:30]:
                lbl = classifier_labels_res.get(c, "")
                display_cols_list.append(f"{c}" + (f" ({lbl})" if lbl else ""))
            st.code(", ".join(display_cols_list) + ("…" if len(cols) > 30 else ""))

    if missing_info_all:
        with st.expander("⚠️ Диссертации без профилей", expanded=False):
            for school_name, missing_df in missing_info_all.items():
                st.markdown(f"**{school_name}**: {len(missing_df)} диссертаций")
                show_df = missing_df.head(20)
                st.dataframe(show_df, use_container_width=True, hide_index=True)
                if len(missing_df) > 20:
                    st.caption(f"… и ещё {len(missing_df) - 20}")

    share_params_button(
        {
            "school_comp_schools": selected_schools,
            "school_comp_scope": selected_scope,
            "school_comp_metric": selected_metric,
            "school_comp_basis": basis_choice,
            "school_comp_nodes": selected_nodes or [],
            "school_comp_decay": decay_factor,
        },
        key="school_comp_share",
    )
