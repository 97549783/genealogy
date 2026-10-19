"""Общие представления источниковых школ, их персон и подтверждений."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.source_schools.bibliography import build_numbered_bibliography, build_source_number_index
from core.source_schools.model import (
    MEMBERSHIP_GROUP_LABELS, accepted_information, dimension_definitions, field_definitions, format_locator,
    format_value, included_persons, membership_index, person_basis_ids,
    uses_membership_division,
)
from core.source_schools.tables import (
    build_people_dataframe, build_candidates_dataframe, configured_table_columns,
    filter_people_dataframe, table_column_labels,
)
from core.source_schools.tree import build_source_school_overview_tree
from core.ui.tree_renderers import build_markmap_html

_STATUS = {"сверено":"Сверено с источником", "унаследовано":"Унаследованная сверка", "частично_сверено":"Частично сверено", "не_проверено":"Ещё не проверено", "ошибка":"Требует исправления"}
_NATURE = {"источниковое_сообщение":"Сообщение источника", "авторская_оценка":"Оценка автора", "редакторская_интерпретация":"Редакторская интерпретация", "источниковое_отнесение":"Отнесение в источнике", "классификационная_интерпретация":"Редакторское отнесение"}
_MEMBERSHIP = {"представитель":"Представитель", "связанное_лицо":"Связанное лицо", "не_установлено":"Характер связи не установлен"}
_DECISION = {"включено":"Включён в описание", "кандидат":"Кандидат на включение", "исключено":"Не включён в рабочий состав", "принято":"Принято", "гипотеза":"Гипотеза", "отклонено":"Отклонено"}


def _safe_url(url: object) -> bool:
    from core.source_schools.links import _safe_link_url
    return isinstance(url,str) and bool(_safe_link_url(url,allow_relative=True))


def _anchor(text: str, link: Mapping[str, str] | str | None) -> str:
    href = link.get("href", "") if isinstance(link, Mapping) else str(link or "")
    if not _safe_url(href):
        return escape(text)
    title = link.get("title", text) if isinstance(link, Mapping) else text
    return f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer" title="{escape(title, quote=True)}">{escape(text)}</a>'


def _tree_icon(link: Mapping[str, str] | None) -> str:
    if not link or not _safe_url(link.get("href")):
        return ""
    from core.source_schools.links import tree_icon_link
    return tree_icon_link(link["href"], link.get("title", "Открыть дерево научного руководства"))


def _basis_ids(document, record):
    assertions = {r["id"]:r for key in ("сведения", "связи") for r in document[key]}
    result, visited = set(), set()
    def collect(item):
        result.update(item.get("основания", []))
        for ident in item.get("опирается_на", []):
            if ident in assertions and ident not in visited:
                visited.add(ident); collect(assertions[ident])
    collect(record)
    return result


def _basis_note(document, ids):
    numbers = build_source_number_index(document)
    result = []
    for basis in document["основания"]:
        if basis["id"] in ids:
            number = numbers[basis["источник"]]
            locator = format_locator(basis.get("локатор"))
            label = f"Источник № {number}" + (f", {locator}" if locator else ", место не уточнено")
            if label not in result:result.append(label)
    return "; ".join(result)


def _render_record(document, record, *, show_label=False):
    definition = field_definitions(document).get(record.get("поле"), {})
    if show_label:st.markdown("**" + definition.get("название", "Сведения") + "**")
    st.write(format_value(record.get("значение")))
    labels = [_NATURE.get(record.get("характер"), ""), _STATUS.get(record.get("проверка", {}).get("статус"), "")]
    if record.get("роль_значения") == "вариант":labels.insert(0,"Альтернативный вариант")
    note = _basis_note(document, _basis_ids(document,record))
    st.caption(" · ".join(x for x in labels if x) + (". " + note if note else ". Источниковая опора пока не уточнена."))
    for warning in record.get("ограничения", []):st.caption(warning)


def _render_school_description(document):
    school=document["школа"]
    st.write(school["границы_описания"])
    if school["альтернативные_названия"]:
        with st.expander("Альтернативные названия"):
            for item in school["альтернативные_названия"]:
                st.write(item["написание"])
                if item.get("примечание"):st.caption(item["примечание"])
    st.caption("Дисциплины: " + "; ".join(school["дисциплины"]))
    st.caption("Страны деятельности: " + (", ".join(x["название"] for x in school["страны"]) or "Пока не размечены"))
    st.caption("Языки описания: " + ", ".join(document["метаданные"]["языки_данных"]))
    if school["языки_работ"]:
        with st.expander("Языки работ школы"):
            roles={"язык_оригиналов":"Оригиналы", "язык_переводов":"Переводы", "язык_работ_не_уточнён":"Оригинал или перевод пока не уточнён"}
            for tag in school["языки_работ"]:
                st.markdown(f"**{tag['название']}** · {roles[tag['роль']]}")
                st.write(tag["охват"])
                st.caption(_basis_note(document,tag["основания"]))
    with st.expander("Паспорт школы", expanded=False):
        for record in accepted_information(document,school["идентификатор_школы"]):
            _render_record(document,record,show_label=True)


def _filters(document, dataframe, *, scope="overview"):
    sid=document["школа"]["идентификатор_школы"]
    prefix=f"source_schools_{sid}_{scope}"
    query=st.text_input("Поиск по представителям",key=prefix+"_query")
    facets=dimension_definitions(document,include_primary=False)
    selections={}
    columns=st.columns(min(3,max(1,len(facets))))
    for n,(fid,definition) in enumerate(facets.items()):
        labels={v["id"]:v["название"] for v in definition["значения"]}
        with columns[n%len(columns)]:
            selections[fid]=st.multiselect(definition["название"],list(labels),format_func=labels.get,key=prefix+"_facet_"+fid,help=definition["описание"])
    primary=document["классификации"]["основное_деление"]
    selected_primary=[]
    selected_membership=[]
    if primary:
        labels={c["id"]:c["название"] for c in primary["категории"]}
        selected_primary=st.multiselect(primary["название"],list(labels),format_func=labels.get,key=prefix+"_primary")
    elif uses_membership_division(document):
        displayed=set(dataframe["id"])
        present={m["отношение_к_школе"] for m in document["состав"] if m["персона"] in displayed}
        labels={key:label for key,label in MEMBERSHIP_GROUP_LABELS.items() if key in present}
        selected_membership=st.multiselect("Отношение к школе",list(labels),format_func=labels.get,key=prefix+"_membership",
            help="Взаимоисключающие группы из реестра состава. Отбор по ним ограничивает поиск и гибкие фильтры.")
    mode=st.radio("Логика сочетания измерений",["intersection","union"],
        format_func=lambda v:{"intersection":"И — пересечение","union":"ИЛИ — объединение"}[v],
        index=0 if document["отображение"]["логика_между_фильтрами_по_умолчанию"]=="И" else 1,
        horizontal=True,key=prefix+"_logic")
    treatment=st.radio("Режим отображения",["highlight","hide"],
        format_func=lambda v:{"highlight":"Подсветить совпадения","hide":"Скрыть несовпадающих"}[v],
        index=0 if document["отображение"]["режим_отбора_по_умолчанию"]=="подсветка" else 1,
        horizontal=True,key=prefix+"_treatment")
    subset=filter_people_dataframe(dataframe,query=query,facet_selections=selections,primary_categories=selected_primary,
        membership_types=selected_membership,mode=mode)
    active=bool(query.strip() or selected_primary or selected_membership or any(selections.values()))
    st.caption(f"Совпало персон: {len(subset)} из {len(dataframe)}. Внутри измерения — ИЛИ; между активными измерениями — {'пересечение' if mode=='intersection' else 'объединение'}.")
    if not active:st.caption("Пока выбор пуст, дерево показано полностью.")
    return subset,active,treatment


def _table_html(dataframe,columns,labels,person_links,lineage_links,highlighted_ids=None):
    headers="".join('<th scope="col">'+escape(labels.get(c,c))+'</th>' for c in columns)
    rows=[]
    for _,row in dataframe.iterrows():
        pid=str(row["id"]);cells=[]
        for column in columns:
            if column=="Имя":
                value=_anchor(str(row[column]),person_links.get(pid))+" "+_tree_icon(lineage_links.get(pid))
            else:
                raw=row.get(column,"")
                value=escape("" if raw is None or (isinstance(raw,float) and pd.isna(raw)) else str(raw)).replace("\n","<br>")
            cells.append("<td>"+value+"</td>")
        css=' class="source-schools-match"' if highlighted_ids is not None and pid in highlighted_ids else ""
        rows.append("<tr"+css+">"+"".join(cells)+"</tr>")
    return '<div class="source-schools-table-scroll"><table class="source-schools-table"><thead><tr>'+headers+'</tr></thead><tbody>'+"".join(rows)+'</tbody></table></div>'


def _render_table(document,dataframe,*,person_links,lineage_links,highlighted_ids=None,scope="overview"):
    sid=document["школа"]["идентификатор_школы"];prefix=f"source_schools_{sid}_{scope}_table"
    labels=table_column_labels(document)
    options=[c for c in labels if c in dataframe.columns and c not in {"id","Имя","Идентификаторы источников","Уверенность"}]
    defaults=[c for c in configured_table_columns(document) if c in options]
    if "Отношение к школе" not in defaults:defaults.insert(0,"Отношение к школе")
    selected=st.multiselect("Столбцы таблицы",options,default=defaults,format_func=labels.get,key=prefix+"_columns")
    columns=["Имя",*selected]
    a,b,c=st.columns([2,1,1])
    with a:order=st.selectbox("Сортировать по",columns,format_func=labels.get,key=prefix+"_sort")
    with b:descending=st.checkbox("По убыванию",key=prefix+"_descending")
    with c:size=st.selectbox("Строк на странице",["all",25,50,100,500],
        format_func=lambda value:"Все строки" if value=="all" else str(value),key=prefix+"_row_limit")
    ordered=dataframe.sort_values(order,ascending=not descending,kind="stable",na_position="last")
    signature=tuple(ordered["id"])
    if st.session_state.get(prefix+"_signature")!=signature:
        st.session_state[prefix+"_page"]=1;st.session_state[prefix+"_signature"]=signature
    if size=="all":
        chunk=ordered
        table_note=f"Показаны все строки; строк в выборке: {len(ordered)}."
    else:
        pages=max(1,(len(ordered)+size-1)//size)
        if st.session_state.get(prefix+"_page",1)>pages:st.session_state[prefix+"_page"]=1
        page=st.number_input("Страница таблицы",min_value=1,max_value=pages,step=1,key=prefix+"_page")
        chunk=ordered.iloc[(page-1)*size:page*size]
        table_note=f"Страница {page} из {pages}; строк в выборке: {len(ordered)}."
    st.markdown('''<style>
.source-schools-table-scroll {overflow-x:auto;max-width:100%;margin:0.5rem 0 1rem}
.source-schools-table {border-collapse:collapse;width:100%;font-size:0.92rem}
.source-schools-table th,.source-schools-table td {border:1px solid #a9b4bf66;padding:.5rem .65rem;text-align:left;vertical-align:top;min-width:9rem;max-width:32rem;overflow-wrap:anywhere}
.source-schools-table th {background:#80808018;white-space:nowrap}
.source-schools-table .source-schools-match {background:#ffab4030}
.source-schools-table a {text-decoration:underline}
.source-school-tree-link {display:inline-flex;vertical-align:middle;margin-left:.3rem}
</style>'''+_table_html(chunk,columns,labels,person_links,lineage_links,highlighted_ids),unsafe_allow_html=True)
    st.caption(table_note+" Имя открывает карточку школы, значок дерева — научное руководство. Обе ссылки открываются в новой вкладке.")
    from core.source_schools.export import build_filtered_people_csv,build_filtered_people_xlsx
    export=ordered[[c for c in ["id",*columns] if c in ordered]].rename(columns=labels)
    left,right=st.columns(2)
    with left:st.download_button("Скачать таблицу CSV",build_filtered_people_csv(export),file_name=sid+".выборка.csv",mime="text/csv",key=prefix+"_csv")
    with right:st.download_button("Скачать таблицу Excel",build_filtered_people_xlsx(export),file_name=sid+".выборка.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key=prefix+"_xlsx")


def render_overview_section(document,indexes,*,lineage_links=None,person_links=None,school_link=None,presentation="tree"):
    lineage_links=lineage_links or {};person_links=person_links or {}
    people=build_people_dataframe(document)
    selected,active,treatment=_filters(document,people)
    selected_ids=set(selected["id"])
    hidden=set(people["id"])-selected_ids if active and treatment=="hide" else None
    if presentation in {"tree","together"}:
        st.subheader("Структура школы")
        mode=st.radio("Режим ветвления",["Одностороннее ветвление","Двустороннее ветвление"],
            horizontal=True,key="source_schools_tree_branching_"+document["школа"]["идентификатор_школы"])
        tree=build_source_school_overview_tree(document,highlighted_person_ids=selected_ids if active else None,
            hidden_person_ids=hidden,lineage_links=lineage_links,person_links=person_links,school_link=school_link)
        markup,height=build_markmap_html(tree.graph,tree.root_id,initial_expand_level=0,
            branching_mode="bidirectional" if mode=="Двустороннее ветвление" else "unidirectional")
        components.html(markup,height=height,scrolling=False)
        st.caption("Клик на кружок узла — свернуть или развернуть ветвь. Имя открывает карточку в новой вкладке, значок дерева — научное руководство. Колёсико мыши — масштаб; перетаскивание — панорама.")
        if active and selected.empty:st.info("По выбранным условиям никто не найден. Структура дерева сохранена.")
    if presentation in {"table","together"}:
        st.subheader("Табличное представление")
        shown=selected if active and treatment=="hide" else people
        _render_table(document,shown,person_links=person_links,lineage_links=lineage_links,
            highlighted_ids=selected_ids if active and treatment=="highlight" else None)
    _render_school_description(document)


def render_person_card(document,indexes,person_id,*,person_links=None,lineage_links=None):
    person_links=person_links or {};lineage_links=lineage_links or {}
    people={p["id"]:p for p in document["объекты"]["персоны"]}
    person=people.get(person_id)
    if person is None:
        st.warning("Персона с таким идентификатором в выбранной школе не найдена.")
        return False
    st.subheader(person["имя"])
    st.caption("Карточка в школе: "+document["школа"]["каноническое_название"])
    member=membership_index(document).get(person_id,{})
    st.caption(_DECISION.get(member.get("решение"),"Состав не определён")+" · "+_MEMBERSHIP.get(member.get("отношение_к_школе"),""))
    identification=person.get("идентификация",{})
    if identification.get("статус")!="установлена":st.warning("Идентификация: "+identification.get("статус","не установлена").replace("_"," "))
    if person.get("варианты_имени"):st.write("Другие написания: "+"; ".join(a["написание"] for a in person["варианты_имени"]))
    if person.get("примечание"):st.write(person["примечание"])
    link=_anchor("Открыть отдельную карточку ↗",person_links.get(person_id))
    icon=_tree_icon(lineage_links.get(person_id))
    st.markdown(link+(" · "+icon+" Научное руководство" if icon else ""),unsafe_allow_html=True)
    if not icon:st.caption("Дерево научного руководства для этой персоны пока не сопоставлено с базой.")
    tabs=st.tabs(["Сведения","Классификации","Связи","Источники и подтверждения","Разночтения"])
    with tabs[0]:
        records=[r for r in accepted_information(document,person_id,include_variants=True)]
        if not records:st.info("Индивидуальные сведения пока не добавлены.")
        for record in records:_render_record(document,record,show_label=True)
    with tabs[1]:
        defs=dimension_definitions(document)
        assignments=[a for a in document["классификационные_назначения"] if a["персона"]==person_id]
        if not assignments:st.info("Классификационные отнесения пока отсутствуют.")
        for a in assignments:
            definition=defs[a["измерение"]]
            values={v["id"]:v["название"] for v in definition.get("значения",definition.get("категории",[]))}
            st.markdown("**"+definition["название"]+"**: "+values[a["значение"]])
            st.caption(_DECISION[a["решение"]]+" · "+_NATURE[a["характер"]]+" · "+_STATUS[a["проверка"]["статус"]])
            if a.get("интервалы"):st.write("; ".join(format_value({"вид":"интервал","значение":i}) for i in a["интервалы"]))
            st.caption(_basis_note(document,_basis_ids(document,a)))
            if a.get("примечание"):st.write(a["примечание"])
    with tabs[2]:
        entities={**people,**{o["id"]:o for o in document["объекты"]["прочие"]},document["школа"]["идентификатор_школы"]:document["школа"]}
        labels={x["код"]:x["название"] for x in document["словари"]["типы_связей"]}
        relations=[r for r in document["связи"] if person_id in (r["от"],r["к"]) and r["решение"]=="принято"]
        if not relations:st.info("Индивидуальные отношения пока не добавлены.")
        for r in relations:
            def entity(ident):
                item=entities[ident];name=item.get("имя") or item.get("название") or item.get("каноническое_название","")
                return _anchor(name,person_links.get(ident))
            st.markdown(entity(r["от"])+" → "+escape(labels[r["тип"]])+" → "+entity(r["к"]),unsafe_allow_html=True)
            if r.get("формулировка_источника"):st.write(r["формулировка_источника"])
            if r.get("нормализованная_роль"):st.caption(r["нормализованная_роль"])
            st.caption(_basis_note(document,_basis_ids(document,r)))
    with tabs[3]:
        st.markdown("**Источниковые атрибуции**")
        ids=set(person_basis_ids(document,person_id))
        bases=[b for b in document["основания"] if b["id"] in ids]
        _render_bases(document,bases,key="person_"+person_id)
    with tabs[4]:
        related_records={"персона":{person_id},
            "связь":{r["id"] for r in document["связи"] if person_id in (r["от"],r["к"])},
            "состав":{m["id"] for m in document["состав"] if m["персона"]==person_id},
            "назначение":{a["id"] for a in document["классификационные_назначения"] if a["персона"]==person_id}}
        subjects={person_id,*related_records["связь"]}
        related_records["сведение"]={r["id"] for r in document["сведения"] if r["субъект"] in subjects}
        disagreements=[x for x in document["редактура"]["разночтения"]
            if any(ref["id"] in related_records.get(ref["реестр"],set()) for v in x["варианты"] for ref in v["записи"])]
        if not disagreements:st.info("Адресные разночтения для этой карточки не указаны.")
        for item in disagreements:_render_disagreement(document,item)
    return True


def render_people_section(document,indexes,*,person_links=None,lineage_links=None):
    people=build_people_dataframe(document)
    selected,active,treatment=_filters(document,people,scope="people")
    st.caption(f"Найдено представителей и связанных лиц: {len(selected)}")
    shown=selected if active and treatment=="hide" else people
    _render_table(document,shown,person_links=person_links or {},lineage_links=lineage_links or {},
        highlighted_ids=set(selected["id"]) if active and treatment=="highlight" else None,scope="people")
    candidates=build_candidates_dataframe(document)
    with st.expander(f"Кандидаты на включение ({len(candidates)})"):
        if candidates.empty:st.info("Кандидатов нет.")
        else:_render_table(document,candidates,person_links=person_links or {},lineage_links=lineage_links or {},scope="candidates")
    all_people={p["id"]:p for p in document["объекты"]["персоны"]}
    options=list(selected["id"])
    selected_person=st.selectbox("Карточка персоны",options,index=None,format_func=lambda ident:all_people[ident]["имя"],key="source_schools_card_"+document["школа"]["идентификатор_школы"])
    if selected_person:render_person_card(document,indexes,selected_person,person_links=person_links,lineage_links=lineage_links)


def render_groups_and_chronology_section(document,indexes):
    st.subheader("Исследовательские группы и хронология")
    primary=document["классификации"]["основное_деление"]
    if primary:
        with st.expander(primary["название"]):
            for rule in primary["правила_отнесения"]:st.write(rule)
            for c in primary["категории"]:st.markdown("**"+c["название"]+"**: "+c["критерий"])
    for obj in document["объекты"]["прочие"]:
        if obj["тип"] in {"коллектив","организация","место","период","событие","школа"}:
            with st.expander(obj["название"]):
                st.caption(obj["тип"].capitalize()+" · "+str(obj.get("подтип") or ""))
                if obj.get("примечание"):st.write(obj["примечание"])
                for r in accepted_information(document,obj["id"],include_variants=True):_render_record(document,r,show_label=True)
                st.caption(_basis_note(document,obj["идентификация"]["основания"]))


def _school_idea_records(document):
    """Выбирает содержательные сведения по разделам словаря.

    Стандартные поля задают опорные разделы. Пользовательские поля могут
    относиться к ним либо к разделам идей, теорий, методов и результатов;
    их коды не требуют отдельного толкования для каждой школы.
    """
    definitions=field_definitions(document)
    standard={"main_ideas","contribution","author_assessment"}
    def normalize(label):return " ".join(str(label).casefold().replace("ё","е").replace("_"," ").split())
    stems=("иде","теор","теорет","метод","понят","результ","вклад","оценк","проблем","гипотез",
           "idea","theor","method","concept","result","contribut","assess","problem","hypothes")
    declared=[*document["отображение"].get("разделы_паспорта",[]),
              *(definition.get("раздел","") for definition in definitions.values())]
    sections={normalize(label) for label in declared
              if any(word.startswith(stems) for word in normalize(label).split())}
    sections.update(normalize(definitions[code]["раздел"]) for code in standard if code in definitions)
    sid=document["школа"]["идентификатор_школы"]
    return [record for record in accepted_information(document,sid,include_variants=True)
            if record["поле"] in standard or normalize(definitions[record["поле"]].get("раздел","")) in sections]


def render_ideas_and_directions_section(document,indexes):
    st.subheader("Основная идея и направления")
    for r in _school_idea_records(document):_render_record(document,r,show_label=True)
    for obj in document["объекты"]["прочие"]:
        if obj["тип"] in {"направление","метод","понятие","результат","работа"}:
            with st.expander(obj["название"]):
                st.caption(obj["тип"].capitalize())
                if obj.get("примечание"):st.write(obj["примечание"])
                for r in accepted_information(document,obj["id"],include_variants=True):_render_record(document,r,show_label=True)
                st.caption(_basis_note(document,obj["идентификация"]["основания"]))


def _render_bases(document,bases,*,key):
    if not bases:
        st.info("Адресные подтверждения пока не добавлены.");return
    sources={s["id"]:s for s in document["источники"]}
    numbers=build_source_number_index(document)
    sid=document["школа"]["идентификатор_школы"]
    page_key="source_schools_bases_page_"+sid+"_"+key
    pages=max(1,(len(bases)+19)//20)
    if st.session_state.get(page_key,1)>pages:st.session_state[page_key]=1
    page=st.number_input("Страница подтверждений",min_value=1,max_value=pages,step=1,key=page_key)
    st.caption(f"Подтверждений: {len(bases)}")
    for b in bases[(page-1)*20:page*20]:
        source=sources[b["источник"]]
        with st.expander(f"Источник № {numbers[source['id']]} · {format_locator(b.get('локатор')) or 'Место не уточнено'}"):
            st.write(source["библиографическое_описание"])
            for access in source.get("доступы",[]):
                if _safe_url(access.get("url")):
                    st.markdown(_anchor("Открыть источник ↗ · "+access["назначение"].replace("_"," "),access["url"]),unsafe_allow_html=True)
            st.caption(_STATUS[b["проверка"]["статус"]]+" · "+b["тип_свидетельства"].replace("_"," "))
            fragment=b.get("фрагмент")
            if fragment:
                st.caption({"цитата":"Цитата","пересказ":"Пересказ","сводка":"Сводка"}[fragment["вид"]])
                st.write(fragment["текст"])
            else:st.caption("Источник и локатор указаны; текстовый фрагмент не воспроизведён.")
            for x in b.get("ограничения",[]):st.warning(x)


def render_sources_and_evidence_section(document,indexes):
    st.subheader("Использованные источники")
    for item in build_numbered_bibliography(document):st.write(f"{item['№']}. {item['описание']}")
    st.caption("Дата обращения относится к конкретной ссылке, если она указана в исходных данных.")
    sources={s["id"]:s for s in document["источники"]}
    chosen=st.multiselect("Источник подтверждения",list(sources),format_func=lambda k:sources[k]["название"],key="source_schools_basis_sources_"+document["школа"]["идентификатор_школы"])
    bases=[b for b in document["основания"] if not chosen or b["источник"] in chosen]
    _render_bases(document,bases,key="all")


def _render_disagreement(document,item):
    with st.expander(item["тема"]):
        st.caption(item["статус"].replace("_"," "))
        for variant in item["варианты"]:
            st.write(variant["формулировка"])
            st.caption(_basis_note(document,variant["основания"]))
        if item.get("редакторское_решение"):st.info(item["редакторское_решение"])


def render_disagreements_and_quality_section(document,indexes):
    st.subheader("Качество данных")
    st.caption("Редакционное состояние: "+document["метаданные"]["статус"].replace("_"," "))
    for note in document["редактура"]["ограничения"]:st.warning(note)
    st.subheader("Разночтения")
    for item in document["редактура"]["разночтения"]:_render_disagreement(document,item)
    st.subheader("Классификационные гипотезы")
    people={p["id"]:p["имя"] for p in document["объекты"]["персоны"]}
    for a in document["классификационные_назначения"]:
        if a["решение"]!="гипотеза":continue
        st.write(people[a["персона"]])
        if a.get("примечание"):st.write(a["примечание"])
        st.caption(_basis_note(document,_basis_ids(document,a)))
    with st.expander("Журнал редакторских решений"):
        for item in document["редактура"]["журнал_решений"]:
            st.markdown("**"+item["предмет"]+"**")
            for field,label in [("выявлено","Выявлено"),("принятое_решение","Решение"),("результат","Результат")]:
                if item.get(field):st.write(label+": "+item[field])
