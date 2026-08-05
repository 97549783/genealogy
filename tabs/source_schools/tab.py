"""Верхний уровень демо-раздела школ по источникам."""
from __future__ import annotations

import io

import streamlit as st

from core.source_schools.export import build_source_school_export_bundle
from core.source_schools.tree import build_source_school_overview_tree
from core.ui.tree_renderers import build_markmap_html, draw_hierarchical_tree
from core.source_schools.data import (
    SOURCE_SCHOOLS_DATA_DIR,
    SourceSchoolDataError,
    build_source_school_index,
    load_source_school_catalog,
)
from .sections import (
    render_disagreements_and_quality_section,
    render_groups_and_chronology_section,
    render_ideas_and_directions_section,
    render_overview_section,
    render_people_section,
    render_sources_and_evidence_section,
)

_VIEW_LABELS = {
    "overview": "Обзор",
    "people": "Состав школы",
    "groups": "Группы и хронология",
    "ideas": "Идеи и направления",
    "sources": "Источники и подтверждения",
    "quality": "Расхождения и качество данных",
}
_RENDERERS = {
    "overview": render_overview_section,
    "people": render_people_section,
    "groups": render_groups_and_chronology_section,
    "ideas": render_ideas_and_directions_section,
    "sources": render_sources_and_evidence_section,
    "quality": render_disagreements_and_quality_section,
}


def render_source_schools_tab() -> None:
    """Отрисовывает демо-раздел школ, описанных в источниках."""
    st.markdown("## Школы по источникам (демо)")
    st.caption("Демонстрационное представление состава и структуры научных школ по опубликованным источникам.")
    if not SOURCE_SCHOOLS_DATA_DIR.exists():
        st.info("Данные о школах по источникам пока не добавлены.")
        return
    try:
        catalog = load_source_school_catalog()
    except SourceSchoolDataError as exc:
        st.error("Не удалось загрузить данные школ по источникам.")
        st.warning("В данных обнаружены демонстрационные или незаполненные записи.")
        return
    if not catalog:
        st.info("В каталоге пока нет доступных школ.")
        return
    labels = {entry["school_id"]: entry["label"] for entry in catalog}
    documents = {entry["school_id"]: entry["document"] for entry in catalog}
    school_id = st.selectbox(
        "Научная школа",
        list(labels),
        format_func=lambda selected_id: labels[selected_id],
        key="source_schools_selected_school",
    )
    document = documents[school_id]
    source_path = next((entry["path"] for entry in catalog if entry["school_id"] == school_id), "")
    tree = build_source_school_overview_tree(document)
    tree_html, _tree_height = build_markmap_html(tree.graph, tree.root_id, branching_mode="bidirectional")
    figure = draw_hierarchical_tree(tree.graph, tree.root_id, title="Структура школы")
    png_buffer = io.BytesIO()
    figure.savefig(png_buffer, format="png", dpi=180, bbox_inches="tight")
    export_bundle = build_source_school_export_bundle(
        document=document,
        source_path=__import__("pathlib").Path(source_path),
        tree=tree,
        tree_html=tree_html,
        tree_png=png_buffer.getvalue(),
    )
    slug = document["школа"].get("идентификатор_школы", "source_school")
    with st.expander("Экспорт данных школы", expanded=False):
        st.download_button("Скачать исходный JSON", export_bundle.json_bytes, file_name=f"{slug}.json", mime="application/json", key="source_schools_export_json")
        st.download_button("Скачать данные в Excel", export_bundle.xlsx_bytes, file_name=f"{slug}.данные.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="source_schools_export_xlsx")
        st.download_button("Скачать список источников", export_bundle.bibliography_txt_bytes, file_name=f"{slug}.список_источников.txt", mime="text/plain", key="source_schools_export_bibliography")
        st.download_button("Скачать полный архив ZIP", export_bundle.zip_bytes, file_name=f"{slug}.полный_экспорт.zip", mime="application/zip", key="source_schools_export_zip")
    required_labels = list(_VIEW_LABELS.values())
    recommended_labels = set(document["демо_представление"].get("рекомендуемые_разделы", []))
    if not set(required_labels).issubset(recommended_labels):
        st.warning("В данных школы указан неполный набор рекомендуемых разделов.")
    st.caption(document["демо_представление"]["методологическое_предупреждение"])
    view = st.radio(
        "Режим просмотра",
        list(_VIEW_LABELS),
        format_func=lambda view_id: _VIEW_LABELS[view_id],
        horizontal=True,
        key="source_schools_view",
    )
    _RENDERERS[view](document, build_source_school_index(document))
