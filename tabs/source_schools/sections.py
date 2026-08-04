"""Отрисовка внутренних режимов демо-раздела школ по источникам."""
from __future__ import annotations
from typing import Any, Mapping
from urllib.parse import urlparse
import streamlit as st
from .tables import build_evidence_dataframe, build_people_dataframe, build_sources_dataframe, filter_people_dataframe, resolve_person_names

def _safe_url(url: str | None) -> bool:
    return bool(url) and urlparse(url).scheme in {"http","https"}

def _source_label(s): return s.get("краткое_название") or s.get("библиографическое_описание", s.get("id",""))
def _evidence_status(v): return "Явное утверждение" if v else "Интерпретация"

def render_overview_section(document, indexes) -> None:
    """Отрисовывает обзор школы."""
    school=document["школа"]; demo=document["демо_представление"]
    st.subheader(demo["заголовок_страницы"]); st.caption(demo["подзаголовок"])
    c1,c2,c3=st.columns(3); c1.metric("Представители", len(school["персоны"])); c2.metric("Источники", len(school["источники"])); c3.metric("Подтверждения", len(school["подтверждения"]))
    st.markdown(f"**Каноническое название:** {school['каноническое_название']}")
    with st.expander("Альтернативные названия", expanded=False):
        for a in school.get("альтернативные_названия",[]): st.write(f"{a.get('название')} — {a.get('примечание','')}")
    st.write(f"**Тип школы:** {school.get('тип_школы','')}"); st.caption(school.get("примечание_к_типу",""))
    st.write("**Дисциплинарные области:** "+"; ".join(school.get("дисциплинарные_области",[])))
    st.write("**Ключевые слова:** "+"; ".join(school.get("ключевые_слова",[])))
    for k,l in [("основная_идея","Основная идея"),("проблема","Проблема"),("гипотеза","Гипотеза"),("теория","Теория"),("метод","Метод")]: st.write(f"**{l}:** {school.get(k,'')}")
    st.write(f"**Хронология:** {school.get('хронология',{}).get('кратко','')}")
    st.write("**География:** "+"; ".join(school.get("география",[]))); st.write("**Организации:** "+"; ".join(school.get("организации",[])))

def render_people_section(document, indexes) -> None:
    """Отрисовывает состав школы с фильтрами и карточкой персоны."""
    st.warning(document["демо_представление"]["методологическое_предупреждение"])
    df=build_people_dataframe(document)
    q=st.text_input("Поиск по представителям", key="source_schools_people_query")
    cats=st.multiselect("Категория включения", sorted(df["Категория"].dropna().unique()), key="source_schools_people_categories")
    roles=st.multiselect("Роль в школе", sorted({x for v in df["Роли"] for x in str(v).split("; ") if x}), key="source_schools_people_roles")
    groups=st.multiselect("Группа или контекст", sorted({x for v in df["Группы и контексты"] for x in str(v).split("; ") if x}), key="source_schools_people_groups")
    source_options={s["id"]:_source_label(s) for s in document["школа"]["источники"]}
    sids=st.multiselect("Источник", list(source_options), format_func=lambda x: source_options[x], key="source_schools_people_sources")
    conf=st.slider("Минимальная уверенность",0.0,1.0,0.0,0.05,key="source_schools_people_confidence")
    filtered=filter_people_dataframe(df, query=q, categories=cats, roles=roles, groups=groups, source_ids=sids, minimum_confidence=conf)
    st.write(f"Найдено представителей: {len(filtered)}")
    if filtered.empty: st.info("По заданным условиям представители не найдены."); return
    st.dataframe(filtered.drop(columns=["ID","Идентификаторы источников"]), hide_index=True, use_container_width=True)
    labels=dict(zip(filtered["ID"], filtered["Представитель"])); pid=st.selectbox("Карточка представителя", list(labels), format_func=lambda x: labels[x], key="source_schools_person_card")
    p=indexes["persons"][pid]; st.markdown(f"### {p.get('полное_имя')}");
    for label,key in [("Годы жизни","годы_жизни"),("Категория включения как систематизация","категория_включения"),("Роли","роль_в_школе"),("Связь с Выготским","статус_связи_с_выготским"),("Период взаимодействия","период_взаимодействия"),("Группы и контексты","группы_и_контексты"),("Основной вклад","основной_вклад"),("Уверенность","уверенность")]: st.write(f"**{label}:** {p.get(key,'') if not isinstance(p.get(key),list) else '; '.join(p.get(key))}")
    st.markdown("#### Источниковые атрибуции")
    for a in p.get("источниковые_атрибуции",[]):
        src=indexes["sources"][a["идентификатор_источника"]]; ev=indexes["evidence"][a["подтверждение"]]
        st.write(f"**{_source_label(src)}:** {a.get('формулировка_роли')} / систематизация: {a.get('нормализованная_роль')} — {_evidence_status(a.get('явное_утверждение'))}. Подтверждение: {ev.get('содержание_свидетельства')} ({ev.get('локатор')}).")

