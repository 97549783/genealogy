"""
school_trees_tab.py — интерфейс вкладки «Построение деревьев».

Публичный API:
    render_school_trees_tab(df, idx, all_supervisor_names, shared_roots)

Модуль отвечает только за UI. Вся логика отрисовки деревьев
находится в tabs/lineages/rendering.py, алгоритмы обхода графа — в core/lineage/graph.py.
"""

from __future__ import annotations

import io
import zipfile
from typing import Dict, List, Optional, Set

import pandas as pd
import streamlit as st

from .rendering import draw_matplotlib
from core.lineage import compute_lineage_metrics
from core.lineage.graph import TREE_OPTIONS, slug, lineage
from core.lineage.membership import get_school_lineage
from core.db import get_db_signature, SUPERVISOR_COLUMNS
from core.ui.table_display import (
    build_tree_export_df,
    render_dissertations_widget,
)
from core.ui.tree_renderers import build_markmap_html
from core.ui.chrome import show_instruction
from core.ui.links import share_button
from core.ui import render_lineage_metrics_panel
from core.ui.filters import science_field_state_suffix, science_fields_to_query_params
from core.ui.science_filtering import render_science_filtered_lineage_context


# ---------------------------------------------------------------------------
# Таблица диссертаций через st.dataframe
# ---------------------------------------------------------------------------

def _render_tree_table(subset: pd.DataFrame, key: str) -> None:
    """
    Отрисовывает скрытый по умолчанию expander «Результаты».

    Args:
        subset: Исходный DataFrame с данными о диссертациях (результат lineage()).
        key:    Уникальный строковый ключ Streamlit для expander-а.
    """
    render_dissertations_widget(
        subset=subset,
        key=key,
        title="Результаты",
        expanded=False,
        file_name_prefix=key,
    )


def _render_markmap_widget(G, root: str, key: str) -> tuple[str, bytes]:
    """
    Отрисовывает Markmap mind-карту через st.components.v1.html.

    Использует Markmap.js 0.18.12 напрямую из CDN — без streamlit-markmap.
    Pan, zoom, autoFit и центрирование корня гарантированы через JS API.

    Выглядит максимально близко к XMind:
    - Корень в центре, ветви расходятся в стороны
    - Цветные ветви (XMind-палитра)
    - Клик на узел — свернуть/развернуть
    - Pan + zoom мышью
    """
    branching_labels = {
        "Одностороннее ветвление": "unidirectional",
        "Двустороннее ветвление": "bidirectional",
    }
    selected_branching = st.radio(
        "Режим ветвления Markmap",
        options=list(branching_labels.keys()),
        index=0,
        horizontal=True,
        key=f"markmap_mode_{key}",
    )

    html_str, height_px = build_markmap_html(
        G,
        root,
        branching_mode=branching_labels[selected_branching],
    )
    st.components.v1.html(html_str, height=height_px + 20, scrolling=False)
    st.caption(
        "💡 Клик на узел — свернуть/развернуть ветвь. "
        "Колёсико мыши — масштаб; зажмите и тяните — панорама."
    )
    return selected_branching, html_str.encode("utf-8")


