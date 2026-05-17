"""Режим сравнения выбранных научных школ по статьям."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

from core.lineage.graph import lineage
from core.ui.links import share_params_button
from .author_matching import (
    build_initials_to_fullnames as _shared_build_initials_to_fullnames,
    canon_article_author_name as _shared_canon_article_author_name,
    canon_initials as _shared_canon_initials,
    compute_selectable_people as _shared_compute_selectable_people,
    display_initials as _shared_display_initials,
    fio_to_short as _shared_fio_to_short,
    resolve_article_author_to_lineage_root as _shared_resolve_article_author_to_lineage_root,
)
from .data import build_articles_dataset_for_schools, filter_articles_with_thematic_scores
from .query_params import parse_bool_param, parse_float_param, query_params_signature, should_hydrate_query
from .comparison import (
    DistanceMetric,
    DISTANCE_METRIC_LABELS,
    ARTICLES_HELP_TEXT,
    CLASSIFIER_LIST_TEXT,
    load_articles_data,
    load_articles_classifier,
    compute_article_analysis,
    create_articles_silhouette_plot,
    create_comparison_summary,
    get_code_depth,
)

try:
    import openpyxl  # type: ignore
except Exception:
    openpyxl = None

# ------------------------------------------------------------------------------
# Константы
# ------------------------------------------------------------------------------
AUTHOR_COLUMN = "candidate_name"
SPECIAL_OPTION_ALL = "🌐 Весь базис"  # Специальная опция для выбора всех кодов
SPECIAL_OPTION_YEAR = "📅 Год"

# ------------------------------------------------------------------------------
# Нормализация имен (без изменений)
# ------------------------------------------------------------------------------
_RE_MULTI_SPACE = re.compile(r"\s+")
_RE_DOTS_SPACES = re.compile(r"\s*\.\s*")
_RE_INIT_SPACES = re.compile(r"([A-Za-zА-Яа-я])\.\s+([A-Za-zА-Яа-я])\.")

def _canon_initials(name: str) -> str:
    return _shared_canon_initials(name)

def _display_initials(canon_key: str) -> str:
    return _shared_display_initials(canon_key)

def _fio_to_short(full_name: str) -> str:
    return _shared_fio_to_short(full_name)

def _is_initials_only_option(label: str) -> bool:
    if not isinstance(label, str):
        return False
    s = label.strip()
    if not s:
        return False
    if s.count(".") >= 2 and len(s.split()) <= 2:
        return True
    return False

# ------------------------------------------------------------------------------
# Работа с базой данных (без изменений)
# ------------------------------------------------------------------------------
def _supervisor_columns(df_lineage: pd.DataFrame) -> List[str]:
    return [
        col for col in df_lineage.columns
        if "supervisor" in col.lower() and "name" in col.lower()
    ]


def _build_initials_to_fullnames(df_lineage: pd.DataFrame) -> Dict[str, List[str]]:
    """Совместимая обёртка над общим сопоставлением ФИО."""
    return _shared_build_initials_to_fullnames(df_lineage)


def _compute_selectable_people(
    df_lineage: pd.DataFrame,
    include_without_descendants: bool,
) -> Tuple[List[str], Dict[str, str]]:
    """Совместимая обёртка выбора людей по таблице `article_authors`."""
    return _shared_compute_selectable_people(df_lineage, include_without_descendants)

# ------------------------------------------------------------------------------
# ОБНОВЛЕНИЕ: Фильтрация признаков с поддержкой "Весь базис"
# ------------------------------------------------------------------------------
def _filter_feature_columns(all_feature_cols: List[str], selected_nodes: List[str]) -> List[str]:
    """
    selected_nodes: список узлов + специальные опции ("Весь базис", "Год").
    Возвращает список колонок для анализа.

    Логика:
    - "Весь базис" → все тематические коды
    - "Год" → Year_num
    - Конкретные узлы → узел + все его потомки
    """
    if not selected_nodes:
        return all_feature_cols

    # Проверяем специальные опции
    include_all_basis = SPECIAL_OPTION_ALL in selected_nodes
    include_year = SPECIAL_OPTION_YEAR in selected_nodes or any(
        n.lower() in ("год", "year", "year_num") for n in selected_nodes
    )

    # Если выбран "Весь базис"
    if include_all_basis:
        thematic = [c for c in all_feature_cols if c != "Year_num" and re.match(r"^[\d\.]+$", c)]
        result = thematic
        if include_year:
            result.append("Year_num")
        return result

    # Только год без тематики
    nodes = [n for n in selected_nodes if re.match(r"^[\d\.]+$", n)]
    if not nodes:
        return ["Year_num"] if include_year else []

    # Собираем коды узлов и их потомков
    picked: Set[str] = set()
    for col in all_feature_cols:
        if col == "Year_num":
            continue
        if not re.match(r"^[\d\.]+$", col):
            continue
        for n in nodes:
            # Если col == node или col начинается с node.
            if col == n or col.startswith(n + "."):
                picked.add(col)
                break

    result = sorted(picked)

    if include_year:
        result.append("Year_num")

    return result

def _format_node_option(code: str, classifier_dict: Dict[str, str]) -> str:
    depth = get_code_depth(code)
    indent = "  " * max(0, depth - 1)
    title = classifier_dict.get(code, "")
    if title:
        return f"{indent}{code} — {title}"
    return f"{indent}{code}"

# ------------------------------------------------------------------------------
# Экспорт (без изменений)
# ------------------------------------------------------------------------------
def _download_dataframe(df: pd.DataFrame, filename_stem: str) -> None:
    if df is None or df.empty:
        st.warning("Нет данных для выгрузки.")
        return

    if openpyxl is not None:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="results")
        st.download_button(
            "⬇️ Скачать Excel",
            data=buf.getvalue(),
            file_name=f"{filename_stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Скачать CSV",
            data=csv_bytes,
            file_name=f"{filename_stem}.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ------------------------------------------------------------------------------
# Диалоги (без изменений)
# ------------------------------------------------------------------------------
def _show_articles_instruction() -> None:
    @st.dialog("📖 Инструкция: анализ и сравнение статей", width="large")
    def _dlg():
        st.markdown(ARTICLES_HELP_TEXT)
    _dlg()

def _show_classifier_list() -> None:
    @st.dialog("🧭 Список тематического классификатора", width="large")
    def _dlg():
        classifier = load_articles_classifier()
        if classifier:
            md_text = "### Классификатор для статей\n\n"
            for code in sorted(classifier.keys(), key=lambda x: (get_code_depth(x), x)):
                depth = get_code_depth(code)
                indent = "  " * (depth - 1)
                md_text += f"{indent}**{code}** — {classifier[code]}\n\n"
            st.markdown(md_text)
        else:
            st.markdown(CLASSIFIER_LIST_TEXT)
    _dlg()

def _show_disambiguation_dialog(ambiguous: Dict[str, List[str]]) -> None:
    @st.dialog("⚠️ Уточнение соответствия автора (инициалы → полное ФИО)", width="large")
    def _dlg():
        st.markdown(
            "Для некоторых авторов в `article_authors` инициалы совпадают сразу с несколькими "
            "полными ФИО в базе. Выберите корректное ФИО для продолжения анализа "
            "или откажитесь от анализа."
        )

        choices: Dict[str, str] = {}
        for init_key, fulls in ambiguous.items():
            label = _display_initials(init_key)
            opts = ["— Отказаться от анализа —", *fulls]
            choice = st.selectbox(
                f"Автор: **{label}**",
                options=opts,
                key=f"ac_pick_{init_key}",
            )
            choices[init_key] = choice

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Продолжить", type="primary", use_container_width=True):
                if any(v.startswith("—") for v in choices.values()):
                    st.session_state["ac_abort"] = True
                    st.session_state["ac_disambiguation"] = {}
                else:
                    st.session_state["ac_abort"] = False
                    st.session_state["ac_disambiguation"] = choices
                st.session_state["ac_run_after_disambiguation"] = True
                st.rerun()
        with col2:
            if st.button("❌ Отмена", use_container_width=True):
                st.session_state["ac_abort"] = True
                st.session_state["ac_disambiguation"] = {}
                st.rerun()

    _dlg()

# ------------------------------------------------------------------------------
# Построение датасета (без изменений)
# ------------------------------------------------------------------------------
def _build_articles_dataset(
    selected_options: List[str],
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    df_articles: pd.DataFrame,
    scope: str,
) -> pd.DataFrame:
    """Совместимая обёртка построения датасета по таблице `article_authors`."""
    return build_articles_dataset_for_schools(
        selected_options=selected_options,
        options_meta=options_meta,
        df_lineage=df_lineage,
        idx_lineage=idx_lineage,
        df_articles=df_articles,
        scope=scope,
    )

# ------------------------------------------------------------------------------
# ОБНОВЛЕНИЕ: Основной рендер с опцией "Весь базис"
# ------------------------------------------------------------------------------
def render_articles_comparison_mode(
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    selected_roots: Optional[List[str]] = None,
    classifier_labels: Optional[Dict[str, str]] = None,
    df_articles: pd.DataFrame | None = None,
) -> None:
    """
    Отрисовывает режим сравнения выбранных школ по статьям.

    ИЗМЕНЕНИЯ:
    - Загружается классификатор для статей (core/classifier/articles_classifier.json)
    - Добавлена опция "Весь базис" для анализа по всем тематическим кодам
    - В multiselect показываются только коды до 3-го уровня (макс 2 точки)
    """
    # Загружаем правильный классификатор для статей
    if classifier_labels is None:
        classifier_labels = load_articles_classifier()

    signature = query_params_signature([
        "articles_mode",
        "aa_journals",
        "ac_people",
        "ac_scope",
        "ac_metric",
        "ac_decay",
        "ac_include_without_desc",
        "ac_nodes",
    ])
    if should_hydrate_query("ac_query_signature", signature):
        people_q = [p.strip() for p in st.query_params.get_all("ac_people") if str(p).strip()]
        st.session_state["ac_selected_options_query"] = people_q

        scope_q = str(st.query_params.get("ac_scope", "")).strip()
        if scope_q in {"direct", "all"}:
            st.session_state["ac_scope"] = scope_q

        metric_q = str(st.query_params.get("ac_metric", "")).strip()
        metric_options = list(DISTANCE_METRIC_LABELS.keys())
        if metric_q in metric_options:
            st.session_state["ac_metric"] = metric_options.index(metric_q)

        decay_val = parse_float_param(st.query_params.get("ac_decay", ""), st.session_state.get("ac_decay_factor", 0.5))
        if 0.0 <= decay_val <= 1.0:
            st.session_state["ac_decay_factor"] = decay_val

        if "ac_include_without_desc" in st.query_params:
            st.session_state["ac_include_without_desc"] = parse_bool_param(st.query_params.get("ac_include_without_desc"), False)

        st.session_state["ac_selected_nodes_query"] = [n.strip() for n in st.query_params.get_all("ac_nodes") if str(n).strip()]
        st.session_state["ac_run_state"] = False

    # Пролог
    top_left, top_right = st.columns([1, 1])
    with top_left:
        st.markdown("### 🔬 Сравнение выбранных школ по статьям")
    with top_right:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📖 Инструкция", key="ac_help_btn"):
                _show_articles_instruction()
        with c2:
            if st.button("🧭 Классификатор", key="ac_classifier_btn"):
                _show_classifier_list()

    # Выбор школ
    st.markdown("---")
    st.markdown("### 👥 Выбор научных школ для сравнения")

    include_without_desc = st.checkbox(
        "Разрешить сравнение тематических профилей работ авторов, данные о диссертантах которых отсутствуют в базе",
        value=st.session_state.get("ac_include_without_desc", False),
        key="ac_include_without_desc",
        help=(
            "Если выключено — доступны только руководители, у которых есть диссертанты в базе.\n\n"
            "Если включено — дополнительно доступны (а) люди из базы без диссертантов и (б) авторы из "
            "`article_authors`, которых нет в базе (отображаются как 'Фамилия И.О.')."
        ),
    )

    options, options_meta = _compute_selectable_people(df_lineage, include_without_descendants=include_without_desc)

    if not options:
        st.error("❌ Не удалось сформировать список доступных руководителей/авторов для сравнения.")
        return

    if "ac_selected_options" not in st.session_state:
        st.session_state["ac_selected_options"] = []
        if selected_roots:
            st.session_state["ac_selected_options"] = [r for r in selected_roots if r in options]
    if "ac_selected_options_query" in st.session_state:
        raw_people = st.session_state.get("ac_selected_options_query", [])
        valid_people = [p for p in raw_people if p in options]
        st.session_state["ac_selected_options"] = valid_people
        if len(valid_people) >= 2:
            st.session_state["ac_run_state"] = True
        st.session_state.pop("ac_selected_options_query", None)

    selected_options = st.multiselect(
        "Выберите руководителей научных школ (минимум 2)",
        options=options,
        default=st.session_state.get("ac_selected_options", []),
        key="ac_selected_options",
        help=(
            "Список ограничен теми, чьи 'Фамилия И.О.' встречаются в article_authors.\n\n"
            "Элементы вида 'Фамилия И.О.' — авторы, которых нет в базе диссертаций."
        ),
    )

    if len(selected_options) < 2:
        st.warning("⚠️ Выберите минимум 2 руководителей/авторов для сравнения.")
        return

    # Параметры анализа
    st.markdown("---")
    col_params1, col_params2 = st.columns(2)

    with col_params1:
        st.markdown("### 📐 Параметры анализа")

        scope = st.radio(
            "Охват участников школы",
            options=["direct", "all"],
            format_func=lambda v: "Только прямые ученики (1-й уровень)" if v == "direct" else "Все поколения школы (генеалогия)",
            index=0,
            key="ac_scope",
        )

        metric_options = list(DISTANCE_METRIC_LABELS.keys())
        metric_idx = st.selectbox(
            "Метрика расстояния",
            options=list(range(len(metric_options))),
            format_func=lambda i: DISTANCE_METRIC_LABELS[metric_options[i]],
            index=metric_options.index("euclidean_orthogonal") if "euclidean_orthogonal" in metric_options else 0,
            key="ac_metric",
        )
        metric_choice: DistanceMetric = metric_options[metric_idx]

        decay_factor = st.slider(
            "Коэффициент затухания иерархии (для косоугольного базиса)",
            min_value=0.0,
            max_value=1.0,
            value=float(st.session_state.get("ac_decay_factor", 0.5)),
            step=0.05,
            key="ac_decay_factor",
            help="Используется только для косоугольного базиса.",
        )

    with col_params2:
        st.markdown("### 🎯 Тематический базис")

        # ОБНОВЛЕНИЕ: Фильтруем только коды до 3-го уровня (максимум 2 точки)
        codes_for_display = sorted(
            [c for c in classifier_labels.keys() if re.match(r"^[\d\.]+$", c) and c.count('.') <= 2],
            key=lambda x: (get_code_depth(x), x),
        )

        # Добавляем специальные опции в начало
        node_options = [SPECIAL_OPTION_ALL, SPECIAL_OPTION_YEAR, *codes_for_display]

        if "ac_selected_nodes_query" in st.session_state:
            raw_nodes = st.session_state.get("ac_selected_nodes_query", [])
            valid_nodes = [n for n in raw_nodes if n in node_options]
            st.session_state["ac_selected_nodes"] = valid_nodes
            st.session_state.pop("ac_selected_nodes_query", None)

        # Форматирование опций для отображения
        def format_option(x):
            if x == SPECIAL_OPTION_ALL:
                return x
            if x == SPECIAL_OPTION_YEAR:
                return x
            return _format_node_option(x, classifier_labels)

        selected_nodes = st.multiselect(
            "Выберите разделы для сопоставления",
            options=node_options,
            default=[SPECIAL_OPTION_YEAR],
            format_func=format_option,
            key="ac_selected_nodes",
            help=(
                f"**{SPECIAL_OPTION_ALL}** — анализировать по всем тематическим кодам классификатора\n\n"
                f"**{SPECIAL_OPTION_YEAR}** — добавить временной фактор\n\n"
                "Выберите конкретные узлы классификатора или их комбинацию. "
                "При выборе узла автоматически включаются все его подузлы. "
                "Например, выбрав '1.1 Образовательная среда', вы включите все коды 1.1.1, 1.1.1.1, 1.1.1.2 и т.д."
            ),
        )

        run_clicked = st.button("🚀 Запустить сравнительный анализ", type="primary", key="ac_run_btn")
        if run_clicked:
            st.session_state["ac_run_state"] = True

    # Проверка неоднозначностей
    if run_clicked or st.session_state.get("ac_run_after_disambiguation", False) or st.session_state.get("ac_run_state", False):
        st.session_state["ac_run_after_disambiguation"] = False

        if st.session_state.get("ac_abort", False):
            st.error("❌ Анализ отменён пользователем.")
            st.session_state["ac_abort"] = False
            return

        ambiguous: Dict[str, List[str]] = {}

        for opt in selected_options:
            resolution = _shared_resolve_article_author_to_lineage_root(opt, df_lineage)
            if resolution.ambiguous_full_names and not resolution.root_name:
                key = _shared_canon_article_author_name(opt)
                resolved = st.session_state.get("ac_disambiguation", {}).get(key)
                if not resolved:
                    ambiguous[key] = list(resolution.ambiguous_full_names)

        if ambiguous:
            _show_disambiguation_dialog(ambiguous)
            return

        if df_articles is None:
            with st.spinner("Загрузка базы статей..."):
                df_articles = load_articles_data()

        if df_articles is None or df_articles.empty:
            st.error("❌ Не удалось загрузить данные статей из SQLite. Проверьте таблицы articles_metadata и articles_scores_inf_edu.")
            return

        # Построение датасета
        with st.spinner("Формирование датасета для сравнения..."):
            dataset = _build_articles_dataset(
                selected_options=selected_options,
                options_meta=options_meta,
                df_lineage=df_lineage,
                idx_lineage=idx_lineage,
                df_articles=df_articles,
                scope=scope,
            )

        if dataset.empty:
            st.error("❌ Недостаточно данных: не удалось найти статьи ни по одной выбранной школе/автору.")
            return

        # Диагностика
        school_counts = dataset["school"].value_counts().to_dict()
        non_empty_schools = [k for k, v in school_counts.items() if v > 0]

        if len(non_empty_schools) < 2:
            st.error(
                "❌ Недостаточно данных для сравнения: статьи найдены только для одной школы/автора.\n"
                "Попробуйте выбрать другой охват или другой набор руководителей/авторов."
            )
            with st.expander("🔎 Диагностика: сколько статей попало в каждую школу", expanded=True):
                st.write(school_counts)
            return

        with st.expander("🔎 Диагностика: сколько статей попало в каждую школу", expanded=False):
            st.write(school_counts)

        with st.expander("📄 Список выбранных статей", expanded=False):
            from .results_table import prepare_articles_results_table
            view_df = prepare_articles_results_table(dataset)
            if "Школа" not in view_df.columns and "school" in dataset.columns:
                view_df.insert(2, "Школа", dataset["school"].astype(str).values)
            st.dataframe(
                view_df,
                column_config={
                    "Сайт журнала": st.column_config.LinkColumn("Сайт журнала", display_text="Читать"),
                    "PDF": st.column_config.LinkColumn("PDF", display_text="PDF"),
                    "Elibrary": st.column_config.LinkColumn("Elibrary", display_text="Библиометрия"),
                },
                use_container_width=True,
                hide_index=True,
            )

        scored_dataset = filter_articles_with_thematic_scores(dataset)
        excluded_count = int(len(dataset) - len(scored_dataset))
        if excluded_count > 0:
            st.info(f"Из анализа тематических профилей исключено статей без рассчитанных тематических профилей: {excluded_count}.")
        if scored_dataset.empty:
            st.info("Для выбранных школ найдены статьи, но среди них нет статей с рассчитанными тематическими профилями.")
            return

        scored_school_counts = scored_dataset["school"].value_counts().to_dict()
        scored_non_empty_schools = [k for k, v in scored_school_counts.items() if v > 0]
        if len(scored_non_empty_schools) < 2:
            st.info("Недостаточно данных для сравнения тематических профилей: статьи с рассчитанными тематическими профилями найдены менее чем для двух школ/авторов.")
            return

        # Подготовка признаков
        meta_cols = {
            "Article_id", "Authors", "Title", "Journal", "ISSN", "Volume", "Issue", "school",
            "Year", "Year_num", "Abstract", "Keywords", "DOI", "Pages", "Funding",
            "Has_thematic_scores", "Article_URL", "Article_PDF", "Published_at", "Section", "UDK", "Citation",
            "Issue_URL", "Issue_PDF", "Issue_title", "Issue_serial", "Issue_in_year",
            "Issue_total_pages", "First_page", "Last_page", "Source_pages_text", "Source_article_url",
        }
        all_cols = scored_dataset.columns.tolist()
        classifier_cols = [c for c in all_cols if c not in meta_cols and re.match(r"^[\d\.]+$", str(c))]
        all_feature_cols = [*classifier_cols, "Year_num"]

        # Используем фильтрацию с поддержкой "Весь базис"
        if selected_nodes:
            feature_cols = _filter_feature_columns(all_feature_cols, selected_nodes)
        else:
            # По умолчанию: все тематические коды без года
            feature_cols = classifier_cols

        # Чистим признаки после исключения статей без тематических профилей
        analysis_dataset = scored_dataset.copy()
        for col in feature_cols:
            analysis_dataset[col] = pd.to_numeric(analysis_dataset[col], errors="coerce").fillna(0)

        if not feature_cols:
            st.error("❌ Не выбраны признаки для сравнения. Выберите узлы классификатора или 'Год'.")
            return

        # Информация о выбранных признаках
        with st.expander("ℹ️ Информация о выбранных признаках", expanded=False):
            thematic = [c for c in feature_cols if c != "Year_num"]
            has_year = "Year_num" in feature_cols

            info_text = f"**Всего признаков для анализа:** {len(feature_cols)}\n\n"
            if thematic:
                info_text += f"**Тематические коды:** {len(thematic)}\n\n"
                if len(thematic) <= 20:
                    info_text += "Коды: " + ", ".join(thematic)
                else:
                    info_text += f"Коды: {', '.join(thematic[:20])}... (ещё {len(thematic) - 20})"
            if has_year:
                info_text += "\n\n**Временной фактор:** включён (Year_num)"

            st.markdown(info_text)

        # Анализ
        with st.spinner("Расчёт метрик (силуэт, DB, CH)..."):
            results = compute_article_analysis(
                df=analysis_dataset,
                feature_columns=feature_cols,
                metric=metric_choice,
                decay_factor=float(decay_factor),
            )

        if not results:
            st.error("❌ Не удалось выполнить анализ (проверьте, что выбранные признаки не пустые).")
            return

        # Вывод результатов
        st.markdown("---")
        st.subheader("📊 Результаты сравнительного анализа")

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Коэффициент силуэта", f"{results.get('silhouette_avg', 0):.3f}")
            st.caption("Степень разделения тематических профилей школ/авторов (от -1 до 1).")
        with m2:
            db = results.get("davies_bouldin")
            st.metric("Индекс Дэвиса–Боулдина", f"{db:.3f}" if isinstance(db, (float, int)) else "—")
            st.caption("Меньшие значения соответствуют более чёткому разделению.")
        with m3:
            ch = results.get("calinski_harabasz")
            st.metric("Индекс Калинского–Харабаза", f"{int(ch)}" if isinstance(ch, (float, int)) else "—")
            st.caption("Большие значения соответствуют более чёткому разделению.")

        st.markdown("### 📈 График силуэта")
        fig = create_articles_silhouette_plot(
            sample_scores=results["sample_silhouette_values"],
            labels=results["labels"],
            school_order=results["school_order"],
            overall_score=results["silhouette_avg"],
            metric_label=DISTANCE_METRIC_LABELS[metric_choice],
        )
        st.pyplot(fig)

        # Центроиды
        school_order = results.get("school_order", [])
        centroids_dist = results.get("centroids_dist")

        if isinstance(school_order, list) and len(school_order) == 2 and isinstance(centroids_dist, (float, int)):
            st.info(f"**Евклидово расстояние между центроидами школ:** {centroids_dist:.3f}")
        elif isinstance(school_order, list) and len(school_order) > 2 and centroids_dist is not None:
            with st.expander("📏 Матрица расстояний между центроидами", expanded=False):
                dist_df = pd.DataFrame(centroids_dist, index=school_order, columns=school_order)
                st.dataframe(dist_df, use_container_width=True)

        st.markdown("### 📋 Сводная статистика")
        summary_df = create_comparison_summary(analysis_dataset, feature_cols)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        with st.expander("📥 Скачать результаты", expanded=False):
            _download_dataframe(summary_df, "articles_comparison_stats")

        share_params_button(
            {
                "tab": "articles_comparison",
                "articles_mode": "comparison",
                "aa_journals": st.session_state.get("aa_selected_journals", ["all"]),
                "ac_people": selected_options,
                "ac_scope": scope,
                "ac_metric": metric_choice,
                "ac_decay": decay_factor,
                "ac_nodes": selected_nodes,
                "ac_include_without_desc": include_without_desc,
            },
            key="ac_share",
        )