def render_groups_and_chronology_section(document, indexes) -> None:
    """Отрисовывает группы, направления, поколения и хронологию."""
    s=document["школа"]; st.subheader("Исследовательские группы")
    for g in s["внутренняя_структура"].get("исследовательские_группы",[]):
        with st.expander(g.get("название","Группа")): st.write(f"Период: {g.get('период','')}"); st.write("Участники: "+"; ".join(resolve_person_names(g.get("участники",[]), indexes["persons"]))); st.write("Подтверждения: "+"; ".join(g.get("подтверждения",[])))
    st.subheader("Направления и поколения"); st.write(s["внутренняя_структура"].get("направления",[])); st.write(s["внутренняя_структура"].get("поколения",[])); st.subheader("Периоды развития"); st.write(s.get("хронология",{}).get("периоды_развития",[]))

def render_ideas_and_directions_section(document, indexes) -> None:
    """Отрисовывает идеи и направления."""
    s=document["школа"]; ideas=s.get("идеи_и_направления",{}); st.write(f"**Основная идея:** {s.get('основная_идея','')}")
    for k,l in [("теоретические_основания","Теоретические основания"),("ключевые_понятия","Ключевые понятия"),("теории","Теории"),("методы","Методы"),("интеллектуальные_источники","Интеллектуальные источники"),("основные_результаты","Основные результаты"),("связанные_школы","Связанные школы")]: st.write(f"**{l}:** {'; '.join(ideas.get(k,[]))}")
    for d in s["внутренняя_структура"].get("направления",[]):
        with st.expander(d.get("название","Направление")): st.write(d.get("описание","")); st.write("Представители: "+"; ".join(resolve_person_names(d.get("представители",[]), indexes["persons"]))); st.write("Подтверждения: "+"; ".join(d.get("подтверждения",[])))

def render_sources_and_evidence_section(document, indexes) -> None:
    """Отрисовывает источники и подтверждения."""
    st.dataframe(build_sources_dataframe(document).drop(columns=["ID"]), hide_index=True, use_container_width=True)
    for s in document["школа"]["источники"]:
        with st.expander(_source_label(s)): st.write(s.get("библиографическое_описание",""));
        if _safe_url(s.get("url")): st.link_button("Открыть источник", s["url"])
        if s.get("дата_обращения"): st.caption(f"Дата обращения: {s['дата_обращения']}")
    evdf=build_evidence_dataframe(document); srcs=st.multiselect("Источник подтверждения", sorted(evdf["Источник"].unique()), key="source_schools_evidence_sources"); types=st.multiselect("Тип утверждения", sorted(evdf["Тип утверждения"].unique()), key="source_schools_evidence_types"); statuses=st.multiselect("Статус утверждения", ["Явное утверждение","Интерпретация"], key="source_schools_evidence_status")
    f=evdf.copy();
    if srcs: f=f[f["Источник"].isin(srcs)]
    if types: f=f[f["Тип утверждения"].isin(types)]
    if statuses: f=f[f["Статус"].isin(statuses)]
    st.dataframe(f.drop(columns=["ID"]), hide_index=True, use_container_width=True)
    for _,r in f.iterrows():
        with st.expander(str(r["Содержание свидетельства"])[:80]): st.write(r.to_dict())

def render_disagreements_and_quality_section(document, indexes) -> None:
    """Отрисовывает расхождения и качество данных."""
    s=document["школа"]; q=document["контроль_качества"]
    for d in s.get("историографические_расхождения",[]):
        with st.expander(d.get("вопрос","Расхождение")):
            for p in d.get("позиции",[]): st.write(f"Источникозависимая интерпретация: {p.get('формулировка')} Источники: {'; '.join(_source_label(indexes['sources'][x]) for x in p.get('источники',[]) if x in indexes['sources'])}")
    st.subheader("Качество данных")
    for k,v in q.get("проверки",{}).items(): (st.success if v else st.warning)(f"{k}: {'да' if v else 'требует проверки'}")
    st.write("Недостаточно сведений: "+"; ".join(q.get("недостаточно_сведений",[]))); st.write("Интерпретативные выводы: "+"; ".join(q.get("интерпретативные_выводы",[]))); st.write("Примечания: "+"; ".join(q.get("примечания",[]))); st.write(q.get("метаданные_извлечения",{}))
    with st.expander("Кандидаты для дальнейшего расширения данных"):
        st.caption("Эти персоны или группы пока не входят в проверенный основной список."); st.write(s.get("кандидаты_на_расширение",[]))
