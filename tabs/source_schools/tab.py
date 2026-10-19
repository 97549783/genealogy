"""Школы по источникам: общие представления и ссылки на школы и персон."""
from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from core.source_schools.data import (
    SOURCE_SCHOOLS_DATA_DIR, SourceSchoolDataError, build_source_school_index,
    build_source_school_summary, load_source_school_catalog,
)
from core.source_schools.export import build_source_school_export_bundle
from core.source_schools.lineages import get_source_school_lineages
from core.source_schools.links import build_source_school_url
from core.source_schools.tree import build_source_school_overview_tree
from core.ui.links import build_share_url_from_params
from core.ui.tree_renderers import build_markmap_html, draw_hierarchical_tree
from .sections import (
    render_disagreements_and_quality_section, render_groups_and_chronology_section,
    render_ideas_and_directions_section, render_overview_section, render_people_section,
    render_person_card, render_sources_and_evidence_section,
)

_VIEW_LABELS = {"overview":"Обзор", "people":"Состав школы", "groups":"Группы и хронология",
    "ideas":"Идеи и направления", "sources":"Источники и подтверждения", "quality":"Расхождения и качество данных"}
_PRESENTATIONS={"tree":"Дерево", "table":"Таблица", "together":"Вместе"}
_RENDERERS={"groups":render_groups_and_chronology_section,"ideas":render_ideas_and_directions_section,
    "sources":render_sources_and_evidence_section,"quality":render_disagreements_and_quality_section}
_DEFAULT_SCHOOL="vygotsky_cultural_historical_school"


def _param(key):
    raw=st.query_params.get(key,"")
    return str(raw[-1] if isinstance(raw,list) and raw else raw or "")


def _default_presentation(document):
    return {"дерево":"tree","таблица":"table","вместе":"together"}.get(document["отображение"]["режим_по_умолчанию"],"tree")


def _school_changed(documents):
    sid=st.session_state.get("source_schools_selected_school")
    if sid not in documents:return
    st.query_params.update({"tab":"source_schools","school":sid,"section":"overview","view":_default_presentation(documents[sid])})
    if "person" in st.query_params:del st.query_params["person"]
    st.session_state["source_schools_view"]="overview"


def _section_changed():
    st.query_params["section"]=st.session_state["source_schools_view"]
    if "person" in st.query_params:del st.query_params["person"]


def _presentation_changed(key):
    st.query_params["view"]=st.session_state[key]


def _prepare_export(document,source_path,person_links,lineage_links,school_url):
    tree=build_source_school_overview_tree(document,person_links=person_links,lineage_links=lineage_links,school_link=school_url)
    markup,_=build_markmap_html(tree.graph,tree.root_id,branching_mode="bidirectional")
    figure=draw_hierarchical_tree(tree.graph,tree.root_id,title="Структура школы")
    try:
        png=io.BytesIO();figure.savefig(png,format="png",dpi=120,bbox_inches="tight")
    finally:plt.close(figure)
    return build_source_school_export_bundle(document=document,source_path=Path(source_path),tree=tree,tree_html=markup,tree_png=png.getvalue())