def render_school_trees_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    all_supervisor_names: List[str],
    shared_roots: Optional[List[str]] = None,
) -> None:
    """Отрисовывает вкладку «Построение деревьев»."""
    if st.button("📖 Инструкция", key="instruction_lineages"):
        show_instruction("lineages")

    st.markdown("### Фильтр отраслей наук")
    filtered_context = render_science_filtered_lineage_context(
        df=df,
        key_prefix="lineages",
        supervisor_columns=SUPERVISOR_COLUMNS,
    )
    filtered_df = filtered_context.df
    filtered_idx = filtered_context.idx
    filtered_supervisors = filtered_context.all_supervisor_names
    sf_suffix = science_field_state_suffix(filtered_context.science_field_ids)

    st.subheader("Выбор научных руководителей для построения деревьев")
    shared_roots = shared_roots or []
    valid_shared_roots = [r for r in shared_roots if r in filtered_supervisors]
    manual_prefill = "\n".join(r for r in shared_roots if r not in filtered_supervisors)

    roots = st.multiselect(
        "Выберите имена из базы",
        options=sorted(filtered_supervisors),
        default=valid_shared_roots,
        help="Список формируется из столбцов с руководителями",
        max_selections=20,
        key=f"lineages_selected_roots_{sf_suffix}",
    )
    manual = st.text_area(
        "Или добавьте имена вручную в формате: Фамилия Имя Отчество (по одному на строку)",
        height=120,
        value=manual_prefill,
        key=f"lineages_manual_roots_{sf_suffix}",
    )
    manual_list = [r.strip() for r in manual.splitlines() if r.strip()]
    roots = list(dict.fromkeys([*roots, *manual_list]))

    build_clicked = st.button("Построить деревья", type="primary", key="build_trees")
    if build_clicked or shared_roots:
        st.session_state["lineages_built"] = True
    build = st.session_state.get("lineages_built", False)

    tree_option_labels = [label for label, _, _ in TREE_OPTIONS]
    selected_tree_labels = st.multiselect(
        "Типы деревьев для построения",
        options=tree_option_labels,
        default=[tree_option_labels[0]],
        help="Фильтрация по степени применяется только к первому уровню относительно выбранного руководителя.",
        key=f"lineages_tree_types_{sf_suffix}",
    )
    selected_tree_labels = selected_tree_labels or [tree_option_labels[0]]
    selected_tree_configs = [opt for opt in TREE_OPTIONS if opt[0] in selected_tree_labels]
    export_md_outline = st.checkbox(
        "Также сохранить оглавление (.md)",
        value=False,
        key=f"lineages_save_md_{sf_suffix}",
    )

    if not build:
        return

    if not roots:
        st.warning("Пожалуйста, выберите или введите хотя бы одно имя руководителя.")
        return

    all_zip_buf = io.BytesIO()
    with zipfile.ZipFile(all_zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root in roots:
            st.markdown("---")
            st.subheader(f"▶ {root}")

            tree_results = []
            for label, suffix, first_level_filter in selected_tree_configs:
                filter_name = None
                if suffix == "doctors":
                    filter_name = "doctors"
                elif suffix == "candidates":
                    filter_name = "candidates"
                if callable(globals().get("lineage")) and getattr(lineage, "__name__", "") != "lineage":
                    G, subset = lineage(filtered_df, filtered_idx, root, first_level_filter=first_level_filter)
                else:
                    G, subset = get_school_lineage(
                        df=filtered_df,
                        idx=filtered_idx,
                        root=root,
                        first_level_filter_name=filter_name,
                        db_signature=get_db_signature(),
                    )
                tree_results.append(
                    {
                        "label": label,
                        "suffix": suffix,
                        "graph": G,
                        "subset": subset,
                    }
                )

            root_slug = slug(root)
            person_entries: List[tuple[str, bytes]] = []
            has_content = False

            for tree in tree_results:
                label = tree["label"]
                suffix = tree["suffix"]
                G = tree["graph"]
                subset = tree["subset"]

                if G.number_of_edges() == 0:
                    st.info(f"{label}: потомки не найдены для выбранного типа дерева.")
                    continue

                has_content = True
                st.markdown(f"#### 🌳 {label}")

                fig = draw_matplotlib(G, root)
                png_buf = io.BytesIO()
                fig.savefig(png_buf, format="png", dpi=300, bbox_inches="tight")
                png_bytes = png_buf.getvalue()

                st.image(png_bytes, caption="Миниатюра PNG", width=220)

                file_prefix = root_slug if suffix == "general" else f"{root_slug}.{suffix}"
                selected_branching_label, html_bytes = _render_markmap_widget(G, root, key=f"{sf_suffix}_{file_prefix}")

                md_bytes = None
                if export_md_outline:
                    out_lines: List[str] = []

                    def walk(n: str, d: int = 0) -> None:
                        out_lines.append(f"{'  ' * d}- {n}")
                        for c in G.successors(n):
                            walk(c, d + 1)

                    walk(root)
                    md_bytes = ("\n".join(out_lines)).encode("utf-8")

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.download_button(
                        "Скачать PNG",
                        data=png_bytes,
                        file_name=f"{file_prefix}.изображение.png",
                        mime="image/png",
                        key=f"png_{sf_suffix}_{file_prefix}",
                    )
                with c2:
                    st.download_button(
                        f"Скачать HTML ({selected_branching_label})",
                        data=html_bytes,
                        file_name=f"{file_prefix}.интерактивная_схема.html",
                        mime="text/html",
                        key=f"html_{sf_suffix}_{file_prefix}",
                    )
                with c3:
                    if md_bytes is not None:
                        st.download_button(
                            "Скачать оглавление .md",
                            data=md_bytes,
                            file_name=f"{file_prefix}.оглавление.md",
                            mime="text/markdown",
                            key=f"md_{sf_suffix}_{file_prefix}",
                        )
                    else:
                        st.empty()

                metrics = compute_lineage_metrics(
                    graph=G,
                    root=root,
                    subset=subset,
                    include_extended=True,
                )
                render_lineage_metrics_panel(
                    metrics,
                    key_prefix=f"{sf_suffix}_{file_prefix}",
                    context_label=f"{label}: {root}",
                    expanded=False,
                    include_extended=True,
                    include_help_button=True,
                )

                _render_tree_table(subset, key=f"{sf_suffix}_{file_prefix}")

                person_entries.append((f"{file_prefix}.изображение.png", png_bytes))
                person_entries.append((f"{file_prefix}.интерактивная_схема.html", html_bytes))
                try:
                    xlsx_df_zip, csv_df_zip = build_tree_export_df(subset)
                    buf_xlsx = io.BytesIO()
                    with pd.ExcelWriter(buf_xlsx, engine="openpyxl") as writer:
                        xlsx_df_zip.to_excel(writer, index=False, sheet_name="Диссертации")
                    person_entries.append((f"{file_prefix}.xlsx", buf_xlsx.getvalue()))
                    person_entries.append((
                        f"{file_prefix}.csv",
                        csv_df_zip.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                    ))
                except Exception:
                    pass
                if md_bytes is not None:
                    person_entries.append((f"{file_prefix}.оглавление.md", md_bytes))

            if has_content and len(person_entries) > 1:
                person_zip_buf = io.BytesIO()
                with zipfile.ZipFile(person_zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as person_zip:
                    for fname, content in person_entries:
                        person_zip.writestr(fname, content)
                        zf.writestr(f"{root_slug}/{fname}", content)

                st.download_button(
                    "⬇ Скачать всё для этого руководителя (ZIP)",
                    data=person_zip_buf.getvalue(),
                    file_name=f"{root_slug}.архив.zip",
                    mime="application/zip",
                    key=f"zip_{sf_suffix}_{root_slug}",
                )

    if len(roots) > 1:
        st.markdown("---")
        st.download_button(
            label="⬇ Скачать всё (ZIP)",
            data=all_zip_buf.getvalue(),
            file_name="архив_деревьев.zip",
            mime="application/zip",
            key=f"dl_zip_all_trees_{sf_suffix}",
        )

    st.markdown("---")
    share_button(
        roots,
        key="lineages_share",
        extra_params={"tab": "lineages", **science_fields_to_query_params(filtered_context.science_field_ids)},
    )
