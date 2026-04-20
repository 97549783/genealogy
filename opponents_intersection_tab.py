"""
Вкладка Streamlit: Взаимосвязи научных школ (через институт оппонентов).

Математическая модель
=====================
Идея основана на работе А.А. Печникова (2025), где строится граф
пересечения научных журналов по множествам авторов.  В нашей адаптации
вместо одного множества авторов на журнал вводятся **два** множества
на каждую научную школу:

    M_i  – множество **членов** школы i  (все узлы дерева научного
           руководства: корень, его ученики, ученики учеников и т.д.);
    O_i  – множество **оппонентов** школы i  (все лица, указанные как
           оппоненты на защитах диссертаций внутри школы).

Связь s_i → s_j означает, что хотя бы один член школы i выступал
оппонентом на защите в школе j, т.е.:

    M_i ∩ O_j ≠ ∅    (стандартная операция пересечения множеств).

Поскольку в общем случае  M_i ∩ O_j ≠ M_j ∩ O_i  (пересекаются
**разные** пары множеств), связь является **направленной**.

Матрично:  если  M ∈ {0,1}^{n×|P|}  – матрица членства (школа × персона),
           а  O ∈ {0,1}^{n×|P|}  – матрица оппонентства,
           то  A = M · O^T,  где  A_{ij} = |M_i ∩ O_j|  – вес связи i→j.
           Матрица A несимметрична, поскольку M ≠ O.

Показатели
----------
1. Пересечение членов и оппонентов научных школ:
       w(i→j) = |M_i ∩ O_j|

2. Жаккар-подобная нормировка:
       k(i→j) = |M_i ∩ O_j| / |M_i ∪ O_j|

3. Доля пересечения от общего количества членов:
       d_M(i→j) = |M_i ∩ O_j| / |M_i|

4. Доля пересечения от общего количества оппонентов:
       d_O(i→j) = |M_i ∩ O_j| / |O_j|

5. Количество школ, привлекших членов этой школы в качестве оппонентов:
       out(i) = |{j ≠ i : M_i ∩ O_j ≠ ∅}|        (исходящая степень)

6. Количество школ, привлечённых этой школой в качестве оппонентов:
       in(j) = |{i ≠ j : M_i ∩ O_j ≠ ∅}|          (входящая степень)

Литература
----------
- Печников А.А. Граф журнального пересечения: определение, модификации
  и содержательный пример // УБС. 2025. № 114. С. 122–137.
- Печников А.А. Пилотная модель сети научных журналов в России:
  анализ на основе графа пересечений // Учён. зап. Казан. ун-та.
  Сер. физ.-мат. наук. 2025. Т. 167, № 2. С. 311–328.
- Tversky A. Features of Similarity // Psychological Review. 1977.
  Vol. 84, No. 4. P. 327–352.
- Latapy M., Magnien C., Del Vecchio N. Basic notions for the analysis
  of large two-mode networks // Social Networks. 2008. Vol. 30(1). P. 31–48.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from utils.graph import lineage, rows_for
from utils.names import norm as _norm
from utils.urls import share_params_button

# ---------------------------------------------------------------------------
#  Константы
# ---------------------------------------------------------------------------

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS = [f"supervisors_{i}.name" for i in (1, 2)]
OPPONENT_COLUMNS = [f"opponents_{i}.name" for i in (1, 2, 3)]

SCOPE_LABELS = {
    "direct": "Только прямые ученики руководителя",
    "all": "Все поколения – ученики, ученики учеников и т.д.",
}

# ---------------------------------------------------------------------------
#  Сбор множеств M_i (члены) и O_i (оппоненты) для школы
# ---------------------------------------------------------------------------

def _collect_members(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    scope: str,
) -> Tuple[Set[str], pd.DataFrame]:
    """
    Возвращает (множество нормализованных имён членов, подмножество df).
    scope='direct' – только прямые ученики;
    scope='all'    – полное дерево.
    """
    if scope == "direct":
        subset = rows_for(df, index, root)
    else:  # 'all'
        _G, subset = lineage(df, index, root)

    members: Set[str] = set()
    members.add(_norm(root))

    if not subset.empty and AUTHOR_COLUMN in subset.columns:
        for val in subset[AUTHOR_COLUMN].dropna():
            n = _norm(str(val))
            if n:
                members.add(n)
    return members, subset


def _collect_opponents(subset: pd.DataFrame) -> Set[str]:
    """Извлекает множество оппонентов из выборки диссертаций школы."""
    opponents: Set[str] = set()
    for col in OPPONENT_COLUMNS:
        if col in subset.columns:
            for val in subset[col].dropna():
                n = _norm(str(val))
                if n:
                    opponents.add(n)
    return opponents

# ---------------------------------------------------------------------------
#  Вычисление матрицы пересечений и показателей
# ---------------------------------------------------------------------------

def compute_intersection_analysis(
    school_data: Dict[str, Tuple[Set[str], Set[str]]],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Принимает  {school_name: (M_i, O_i)}.
    Возвращает 6 DataFrame:
      - raw_matrix:     |M_i ∩ O_j|
      - jaccard_matrix: |M_i ∩ O_j| / |M_i ∪ O_j|
      - member_share:   |M_i ∩ O_j| / |M_i|
      - opponent_share: |M_i ∩ O_j| / |O_j|
      - node_stats:     сводная таблица (in-/out-degree, размеры множеств и др.)
      - persons_detail: подробно – кто именно пересёкся
    """
    names = sorted(school_data.keys())
    n = len(names)

    raw = np.zeros((n, n), dtype=int)
    jaccard = np.zeros((n, n))
    m_share = np.zeros((n, n))
    o_share = np.zeros((n, n))

    persons_rows = []

    for i, si in enumerate(names):
        Mi, _ = school_data[si][0], school_data[si][1]
        for j, sj in enumerate(names):
            if i == j:
                continue
            Oj = school_data[sj][1]
            intersection = Mi & Oj
            card_inter = len(intersection)
            raw[i, j] = card_inter

            union = Mi | Oj
            jaccard[i, j] = card_inter / len(union) if union else 0.0
            m_share[i, j] = card_inter / len(Mi) if Mi else 0.0
            o_share[i, j] = card_inter / len(Oj) if Oj else 0.0

            if card_inter > 0:
                for person in sorted(intersection):
                    persons_rows.append({
                        "Школа, к которой принадлежит человек": si,
                        "Школа, где он выступал оппонентом": sj,
                        "Имя": person,
                    })

    raw_df = pd.DataFrame(raw, index=names, columns=names)
    jaccard_df = pd.DataFrame(np.round(jaccard, 4), index=names, columns=names)
    m_share_df = pd.DataFrame(np.round(m_share, 4), index=names, columns=names)
    o_share_df = pd.DataFrame(np.round(o_share, 4), index=names, columns=names)

    stats_rows = []
    for i, name in enumerate(names):
        Mi, Oi = school_data[name]
        out_degree = int(np.sum(raw[i, :] > 0))
        in_degree  = int(np.sum(raw[:, i] > 0))
        out_weight = int(np.sum(raw[i, :]))
        in_weight  = int(np.sum(raw[:, i]))
        stats_rows.append({
            "Научная школа": name,
            "Членов в школе": len(Mi),
            "Оппонентов привлечено": len(Oi),
            "В скольких других школах оппонировали члены этой школы": out_degree,
            "Всего случаев участия как оппонент (в других школах)": out_weight,
            "Из скольких других школ эта школа приглашала оппонентов": in_degree,
            "Всего приглашённых оппонентов из других школ": in_weight,
        })
    stats_df = pd.DataFrame(stats_rows)

    persons_df = pd.DataFrame(persons_rows) if persons_rows else pd.DataFrame(
        columns=["Школа, к которой принадлежит человек", "Школа, где он выступал оппонентом", "Имя"]
    )

    return raw_df, jaccard_df, m_share_df, o_share_df, stats_df, persons_df

