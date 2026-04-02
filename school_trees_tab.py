"""
school_trees_tab.py — интерфейс вкладки «Построение деревьев».

Публичный API:
    render_school_trees_tab(df, idx, all_supervisor_names, shared_roots)

Модуль отвечает только за UI. Вся логика отрисовки деревьев
находится в school_trees.py, алгоритмы обхода графа — в utils/graph.py.
"""

from __future__ import annotations

import io
import zipfile
from typing import Callable, Dict, List, Optional, Set

import pandas as pd
import streamlit as st

from school_trees import build_pyvis_html, draw_matplotlib
from utils.graph import TREE_OPTIONS, lineage
from utils.ui import download_data_dialog, show_instruction
from utils.urls import share_button


def render_school_trees_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    all_supervisor_names: List[str],
    shared_roots: Optional[List[str]] = None,
) -> None:
    """
    Отрисовывает вкладку «Построение деревьев».

    Аргументы:
        df                   — основной DataFrame с диссертациями
        idx                  — индекс имён (build_index)
        all_supervisor_names — список всех научных руководителей для виджета выбора
        shared_roots         — имена, переданные через URL (?root=...), или None
    """
    # ── Заголовок и инструкция ────────────────────────────────────────────────
    col_title, col_help = st.columns([0.85, 0.15])
    with col_title:
        st.subheader("Построение деревьев научного руководства")
    with col_help:
        if st.button("📖 Инструкция", key="lineages_help_btn"):
            show_instruction("lineages")

    # ── Выбор руководителей ───────────────────────────────────────────────────
    default_roots = shared_roots or []
    selected_roots: List[str] = st.multiselect(
        "Выберите имена из базы",
        options=all_supervisor_names,
        default=[r for r in default_roots if r in all_supervisor_names],
        placeholder="Начните вводить фамилию…",
        key="lineages_selected_roots",
    )

    # ── Опции ─────────────────────────────────────────────────────────────────
    col_opts_l, col_opts_r = st.columns([0.6, 0.4])
    with col_opts_l:
        tree_option_labels = [label for label, _, _ in TREE_OPTIONS]
        tree_choice = st.radio(
            "Тип дерева",
            options=range(len(TREE_OPTIONS)),
            format_func=lambda i: tree_option_labels[i],
            horizontal=True,
            key="lineages_tree_type",
        )
    with col_opts_r:
        save_md = st.checkbox(
            "Также сохранить оглавление (.md)",
            value=False,
            key="lineages_save_md",
        )

    _, tree_slug, first_level_filter = TREE_OPTIONS[tree_choice]

    # ── Кнопка запуска ────────────────────────────────────────────────────────
    run = st.button("Построить деревья", type="primary", key="lineages_run")
    if not run:
        return
    if not selected_roots:
        st.warning("Выберите хотя бы одного научного руководителя.")
        return

    # ── Построение деревьев ───────────────────────────────────────────────────
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root_name in selected_roots:
            st.markdown(f"---\n### 🌳 {root_name}")

            G, subset = lineage(df, idx, root_name, first_level_filter)

            if G.number_of_nodes() == 0:
                st.info(f"Потомки для «{root_name}» не найдены.")
                continue

            node_count = G.number_of_nodes()
            edge_count = G.number_of_edges()
            st.caption(
                f"Узлов: {node_count} · Связей: {edge_count} · "
                f"Диссертаций в таблице: {len(subset)}"
            )

            # ── Статичный PNG ────────────────────────────────────────────────
            with st.spinner("Рисую PNG…"):
                fig = draw_matplotlib(G, root_name)
            st.pyplot(fig)

            # PNG → в ZIP
            png_buf = io.BytesIO()
            fig.savefig(png_buf, format="png", bbox_inches="tight", dpi=150)
            import matplotlib.pyplot as plt
            plt.close(fig)
            root_slug = _slugify(root_name)
            zf.writestr(f"{root_slug}_{tree_slug}.png", png_buf.getvalue())

            # Кнопка скачивания PNG
            st.download_button(
                label="⬇ Скачать PNG",
                data=png_buf.getvalue(),
                file_name=f"{root_slug}_{tree_slug}.png",
                mime="image/png",
                key=f"dl_png_{root_slug}_{tree_slug}",
            )

            # ── Интерактивный граф ───────────────────────────────────────────
            with st.spinner("Генерирую интерактивный граф…"):
                html_content = build_pyvis_html(G, root_name)
            st.components.v1.html(html_content, height=1050, scrolling=False)

            # HTML → в ZIP
            html_bytes = html_content.encode("utf-8")
            zf.writestr(f"{root_slug}_{tree_slug}.html", html_bytes)

            # Кнопка скачивания HTML
            st.download_button(
                label="⬇ Скачать HTML",
                data=html_bytes,
                file_name=f"{root_slug}_{tree_slug}.html",
                mime="text/html",
                key=f"dl_html_{root_slug}_{tree_slug}",
            )

            # ── Таблица данных ───────────────────────────────────────────────
            if not subset.empty:
                with st.expander(f"📋 Таблица данных ({len(subset)} строк)", expanded=False):
                    st.dataframe(subset, use_container_width=True, hide_index=True)
                    download_data_dialog(
                        subset,
                        file_base=f"{root_slug}_{tree_slug}_data",
                        key_prefix=f"dl_data_{root_slug}_{tree_slug}",
                    )

            # ── Оглавление Markdown ──────────────────────────────────────────
            if save_md:
                md_text = _build_md_toc(G, root_name)
                md_bytes = md_text.encode("utf-8")
                zf.writestr(f"{root_slug}_{tree_slug}_toc.md", md_bytes)
                st.download_button(
                    label="⬇ Скачать оглавление (.md)",
                    data=md_bytes,
                    file_name=f"{root_slug}_{tree_slug}_toc.md",
                    mime="text/markdown",
                    key=f"dl_md_{root_slug}_{tree_slug}",
                )

    # ── Кнопка «Скачать всё ZIP» (если несколько деревьев) ───────────────────
    if len(selected_roots) > 1:
        st.markdown("---")
        st.download_button(
            label="⬇ Скачать всё (ZIP)",
            data=zip_buf.getvalue(),
            file_name=f"trees_{tree_slug}.zip",
            mime="application/zip",
            key=f"dl_zip_{tree_slug}",
        )

    # ── Кнопка «Поделиться» ───────────────────────────────────────────────────
    st.markdown("---")
    share_button(selected_roots, key="lineages_share")


# ── Вспомогательные ───────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    """Безопасное имя файла из произвольной строки."""
    import re
    return re.sub(r"[^A-Za-zА-Яа-я0-9]+", "_", s).strip("_") or "tree"


def _build_md_toc(G, root: str, indent: str = "  ") -> str:
    """
    Строит текстовое оглавление дерева в формате Markdown.
    Использует BFS, сохраняя порядок по уровням.
    """
    from collections import deque

    lines: list[str] = [f"# {root}\n"]
    q: deque = deque([(root, 0)])
    seen: set = set()
    while q:
        node, depth = q.popleft()
        if node in seen:
            continue
        seen.add(node)
        if node != root:
            lines.append(f"{indent * depth}- {node}")
        for child in G.successors(node):
            q.append((child, depth + 1))
    return "\n".join(lines)