def _render_export(document,source_path,person_links,lineage_links,school_url):
    sid=document["школа"]["идентификатор_школы"]
    with st.expander("Экспорт данных школы",expanded=False):
        st.download_button("Скачать исходный JSON",json.dumps(document,ensure_ascii=False,indent=2).encode("utf-8"),
            file_name=sid+".json",mime="application/json",key="source_schools_json_"+sid)
        if st.button("Подготовить Excel и полный архив",key="source_schools_prepare_"+sid):
            with st.spinner("Подготавливаем таблицы и изображения полной школы…"):
                try:st.session_state["source_schools_bundle_"+sid]=_prepare_export(document,source_path,person_links,lineage_links,school_url)
                except (ValueError,OSError,RuntimeError) as exc:st.error("Не удалось подготовить экспорт: "+str(exc))
        bundle=st.session_state.get("source_schools_bundle_"+sid)
        if bundle:
            st.download_button("Скачать данные в Excel",bundle.xlsx_bytes,file_name=sid+".данные.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key="source_schools_xlsx_"+sid)
            st.download_button("Скачать список источников",bundle.bibliography_txt_bytes,file_name=sid+".источники.txt",mime="text/plain",key="source_schools_bib_"+sid)
            st.download_button("Скачать полный архив ZIP",bundle.zip_bytes,file_name=sid+".полный_экспорт.zip",mime="application/zip",key="source_schools_zip_"+sid)
        st.caption("Полный экспорт включает всю школу. Таблицу текущей выборки можно скачать рядом с табличным представлением.")


def render_source_schools_tab(*,df:pd.DataFrame|None=None,idx:dict|None=None,db_signature=None):
    st.markdown("## Школы по источникам")
    st.caption("Состав, идеи и исторические связи школ по опубликованным источникам.")
    try:catalog=load_source_school_catalog()
    except SourceSchoolDataError as exc:
        st.error("Не удалось загрузить данные школ по источникам.");st.warning(str(exc));return
    if not catalog:st.info("В каталоге пока нет доступных школ.");return
    documents={entry["school_id"]:entry["document"] for entry in catalog}
    labels={entry["school_id"]:entry["label"] for entry in catalog}
    requested_school=_param("school")
    route=tuple(_param(k) for k in ("school","person","view","section"))
    if st.session_state.get("source_schools_applied_route")!=route:
        if requested_school:
            st.session_state["source_schools_selected_school"]=requested_school if requested_school in documents else None
        elif "source_schools_selected_school" not in st.session_state:
            st.session_state["source_schools_selected_school"]=_DEFAULT_SCHOOL if _DEFAULT_SCHOOL in documents else next(iter(documents))
        st.session_state["source_schools_view"]=_param("section") if _param("section") in _VIEW_LABELS else "overview"
        st.session_state["source_schools_applied_route"]=route
    if st.session_state.get("source_schools_selected_school") not in documents:
        st.session_state["source_schools_selected_school"]=None
    sid=st.selectbox("Научная школа",list(documents),format_func=labels.get,index=None,
        key="source_schools_selected_school",on_change=_school_changed,args=(documents,))
    with st.expander("Каталог школ и постоянные ссылки"):
        countries=sorted({tag["название"] for d in documents.values() for tag in d["школа"]["страны"]})
        languages=sorted({tag["название"] for d in documents.values() for tag in d["школа"]["языки_работ"]})
        left,right=st.columns(2)
        with left:country=st.multiselect("Страны школ",countries,key="source_schools_catalog_countries")
        with right:language=st.multiselect("Языки работ школ",languages,key="source_schools_catalog_languages")
        found=0
        for ident,d in documents.items():
            if country and not set(country)&{x["название"] for x in d["школа"]["страны"]}:continue
            if language and not set(language)&{x["название"] for x in d["школа"]["языки_работ"]}:continue
            st.markdown(f"[{labels[ident]}]({build_source_school_url(ident)})")
            found+=1
        if not found:st.info("В каталоге нет школ с выбранными метками.")
    if sid is None:
        if requested_school:st.warning("Школа с таким идентификатором не найдена. Выберите школу из каталога.")
        return
    document=documents[sid]
    indexes=build_source_school_index(document)
    school_url=build_source_school_url(sid)
    person_links={p["id"]:{"href":build_source_school_url(sid,person_id=p["id"],view="person"),
        "title":"Открыть карточку в школе «"+labels[sid]+"» в новой вкладке"} for p in document["объекты"]["персоны"]}
    lineage_links={}
    if df is not None and idx is not None:
        resolutions=get_source_school_lineages(document,df,idx,db_signature)
        lineage_links={pid:{"href":build_share_url_from_params({"tab":"lineages","root":r.root_name}),
            "title":f"Открыть дерево научного руководства: {r.root_name}. Диссертационных записей: {r.record_count}."} for pid,r in resolutions.items()}
    st.subheader(labels[sid])
    st.markdown(f"[Постоянная ссылка на школу ↗]({school_url})")
    with st.expander("Скопировать ссылку на школу"):
        st.code(school_url,language=None)
    summary=build_source_school_summary(document)
    columns=st.columns(4)
    for col,label,key in zip(columns,["В составе описания","Представители","Связанные лица","Источники"],
                            ["included_count","representative_count","related_count","source_count"]):
        with col:st.metric(label,summary[key])
    if document["метаданные"]["статус"]!="готово":
        st.caption("Рабочая редакция: источниковые и редакторские ограничения доступны в разделе качества данных.")
    _render_export(document,next(entry["path"] for entry in catalog if entry["school_id"]==sid),person_links,lineage_links,school_url)
    requested_person=_param("person")
    if requested_person:
        st.markdown(f"[← Перейти к школе]({school_url})")
        if render_person_card(document,indexes,requested_person,person_links=person_links,lineage_links=lineage_links):
            with st.expander("Скопировать ссылку на карточку"):
                st.code(person_links[requested_person]["href"],language=None)
        return
    if _param("view")=="person":st.warning("Для открытия карточки в ссылке нужен идентификатор персоны.")
    section=st.radio("Режим просмотра",list(_VIEW_LABELS),format_func=_VIEW_LABELS.get,horizontal=True,
        key="source_schools_view",on_change=_section_changed)
    if section=="overview":
        key="source_schools_presentation_"+sid
        requested=_param("view")
        token=(sid,requested)
        if st.session_state.get("source_schools_presentation_route")!=token:
            st.session_state[key]=requested if requested in _PRESENTATIONS else _default_presentation(document)
            st.session_state["source_schools_presentation_route"]=token
        if requested and requested not in {*_PRESENTATIONS,"person"}:
            st.warning("Неизвестное представление в ссылке; показан режим по умолчанию.")
        presentation=st.radio("Представление",list(_PRESENTATIONS),format_func=_PRESENTATIONS.get,horizontal=True,
            key=key,on_change=_presentation_changed,args=(key,))
        if not requested_school:st.query_params.update({"tab":"source_schools","school":sid,"view":presentation})
        render_overview_section(document,indexes,lineage_links=lineage_links,person_links=person_links,school_link=school_url,presentation=presentation)
    elif section=="people":render_people_section(document,indexes,person_links=person_links,lineage_links=lineage_links)
    else:_RENDERERS[section](document,indexes)