# ---------------------------------------------------------------------------
#  Основная функция вкладки Streamlit
# ---------------------------------------------------------------------------

def render_opponents_intersection_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
) -> None:
    """Отображает вкладку «Взаимосвязи научных школ (через институт оппонентов)»."""

    st.subheader("Взаимосвязи научных школ (через институт оппонентов)")
    st.markdown(
        """
Если учёные из одной научной школы выступают официальными оппонентами на защитах диссертаций
представителей другой школы, то это проявление взаимосвязей между школами. Предлагаемый
инструмент показывает, насколько часто такие взаимодействия происходят и в каком направлении.
        """
    )

    with st.expander("Как это работает подробнее"):
        st.markdown(
            """
**Две группы для каждой школы:**

- **Члены школы** – научный руководитель и все его ученики (а также их ученики, если выбрать полное дерево)
- **Оппоненты школы** – все учёные, которые выступали в качестве официальных оппонентов на защитах диссертаций этой школы

**Связь между школами** фиксируется, когда член одной школы оказался оппонентом в другой.
Это говорит о том, что учёного из школы A пригласили оценивать работу в школе B –
значит, между ними есть научный диалог.
            """
        )

    # --- Выбор научных руководителей ---
    st.markdown("---")
    st.markdown("### 1. Выбор научных школ")

    supervisor_cols = [
        col for col in df.columns
        if "supervisor" in col.lower() and "name" in col.lower()
    ]
    all_supervisors: Set[str] = set()
    for col in supervisor_cols:
        if col in df.columns:
            all_supervisors.update(
                str(v).strip()
                for v in df[col].dropna().unique()
                if str(v).strip()
            )
    all_supervisors_sorted = sorted(all_supervisors)

    if not all_supervisors_sorted:
        st.error("В данных не найдены научные руководители.")
        return

    if not st.session_state.get("opponents_intersection_query_hydrated", False):
        schools_q = [s.strip() for s in st.query_params.get_all("schools") if str(s).strip()]
        if schools_q:
            valid_schools = [s for s in schools_q if s in all_supervisors_sorted]
            if len(valid_schools) >= 2:
                st.session_state["opponents_intersection_schools"] = valid_schools
                st.session_state["opponents_intersection_run_state"] = True

        scope_q = str(st.query_params.get("scope", "")).strip()
        scope_options = list(SCOPE_LABELS.keys())
        if scope_q in scope_options:
            st.session_state["opponents_intersection_scope"] = scope_options.index(scope_q)

        st.session_state["opponents_intersection_query_hydrated"] = True

    selected_schools = st.multiselect(
        "Выберите научных руководителей (≥ 2)",
        options=all_supervisors_sorted,
        default=[],
        key="opponents_intersection_schools",
        help="Каждый руководитель – корень своей научной школы. Все его ученики и их ученики входят в эту школу.",
    )

    if len(selected_schools) < 2:
        st.info("Выберите не менее двух школ, чтобы увидеть связи между ними.")
        return

    # --- Параметры ---
    st.markdown("---")
    st.markdown("### 2. Параметры анализа")

    scope_options = list(SCOPE_LABELS.keys())
    scope_labels_list = [SCOPE_LABELS[s] for s in scope_options]
    scope_idx = st.radio(
        "Кого считать членами школы?",
        options=range(len(scope_options)),
        format_func=lambda i: scope_labels_list[i],
        key="opponents_intersection_scope",
        help="Влияет на то, кто войдёт в состав школы. Больше поколений – шире охват, но анализ занимает дольше.",
    )
    selected_scope = scope_options[scope_idx]

    # --- Кнопки запуска и сброса ---
    st.markdown("---")

    col_run, col_reset = st.columns([3, 1])
    with col_run:
        run_clicked = st.button("Запустить анализ", key="opponents_intersection_run", type="primary")
    with col_reset:
        if st.button("Сбросить кэш",
                     key="opponents_intersection_reset",
                     help="Очистить сохранённые результаты и пересчитать"):
            cache_key = _cache_key(selected_schools, selected_scope)
            if cache_key in st.session_state:
                del st.session_state[cache_key]
            st.rerun()

    if run_clicked:
        st.session_state["opponents_intersection_run_state"] = True

    cache_key = _cache_key(selected_schools, selected_scope)
    if not st.session_state.get("opponents_intersection_run_state", False) and cache_key not in st.session_state:
        return

    # --- Сбор данных с кэшированием ---
    if run_clicked or st.session_state.get("opponents_intersection_run_state", False) or cache_key not in st.session_state:
        with st.spinner("Собираем множества членов и оппонентов..."):
            school_data: Dict[str, Tuple[Set[str], Set[str]]] = {}
            info_rows = []
            progress = st.progress(0)
            for i, school_name in enumerate(selected_schools):
                members, subset = _collect_members(
                    df, idx, school_name, selected_scope,
                )
                opponents = _collect_opponents(subset)
                school_data[school_name] = (members, opponents)
                info_rows.append({
                    "Научная школа": school_name,
                    "Диссертаций в школе": len(subset),
                    "Члены школы": len(members),
                    "Официальные оппоненты на защитах диссертаций школы": len(opponents),
                })
                progress.progress((i + 1) / len(selected_schools))
            progress.empty()
            st.session_state[cache_key] = (school_data, info_rows)

    school_data, info_rows = st.session_state[cache_key]

    # Краткая сводка по школам
    st.markdown("### Что входит в каждую школу")
    st.dataframe(pd.DataFrame(info_rows), use_container_width=True, hide_index=True)
    st.caption(
        "Члены школы – это сам основатель и все его ученики (диссертанты). "
        "Оппоненты – официальные оппоненты на защитах диссертаций членов этой школы."
    )

    # --- Вычисление ---
    with st.spinner("Вычисляем пересечения..."):
        raw_df, jaccard_df, m_share_df, o_share_df, stats_df, persons_df = \
            compute_intersection_analysis(school_data)

    # --- Результаты ---
    st.markdown("---")
    st.markdown("### 3. Насколько школы связаны между собой")
    st.markdown(
        "Таблицы ниже показывают связи между школами. "
        "Строка – школа, к которой принадлежит сам оппонент (т.е. в которой оппонент защищал диссертацию). "
        "Столбец – школа, на защите диссертаций которой этот же учёный выступал в качестве официального оппонента."
    )

    tab_raw, tab_jaccard, tab_mshare, tab_oshare = st.tabs([
        "Число пересечений",
        "Относительная схожесть (Жаккар-подобная нормировка)",
        "Доля от общего кол-ва членов",
        "Доля от общего кол-ва оппонентов",
    ])
    with tab_raw:
        st.caption(
            "Сколько учёных из школы (строка) выступали оппонентами в другой школе (столбец). "
            "Чем больше число – тем теснее связь."
        )
        st.dataframe(raw_df, use_container_width=True)
    with tab_jaccard:
        st.caption(
            "Доля учёных, которые, являясь членами одной школы, выступили в качестве оппонентов "
            "другой школы, относительно общего числа членов обеих школ. "
            "Значение от 0 до 1: 0 – нет связи, 1 – полное совпадение."
        )
        st.dataframe(jaccard_df, use_container_width=True)
    with tab_mshare:
        st.caption("d_M(i→j) = |M_i ∩ O_j| / |M_i|")
        st.dataframe(m_share_df, use_container_width=True)
    with tab_oshare:
        st.caption("d_O(i→j) = |M_i ∩ O_j| / |O_j|")
        st.dataframe(o_share_df, use_container_width=True)

    # --- Сводка по школам ---
    st.markdown("---")
    st.markdown("### 4. Активность каждой школы")
    st.info(
        "Высокий показатель «В скольких других школах оппонировали» означает, что учёные этой школы "
        "востребованы как эксперты в широком круге. "
        "Высокий «Из скольких школ приглашали» – что школа активно привлекает внешних экспертов."
    )
    st.dataframe(stats_df, use_container_width=True, hide_index=True)

    # --- Детализация: кто именно пересёкся ---
    st.markdown("---")
    st.markdown("### 5. Кто именно связывает школы")
    st.markdown(
        "Список учёных, которые являются членами одной школы и одновременно выступали оппонентами в другой."
    )
    if persons_df.empty:
        st.info("Пересечений не обнаружено.")
    else:
        st.caption(f"Всего записей: {len(persons_df)}")
        filter_source = st.selectbox(
            "Показать людей из школы",
            options=["Все"] + sorted(persons_df["Школа, к которой принадлежит человек"].unique()),
            key="opponents_intersection_filter_source",
        )
        display_df = persons_df
        if filter_source != "Все":
            display_df = display_df[display_df["Школа, к которой принадлежит человек"] == filter_source]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- Скачивание ---
    st.markdown("---")
    st.markdown("### Скачать результаты")
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            raw_df.to_excel(writer, sheet_name="Число пересечений")
            jaccard_df.to_excel(writer, sheet_name="Относит схожесть (Жаккар)")
            m_share_df.to_excel(writer, sheet_name="Доля от членов школы")
            o_share_df.to_excel(writer, sheet_name="Доля от оппонентов школы")
            stats_df.to_excel(writer, index=False, sheet_name="Сводка вершин")
            if not persons_df.empty:
                persons_df.to_excel(writer, index=False, sheet_name="Персоны")
        st.download_button(
            "📥 Скачать Excel",
            data=buf.getvalue(),
            file_name="взаимосвязи_научных_школ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="opponents_intersection_download_xlsx",
        )
    with col_dl2:
        csv_data = raw_df.to_csv(encoding="utf-8-sig")
        st.download_button(
            "📥 Скачать матрицу (CSV)",
            data=csv_data.encode("utf-8-sig"),
            file_name="матрица_взаимосвязей_школ.csv",
            mime="text/csv",
            key="opponents_intersection_download_csv",
        )

    share_params_button(
        {
            "schools": selected_schools,
            "scope": selected_scope,
        },
        key="opponents_intersection_share",
    )


def _cache_key(selected_schools: List[str], scope: str) -> str:
    """Уникальный ключ кэша для данного набора школ и глубины."""
    return "opp_intersection_" + "|".join(sorted(selected_schools)) + "_" + scope
