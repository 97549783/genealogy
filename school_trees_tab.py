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
from typing import Dict, List, Optional, Set

import pandas as pd
import streamlit as st

from school_trees import build_pyvis_html, draw_matplotlib
from utils.graph import TREE_OPTIONS, lineage, slug
from utils.table_display import (
    build_tree_display_df,
    build_tree_export_df,
)
from utils.ui import show_instruction
from utils.urls import share_button


# ---------------------------------------------------------------------------
# Служебная функция: инъекция CSS для размера шрифта в таблице
# ---------------------------------------------------------------------------

def _inject_table_font_size(px: int) -> None:
    """
    Инъектирует CSS, который устанавливает размер шрифта в ячейках
    всех Streamlit-таблиц (фрейм с data-testid="stDataFrame").
    Вызывается перед каждым рендером таблицы, чтобы отразить
    текущее значение слайдера.

    Args:
        px: Размер шрифта в пикселях (8–22).
    """
    st.markdown(
        f"""
        <style>
        [data-testid="stDataFrame"] iframe {{
            /* увеличиваем высоту фрейма, чтобы таблица не обрезалась */
            min-height: {max(300, px * 20)}px;
        }}
        [data-testid="stDataFrame"] [role="gridcell"],
        [data-testid="stDataFrame"] [role="columnheader"] {{
            font-size: {px}px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Главная функция рендеринга таблицы списка диссертаций
# ---------------------------------------------------------------------------

def _render_tree_table(subset: pd.DataFrame, key: str) -> None:
    """
    Отрисовывает скрытый по умолчанию expander «Список диссертаций в дереве»
    со следующими элементами:

    1. Слайдер размера шрифта (8–22 пк, по умолчанию 13).
    2. Таблица с русскими названиями колонок.
    3. Колонка «Автореферат» отображается через LinkColumn: текст берётся
       из служебной колонки «_abstract_label» («Скачать»/«Читать»/«»).
       Служебная колонка скрита (визуально).
    4. Кнопки «Скачать Excel» / «Скачать CSV».

    Колонка «Автореферат» в xlsx: формула =HYPERLINK(«..», «Скачать»/«Читать»).
    Колонка «Автореферат» в csv: плоская строка URL.

    Args:
        subset: Исходный DataFrame с данными о диссертациях (результат lineage()).
        key:    Уникальный строковый ключ Streamlit для expander-а.
    """
    label = f"📋 Список диссертаций в дереве ({len(subset)})"
    with st.expander(label, expanded=False):
        display_df = build_tree_display_df(subset)
        if display_df.empty:
            st.info("Данные отсутствуют.")
            return

        # --- Слайдер шрифта ---
        font_px = st.slider(
            "Размер шрифта в таблице",
            min_value=8,
            max_value=22,
            value=13,
            step=1,
            key=f"font_size_{key}",
            help="Изменяет размер шрифта в ячейках таблицы.",
        )
        _inject_table_font_size(font_px)

        # --- Настройка LinkColumn ---
        # build_tree_display_df добавляет служебную колонку «_abstract_label»
        # с значениями 'Скачать'/'Читать'/''. Именно эта колонка
        # используется как display_text для LinkColumn.
        # Сама колонка «_abstract_label» скрывается.
        abstract_col = "Автореферат"
        column_config: dict = {}
        if abstract_col in display_df.columns:
            column_config[abstract_col] = st.column_config.LinkColumn(
                label=abstract_col,
                display_text="_abstract_label",
                help="Скачать PDF или читать онлайн на rusneb.ru.",
            )
        if "_abstract_label" in display_df.columns:
            column_config["_abstract_label"] = st.column_config.Column(
                label="_abstract_label",
                disabled=True,
                # Streamlit не поддерживает hidden= напрямую,
                # но колонка останется узкой и неприметной — её
                # можно скрыть, сдвинув в право.
            )

        st.dataframe(
            display_df,
            use_container_width=True,
            column_config=column_config,
            key=f"df_{key}",
        )

        # --- Кнопки экспорта ---
        xlsx_df, csv_df = build_tree_export_df(subset)

        col_xlsx, col_csv = st.columns(2)
        with col_xlsx:
            buf = io.BytesIO()
            try:
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    xlsx_df.to_excel(writer, index=False, sheet_name="Диссертации")
                st.download_button(
                    label="📊 Скачать Excel",
                    data=buf.getvalue(),
                    file_name=f"{key}.sampling.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_xlsx_{key}",
                    use_container_width=True,
                )
            except Exception as exc:
                st.error(f"Ошибка создания Excel: {exc}")

        with col_csv:
            csv_bytes = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📄 Скачать CSV",
                data=csv_bytes,
                file_name=f"{key}.sampling.csv",
                mime="text/csv",
                key=f"dl_csv_{key}",
                use_container_width=True,
            )


def render_school_trees_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    all_supervisor_names: List[str],
    shared_roots: Optional[List[str]] = None,
) -> None:
    """Отрисовывает вкладку «Построение деревьев»."""
    if st.button("📖 Инструкция", key="instruction_lineages"):
        show_instruction("lineages")

    st.subheader("Выбор научных руководителей для построения деревьев")
    shared_roots = shared_roots or []
    valid_shared_roots = [r for r in shared_roots if r in all_supervisor_names]
    manual_prefill = "\n".join(r for r in shared_roots if r not in all_supervisor_names)

    roots = st.multiselect(
        "Выберите имена из базы",
        options=sorted(all_supervisor_names),
        default=valid_shared_roots,
        help="Список формируется из столбцов с руководителями",
        key="lineages_selected_roots",
    )
    manual = st.text_area(
        "Или добавьте имена вручную в формате: Фамилия Имя Отчество (по одному на строку)",
        height=120,
        value=manual_prefill,
        key="lineages_manual_roots",
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
        key="lineages_tree_types",
    )
    selected_tree_labels = selected_tree_labels or [tree_option_labels[0]]
    selected_tree_configs = [opt for opt in TREE_OPTIONS if opt[0] in selected_tree_labels]
    export_md_outline = st.checkbox(
        "Также сохранить оглавление (.md)",
        value=False,
        key="lineages_save_md",
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
                G, subset = lineage(df, idx, root, first_level_filter=first_level_filter)
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

                html = build_pyvis_html(G, root)
                st.components.v1.html(html, height=800, width=2000, scrolling=True)
                html_bytes = html.encode("utf-8")

                md_bytes = None
                if export_md_outline:
                    out_lines: List[str] = []

                    def walk(n: str, d: int = 0) -> None:
                        out_lines.append(f"{'  ' * d}- {n}")
                        for c in G.successors(n):
                            walk(c, d + 1)

                    walk(root)
                    md_bytes = ("\n".join(out_lines)).encode("utf-8")

                file_prefix = root_slug if suffix == "general" else f"{root_slug}.{suffix}"

                # Кнопки скачивания дерева (не данных таблицы — они теперь в expander)
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.download_button(
                        "Скачать PNG",
                        data=png_bytes,
                        file_name=f"{file_prefix}.png",
                        mime="image/png",
                        key=f"png_{file_prefix}",
                    )
                with c2:
                    st.download_button(
                        "Скачать HTML",
                        data=html_bytes,
                        file_name=f"{file_prefix}.html",
                        mime="text/html",
                        key=f"html_{file_prefix}",
                    )
                with c3:
                    if md_bytes is not None:
                        st.download_button(
                            "Скачать оглавление .md",
                            data=md_bytes,
                            file_name=f"{file_prefix}.xmind.md",
                            mime="text/markdown",
                            key=f"md_{file_prefix}",
                        )
                    else:
                        st.empty()

                # ----------------------------------------------------------------
                # Список диссертаций + экспорт (скрыт по умолчанию)
                # ----------------------------------------------------------------
                _render_tree_table(subset, key=file_prefix)

                person_entries.append((f"{file_prefix}.png", png_bytes))
                person_entries.append((f"{file_prefix}.html", html_bytes))
                # Для ZIP по-прежнему кладём исходный CSV/xlsx
                try:
                    xlsx_df_zip, csv_df_zip = build_tree_export_df(subset)
                    buf_xlsx = io.BytesIO()
                    with pd.ExcelWriter(buf_xlsx, engine="openpyxl") as writer:
                        xlsx_df_zip.to_excel(writer, index=False, sheet_name="Диссертации")
                    person_entries.append((f"{file_prefix}.sampling.xlsx", buf_xlsx.getvalue()))
                    person_entries.append((
                        f"{file_prefix}.sampling.csv",
                        csv_df_zip.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                    ))
                except Exception:
                    pass
                if md_bytes is not None:
                    person_entries.append((f"{file_prefix}.xmind.md", md_bytes))

            if has_content and len(person_entries) > 1:
                person_zip_buf = io.BytesIO()
                with zipfile.ZipFile(person_zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as person_zip:
                    for fname, content in person_entries:
                        person_zip.writestr(fname, content)
                        zf.writestr(f"{root_slug}/{fname}", content)

                st.download_button(
                    "⬇ Скачать всё для этого руководителя (ZIP)",
                    data=person_zip_buf.getvalue(),
                    file_name=f"{root_slug}.zip",
                    mime="application/zip",
                    key=f"zip_{root_slug}",
                )

    if len(roots) > 1:
        st.markdown("---")
        st.download_button(
            label="⬇ Скачать всё (ZIP)",
            data=all_zip_buf.getvalue(),
            file_name="trees_bundle.zip",
            mime="application/zip",
            key="dl_zip_all_trees",
        )

    st.markdown("---")
    share_button(roots, key="lineages_share")
