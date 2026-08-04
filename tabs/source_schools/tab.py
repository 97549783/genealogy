"""Верхний уровень демо-раздела школ по источникам."""
from __future__ import annotations
import streamlit as st
from .data import SOURCE_SCHOOLS_DATA_DIR, SourceSchoolDataError, build_source_school_index, load_source_school_catalog
from .sections import render_disagreements_and_quality_section, render_groups_and_chronology_section, render_ideas_and_directions_section, render_overview_section, render_people_section, render_sources_and_evidence_section

_VIEW_LABELS={"overview":"Обзор","people":"Состав школы","groups":"Группы и хронология","ideas":"Идеи и направления","sources":"Источники и подтверждения","quality":"Расхождения и качество данных"}
_RENDERERS={"overview":render_overview_section,"people":render_people_section,"groups":render_groups_and_chronology_section,"ideas":render_ideas_and_directions_section,"sources":render_sources_and_evidence_section,"quality":render_disagreements_and_quality_section}

def render_source_schools_tab() -> None:
    """Отрисовывает демо-раздел школ, описанных в источниках."""
    st.markdown("## Школы по источникам (демо)")
    st.caption("Демонстрационное представление состава и структуры научных школ по опубликованным источникам.")
    if not SOURCE_SCHOOLS_DATA_DIR.exists():
        st.info("Данные о школах по источникам пока не добавлены.")
        return
    try:
        catalog=load_source_school_catalog()
    except SourceSchoolDataError as exc:
        st.error("Не удалось загрузить данные школ по источникам."); st.warning(str(exc)); return
    if not catalog:
        st.info("В каталоге пока нет доступных школ."); return
    labels={e["school_id"]:e["label"] for e in catalog}; docs={e["school_id"]:e["document"] for e in catalog}
    sid=st.selectbox("Научная школа", list(labels), format_func=lambda x: labels[x], key="source_schools_selected_school")
    doc=docs[sid]
    required=list(_VIEW_LABELS.values())
    if not set(required).issubset(set(doc["демо_представление"].get("рекомендуемые_разделы", []))):
        st.warning("В данных школы указан неполный набор рекомендуемых разделов.")
    st.caption(doc["демо_представление"]["методологическое_предупреждение"])
    view=st.radio("Режим просмотра", list(_VIEW_LABELS), format_func=lambda x:_VIEW_LABELS[x], horizontal=True, key="source_schools_view")
    _RENDERERS[view](doc, build_source_school_index(doc))
