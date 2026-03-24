"""
Вкладка Streamlit: Пересечение научных школ через оппонентов.

Математическая модель
=====================
Идея основана на работе А.А. Печникова (2025), где строится граф
пересечения научных журналов по множествам авторов.  В нашей адаптации
вместо одного множества авторов на журнал вводятся **два** множества
на каждую научную школу:

    M_i  — множество **членов** школы i  (все узлы дерева научного
           руководства: корень, его ученики, ученики учеников и т.д.);
    O_i  — множество **оппонентов** школы i  (все лица, указанные как
           оппоненты на защитах диссертаций внутри школы).

Дуга  s_i → s_j  в ориентированном графе означает, что хотя бы один
член школы i выступал оппонентом на защите в школе j, т.е.:

    M_i ∩ O_j ≠ ∅    (стандартная операция пересечения множеств).

Поскольку в общем случае  M_i ∩ O_j ≠ M_j ∩ O_i  (пересекаются
**разные** пары множеств), граф является **направленным** — в отличие
от ненаправленного графа журнального пересечения Печникова.

Матрично:  если  M ∈ {0,1}^{n×|P|}  — матрица членства (школа × персона),
           а  O ∈ {0,1}^{n×|P|}  — матрица оппонентства,
           то  A = M · O^T,  где  A_{ij} = |M_i ∩ O_j|  — вес дуги i→j.
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
import re
from typing import Callable, Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
#  Константы
# ---------------------------------------------------------------------------

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS = [f"supervisors_{i}.name" for i in (1, 2)]
OPPONENT_COLUMNS = [f"opponents_{i}.name" for i in (1, 2, 3)]

SCOPE_LABELS = {
    "direct": "Только первое поколение (прямые ученики)",
    "all": "Все поколения (полное дерево)",
}

# ---------------------------------------------------------------------------
#  Вспомогательные функции (нормализация, поиск по индексу)
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """
    FIX #1: Нормализация ФИО совместима с streamlit_app.py:
    - заменяет точки пробелами (инициалы «И.И.» → «и и»)
    - заменяет «ё» → «е»
    - приводит к нижнему регистру
    - сжимает множественные пробелы
    """
    return re.sub(r"\s+", " ", s.replace(".", " ").replace("ё", "е")).strip().lower()


def _split_full(full: str) -> Tuple[str, str, str]:
    p = full.split()
    p += ["", "", ""]
    return p[0], p[1] if len(p) > 1 else "", p[2] if len(p) > 2 else ""


def _variants(full: str) -> Set[str]:
    last, first, mid = _split_full(full.strip())
    fi, mi = first[:1], mid[:1]
    init = fi + mi
    initdots = ".".join(init) + "." if init else ""
    return {
        v.strip()
        for v in [
            full,
            f"{last} {first} {mid}".strip(),
            f"{last} {init}",
            f"{last} {initdots}",
            f"{init} {last}",
            f"{initdots} {last}",
        ]
        if v
    }


def _rows_for(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    name: str,
) -> pd.DataFrame:
    hits: Set[int] = set()
    for v in _variants(name):
        hits.update(index.get(_norm(v), set()))
    return df.loc[list(hits)] if hits else df.iloc[0:0]

# ---------------------------------------------------------------------------
#  Сбор множеств M_i (члены) и O_i (оппоненты) для школы
# ---------------------------------------------------------------------------

def _collect_members(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    scope: str,
    lineage_func: Callable,
    rows_for_func: Callable,
) -> Tuple[Set[str], pd.DataFrame]:
    """
    Возвращает (множество нормализованных имён членов, подмножество df).
    scope='direct' — только прямые ученики;
    scope='all'    — полное дерево.
    """
    if scope == "direct":
        subset = rows_for_func(df, index, root)
    else:  # 'all'
        _G, subset = lineage_func(df, index, root)

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
      - persons_detail: подробно — кто именно пересёкся
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
                        "Школа-источник (член)": si,
                        "Школа-приёмник (оппонент)": sj,
                        "Персона": person,
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
            "|M| (члены)": len(Mi),
            "|O| (оппоненты)": len(Oi),
            "Кол-во школ, привлекших членов этой школы в качестве оппонентов": out_degree,
            "Суммарное исходящее пересечение": out_weight,
            "Кол-во школ, привлечённых этой школой в качестве оппонентов": in_degree,
            "Суммарное входящее пересечение": in_weight,
        })
    stats_df = pd.DataFrame(stats_rows)

    persons_df = pd.DataFrame(persons_rows) if persons_rows else pd.DataFrame(
        columns=["Школа-источник (член)", "Школа-приёмник (оппонент)", "Персона"]
    )

    return raw_df, jaccard_df, m_share_df, o_share_df, stats_df, persons_df

# ---------------------------------------------------------------------------
#  Построение и визуализация орграфа
# ---------------------------------------------------------------------------

def build_opponents_intersection_graph(
    raw_matrix: pd.DataFrame,
    min_weight: int = 1,
) -> nx.DiGraph:
    """Создаёт направленный граф из матрицы пересечений."""
    G = nx.DiGraph()
    names = list(raw_matrix.index)
    for name in names:
        G.add_node(name)
    for i, si in enumerate(names):
        for j, sj in enumerate(names):
            w = int(raw_matrix.iloc[i, j])
            if w >= min_weight and i != j:
                G.add_edge(si, sj, weight=w)
    return G

# ---------------------------------------------------------------------------
#  Основная функция вкладки Streamlit
# ---------------------------------------------------------------------------

def render_opponents_intersection_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    lineage_func: Callable,
    rows_for_func: Callable,
) -> None:
    """Отображает вкладку «Граф пересечения научных школ»."""

    st.subheader("Граф пересечения научных школ")
    st.markdown(
        """
