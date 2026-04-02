"""
articles_comparison_tab.py

Изменения:
1. Добавлена опция "Весь базис" для анализа по всем тематическим кодам
2. В multiselect показываются только коды до 3-го уровня (макс 2 точки)
3. При выборе узла автоматически включаются все его потомки
4. Используется правильный классификатор для статей
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

from utils.graph import lineage
from articles_comparison import (
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
    if not isinstance(name, str):
        return ""
    s = name.strip()
    if not s:
        return ""
    s = _RE_MULTI_SPACE.sub(" ", s)
    s = _RE_DOTS_SPACES.sub(".", s)
    s = _RE_INIT_SPACES.sub(r"\1.\2.", s)
    s = _RE_MULTI_SPACE.sub(" ", s)
    return s.lower()

def _display_initials(canon_key: str) -> str:
    if not isinstance(canon_key, str):
        return ""
    s = canon_key.strip()
    if not s:
        return ""
    parts = s.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0].title()
    surname, init = parts[0], parts[1]
    return f"{surname.title()} {init.upper()}".strip()

def _fio_to_short(full_name: str) -> str:
    if not isinstance(full_name, str):
        return ""
    s = full_name.strip()
    if not s:
        return ""
    s = s.replace(".", " ")
    parts = [p for p in s.split() if p]
    if not parts:
        return ""
    surname = parts[0]
    initials = ""
    if len(parts) >= 2:
        initials += parts[1][0] + "."
    if len(parts) >= 3:
        initials += parts[2][0] + "."
    return f"{surname} {initials}".strip()

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

@st.cache_data(show_spinner=False)
def _extract_authors_initials_from_articles() -> Set[str]:
    df_articles = load_articles_data()
    if df_articles is None or df_articles.empty or "Authors" not in df_articles.columns:
        return set()
    authors_set: Set[str] = set()
    for raw in df_articles["Authors"].dropna().astype(str).tolist():
        for part in re.split(r"[;]", raw):
            c = _canon_initials(part)
            if c:
                authors_set.add(c)
    return authors_set

@st.cache_data(show_spinner=False)
def _build_initials_to_fullnames(df_lineage: pd.DataFrame) -> Dict[str, List[str]]:
    names: Set[str] = set()

    if AUTHOR_COLUMN in df_lineage.columns:
        names.update(
            str(v).strip() for v in df_lineage[AUTHOR_COLUMN].dropna().astype(str).tolist()
            if str(v).strip()
        )

    for col in _supervisor_columns(df_lineage):
        names.update(
            str(v).strip() for v in df_lineage[col].dropna().astype(str).tolist()
            if str(v).strip()
        )

    mapping: Dict[str, List[str]] = {}
    for full in names:
        short = _fio_to_short(full)
        key = _canon_initials(short)
        if not key:
            continue
        mapping.setdefault(key, [])
        if full not in mapping[key]:
            mapping[key].append(full)

    for k in list(mapping.keys()):
        mapping[k] = sorted(mapping[k])
    return mapping

@st.cache_data(show_spinner=False)
def _compute_selectable_people(
    df_lineage: pd.DataFrame,
    include_without_descendants: bool,
) -> Tuple[List[str], Dict[str, str]]:
    authors_in_articles = _extract_authors_initials_from_articles()
    initials_to_full = _build_initials_to_fullnames(df_lineage)

    supervisor_cols = _supervisor_columns(df_lineage)
    leaders: Set[str] = set()
    for col in supervisor_cols:
        leaders.update(
            str(v).strip() for v in df_lineage[col].dropna().astype(str).unique()
            if str(v).strip()
        )

    leader_options: List[str] = []
    for full in sorted(leaders):
        key = _canon_initials(_fio_to_short(full))
        if key and key in authors_in_articles:
            leader_options.append(full)

    meta: Dict[str, str] = {o: "leader" for o in leader_options}

    if not include_without_descendants:
        return leader_options, meta

    all_fullnames: Set[str] = set()
    for fulls in initials_to_full.values():
        all_fullnames.update(fulls)

    person_no_desc: List[str] = []
    for full in sorted(all_fullnames):
        if full in leaders:
            continue
        key = _canon_initials(_fio_to_short(full))
        if key and key in authors_in_articles:
            person_no_desc.append(full)

    for o in person_no_desc:
        meta[o] = "person_no_desc"

    initials_only: List[str] = []
    initials_amb: List[str] = []
    for key in sorted(authors_in_articles):
        fulls = initials_to_full.get(key, [])
        if len(fulls) == 0:
            display = _display_initials(key)
            initials_only.append(display)
            meta[display] = "initials_only"
        elif len(fulls) > 1:
            display = _display_initials(key)
            initials_amb.append(display)
            meta[display] = "initials_ambiguous"

    options = [*leader_options, *person_no_desc, *initials_only, *initials_amb]
    return options, meta

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
    @st.dialog("📖 Инструкция: Сравнение по статьям", width="large")
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
            "Для некоторых авторов в `articles_scores.csv` инициалы совпадают сразу с несколькими "
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
    if df_articles is None or df_articles.empty:
        return pd.DataFrame()

    work_articles = df_articles.copy()
    if "Year" in work_articles.columns:
        work_articles["Year_num"] = pd.to_numeric(work_articles["Year"], errors="coerce").fillna(0)
    else:
        work_articles["Year_num"] = 0

    if "_authors_set" not in work_articles.columns:
        work_articles["_authors_set"] = work_articles["Authors"].astype(str).apply(
            lambda s: {_canon_initials(x) for x in re.split(r"[;]", s) if _canon_initials(x)}
        )

    initials_to_full = _build_initials_to_fullnames(df_lineage)
    combined: List[pd.DataFrame] = []

    for opt in selected_options:
        kind = options_meta.get(opt, "")
        school_label = opt

        members_initials: Set[str] = set()
        if kind in ("leader", "person_no_desc"):
            root_full = opt
            if scope == "direct" or scope == "all":
                try:
                    G, _ = lineage(df_lineage, idx_lineage, root_full)
                except TypeError:
                    G, _ = lineage(df_lineage, idx_lineage, root_full)
                if G is not None and getattr(G, "has_node", lambda _: False)(root_full):
                    if scope == "direct":
                        names = set(getattr(G, "successors")(root_full))
                        names.add(root_full)
                    else:
                        names = set(getattr(G, "nodes")())
                        names.add(root_full)
                else:
                    names = {root_full}
            else:
                names = {root_full}

            members_initials = {_canon_initials(_fio_to_short(n)) for n in names if _fio_to_short(n)}
            members_initials = {m for m in members_initials if m}

        elif kind in ("initials_only", "initials_ambiguous"):
            init_key = _canon_initials(opt)
            resolved = st.session_state.get("ac_disambiguation", {}).get(init_key)
            if resolved:
                school_label = resolved
                members_initials = {_canon_initials(_fio_to_short(resolved))}
            else:
                members_initials = {init_key}

        else:
            init_key = _canon_initials(opt)
            members_initials = {init_key} if init_key else set()

        if not members_initials:
            continue

        mask = work_articles["_authors_set"].apply(lambda s: not s.isdisjoint(members_initials))
        sub = work_articles[mask].copy()

        if sub.empty:
            continue

        sub["school"] = school_label
        combined.append(sub)

    if not combined:
        return pd.DataFrame()

    out = pd.concat(combined, ignore_index=True)

    if "_authors_set" in out.columns:
        out = out.drop(columns=["_authors_set"], errors="ignore")

    return out

# ------------------------------------------------------------------------------
# ОБНОВЛЕНИЕ: Основной рендер с опцией "Весь базис"
# ------------------------------------------------------------------------------
def render_articles_comparison_tab(
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    selected_roots: Optional[List[str]] = None,
    classifier_labels: Optional[Dict[str, str]] = None,
) -> None:
    """
    Отрисовывает вкладку сравнения по статьям.

    ИЗМЕНЕНИЯ:
    - Загружается классификатор для статей (articles_classifier.json)
    - Добавлена опция "Весь базис" для анализа по всем тематическим кодам
    - В multiselect показываются только коды до 3-го уровня (макс 2 точки)
    """
    # Загружаем правильный классификатор для статей
    if classifier_labels is None:
        classifier_labels = load_articles_classifier()

    # Пролог
    top_left, top_right = st.columns([1, 1])
    with top_left:
        st.markdown("### 🔬 Сравнение по статьям")
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
            "`articles_scores.csv`, которых нет в базе (отображаются как 'Фамилия И.О.')."
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

    selected_options = st.multiselect(
        "Выберите руководителей научных школ (минимум 2)",
        options=options,
        default=st.session_state.get("ac_selected_options", []),
        key="ac_selected_options",
        help=(
            "Список ограничен теми, чьи 'Фамилия И.О.' встречаются в articles_scores.csv.\n\n"
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
            help="Используется только для 'косоугольного базиса' (oblique).",
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

    # Проверка неоднозначностей
    if run_clicked or st.session_state.get("ac_run_after_disambiguation", False):
        st.session_state["ac_run_after_disambiguation"] = False

        if st.session_state.get("ac_abort", False):
            st.error("❌ Анализ отменён пользователем.")
            st.session_state["ac_abort"] = False
            return

        initials_to_full = _build_initials_to_fullnames(df_lineage)
        ambiguous: Dict[str, List[str]] = {}

        for opt in selected_options:
            if options_meta.get(opt) == "initials_ambiguous":
                key = _canon_initials(opt)
                fulls = initials_to_full.get(key, [])
                resolved = st.session_state.get("ac_disambiguation", {}).get(key)
                if not resolved and len(fulls) > 1:
                    ambiguous[key] = fulls

        if ambiguous:
            _show_disambiguation_dialog(ambiguous)
            return

        # Загрузка статей
        with st.spinner("Загрузка базы статей..."):
            df_articles = load_articles_data()

        if df_articles is None or df_articles.empty:
            st.error("❌ Не удалось загрузить `articles_scores.csv`. Проверьте, что файл доступен в репозитории.")
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

        # Подготовка признаков
        meta_cols = {"Article_id", "Authors", "Title", "Journal", "Volume", "Issue", "school", "Year", "Year_num"}
        all_cols = dataset.columns.tolist()
        classifier_cols = [c for c in all_cols if c not in meta_cols and re.match(r"^[\d\.]+$", str(c))]
        all_feature_cols = [*classifier_cols, "Year_num"]

        # ОБНОВЛЕНИЕ: Используем обновленную функцию фильтрации с поддержкой "Весь базис"
        if selected_nodes:
            feature_cols = _filter_feature_columns(all_feature_cols, selected_nodes)
        else:
            # По умолчанию: все тематические коды без года
            feature_cols = classifier_cols

        # Чистим признаки
        for col in feature_cols:
            dataset[col] = pd.to_numeric(dataset[col], errors="coerce").fillna(0)

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
                df=dataset,
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
        summary_df = create_comparison_summary(dataset, feature_cols)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        with st.expander("📥 Скачать результаты", expanded=False):
            _download_dataframe(summary_df, "articles_comparison_stats")

        with st.expander("📄 Список проанализированных статей", expanded=False):
            view_cols = [c for c in ["Article_id", "school", "Authors", "Title", "Year"] if c in dataset.columns]
            view_df = dataset[view_cols].copy()
            rename = {"Article_id": "ID", "school": "Школа/Автор", "Authors": "Авторы", "Title": "Заголовок", "Year": "Год"}
            view_df = view_df.rename(columns=rename)
            st.dataframe(view_df, use_container_width=True, hide_index=True)