Анализ строится на **двух множествах** для каждой научной школы:
**M** — члены школы (дерево научного руководства) и **O** — оппоненты
на защитах школы.  Дуга *школа₁ → школа₂* означает, что хотя бы один
**член** школы₁ выступал **оппонентом** в школе₂ (*M₁ ∩ O₂ ≠ ∅*).
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

    selected_schools = st.multiselect(
        "Выберите научных руководителей (≥ 2)",
        options=all_supervisors_sorted,
        default=[],
        key="opponents_intersection_schools",
        help="Каждый руководитель — корень дерева научной школы.",
    )

    if len(selected_schools) < 2:
        st.info("Выберите не менее двух научных школ для анализа.")
        return

    # --- Параметры ---
    st.markdown("---")
    st.markdown("### 2. Параметры анализа")

    col1, col2 = st.columns(2)
    with col1:
        scope_options = list(SCOPE_LABELS.keys())
        scope_labels_list = [SCOPE_LABELS[s] for s in scope_options]
        scope_idx = st.radio(
            "Глубина дерева",
            options=range(len(scope_options)),
            format_func=lambda i: scope_labels_list[i],
            key="opponents_intersection_scope",
            help="«Первое поколение» — только прямые ученики руководителя.  "
                 "«Все поколения» — полное рекурсивное дерево.",
        )
        selected_scope = scope_options[scope_idx]

    with col2:
        min_weight = st.number_input(
            "Минимальный вес дуги (порог)",
            min_value=1,
            max_value=50,
            value=1,
            step=1,
            key="opponents_intersection_min_weight",
            help="Дуги с весом меньше порога не отображаются в графе.",
        )

    # --- Кнопки запуска и сброса ---
    st.markdown("---")

    # FIX #3: кнопка сброса кэша рядом с кнопкой запуска
    col_run, col_reset = st.columns([3, 1])
    with col_run:
        run_clicked = st.button("Построить граф", key="opponents_intersection_run", type="primary")
    with col_reset:
        if st.button("Сбросить кэш",
                     key="opponents_intersection_reset",
                     help="Очистить сохранённые результаты и пересчитать"):
            cache_key = _cache_key(selected_schools, selected_scope)
            if cache_key in st.session_state:
                del st.session_state[cache_key]
            st.rerun()

    # FIX #2: показываем результат из кэша даже без нажатия кнопки
    cache_key = _cache_key(selected_schools, selected_scope)
    if not run_clicked and cache_key not in st.session_state:
        return

    # --- FIX #2: Сбор данных с кэшированием ---
    if run_clicked or cache_key not in st.session_state:
        with st.spinner("Собираем множества членов и оппонентов..."):
            school_data: Dict[str, Tuple[Set[str], Set[str]]] = {}
            info_rows = []
            progress = st.progress(0)
            for i, school_name in enumerate(selected_schools):
                members, subset = _collect_members(
                    df, idx, school_name, selected_scope,
                    lineage_func, rows_for_func,
                )
                opponents = _collect_opponents(subset)
                school_data[school_name] = (members, opponents)
                info_rows.append({
                    "Научная школа": school_name,
                    "Диссертаций": len(subset),
                    "|M| (члены)": len(members),
                    "|O| (оппоненты)": len(opponents),
                })
                progress.progress((i + 1) / len(selected_schools))
            progress.empty()
            st.session_state[cache_key] = (school_data, info_rows)

    school_data, info_rows = st.session_state[cache_key]

    # Краткая сводка по школам
    st.markdown("### Сводка по школам")
    st.dataframe(pd.DataFrame(info_rows), use_container_width=True, hide_index=True)

    # --- Вычисление ---
    with st.spinner("Вычисляем пересечения..."):
        raw_df, jaccard_df, m_share_df, o_share_df, stats_df, persons_df = \
            compute_intersection_analysis(school_data)

    # --- Результаты ---
    st.markdown("---")
    st.markdown("### 3. Матрицы пересечений")
    st.markdown(
        "Строки — школа-источник (*члены* M_i), столбцы — школа-приёмник (*оппоненты* O_j).  "
        "Значение ячейки (i, j) описывает дугу i → j."
    )

    tab_raw, tab_jaccard, tab_mshare, tab_oshare = st.tabs([
        "Пересечение членов и оппонентов |M_i ∩ O_j|",
        "Жаккар-подобная нормировка",
        "Доля от общего кол-ва членов",
        "Доля от общего кол-ва оппонентов",
    ])
    with tab_raw:
        st.caption("w(i→j) = |M_i ∩ O_j|")
        st.dataframe(raw_df, use_container_width=True)
    with tab_jaccard:
        st.caption("k(i→j) = |M_i ∩ O_j| / |M_i ∪ O_j|")
        st.dataframe(jaccard_df, use_container_width=True)
    with tab_mshare:
        st.caption("d_M(i→j) = |M_i ∩ O_j| / |M_i|")
        st.dataframe(m_share_df, use_container_width=True)
    with tab_oshare:
        st.caption("d_O(i→j) = |M_i ∩ O_j| / |O_j|")
        st.dataframe(o_share_df, use_container_width=True)

    # --- Сводка по вершинам ---
    st.markdown("---")
    st.markdown("### 4. Характеристики вершин графа")
    st.dataframe(stats_df, use_container_width=True, hide_index=True)

    # --- Граф ---
    st.markdown("---")
    st.markdown("### 5. Ориентированный граф пересечений научных школ")

    G = build_opponents_intersection_graph(raw_df, min_weight=int(min_weight))

    if G.number_of_edges() == 0:
        st.warning("При выбранном пороге дуг в графе нет. Попробуйте уменьшить порог.")
    else:
        st.caption(
            f"Вершин: {G.number_of_nodes()}, дуг: {G.number_of_edges()}"
            f" (порог веса ≥ {min_weight})"
        )

        try:
            from pyvis.network import Network as PyvisNetwork
            import json as _json

            net = PyvisNetwork(
                height="700px", width="100%", directed=True, bgcolor="#ffffff"
            )
            net.toggle_physics(True)
            for node in G.nodes():
                net.add_node(str(node), label=str(node), title=str(node),
                             shape="box", color="#ADD8E6")
            for u, v, data in G.edges(data=True):
                w = data.get("weight", 1)
                net.add_edge(str(u), str(v), value=w,
                             title=f"{u} → {v}: {w}", arrows="to")
            vis_opts = {
                "nodes": {"font": {"size": 11}},
                "edges": {
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
                    "smooth": {"type": "curvedCW", "roundness": 0.15},
                },
                "physics": {
                    "forceAtlas2Based": {
                        "gravitationalConstant": -80,
                        "centralGravity": 0.01,
                        "springLength": 200,
                    },
                    "solver": "forceAtlas2Based",
                    "stabilization": {"iterations": 200},
                },
            }
            net.set_options(_json.dumps(vis_opts))
            try:
                html = net.generate_html()
            except AttributeError:
                from pathlib import Path as _Path
                tmp = _Path("_tmp_graph.html")
                net.save_graph(str(tmp))
                html = tmp.read_text(encoding="utf-8")
                try:
                    tmp.unlink()
                except Exception:
                    pass
            st.components.v1.html(html, height=720, scrolling=True)

        except ImportError:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(max(8, len(G) * 0.6), 6))
            pos = nx.spring_layout(G, k=2.5, seed=42)
            weights = [G[u][v]["weight"] for u, v in G.edges()]
            max_w = max(weights) if weights else 1
            widths = [1 + 4 * w / max_w for w in weights]
            nx.draw(G, pos, with_labels=True, node_color="#ADD8E6",
                    node_size=2500, font_size=8, arrows=True, width=widths, ax=ax)
            edge_labels = {(u, v): d["weight"] for u, v, d in G.edges(data=True)}
            nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                         font_size=7, ax=ax)
            ax.set_title("Граф экспертного присутствия научных школ", fontsize=12)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    # --- Детализация: кто именно пересёкся ---
    st.markdown("---")
    st.markdown("### 6. Детализация пересечений (персоны)")
    if persons_df.empty:
        st.info("Пересечений не обнаружено.")
    else:
        st.caption(f"Всего записей: {len(persons_df)}")
        filter_source = st.selectbox(
            "Фильтр по школе-источнику",
            options=["Все"] + sorted(persons_df["Школа-источник (член)"].unique()),
            key="opponents_intersection_filter_source",
        )
        display_df = persons_df
        if filter_source != "Все":
            display_df = display_df[display_df["Школа-источник (член)"] == filter_source]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- Скачивание ---
    st.markdown("---")
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            raw_df.to_excel(writer, sheet_name="Пересечение (абс)")
            jaccard_df.to_excel(writer, sheet_name="Жаккар")
            m_share_df.to_excel(writer, sheet_name="Доля от членов")
            o_share_df.to_excel(writer, sheet_name="Доля от оппонентов")
            stats_df.to_excel(writer, index=False, sheet_name="Сводка вершин")
            if not persons_df.empty:
                persons_df.to_excel(writer, index=False, sheet_name="Персоны")
        st.download_button(
            "📥 Скачать Excel",
            data=buf.getvalue(),
            file_name="opponents_intersection_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="opponents_intersection_download_xlsx",
        )
    with col_dl2:
        csv_data = raw_df.to_csv(encoding="utf-8-sig")
        st.download_button(
            "📥 Скачать матрицу (CSV)",
            data=csv_data.encode("utf-8-sig"),
            file_name="opponents_intersection_matrix.csv",
            mime="text/csv",
            key="opponents_intersection_download_csv",
        )


def _cache_key(selected_schools: List[str], scope: str) -> str:
    """FIX #2: Уникальный ключ кэша для данного набора школ и глубины."""
    return "opp_intersection_" + "|".join(sorted(selected_schools)) + "_" + scope
