"""Отрисовка внутренних режимов демо-раздела школ по источникам."""
from __future__ import annotations

import io
from typing import Any, Mapping
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components

from core.source_schools.bibliography import build_numbered_bibliography, build_source_number_index
from core.source_schools.export import build_filtered_people_csv, build_filtered_people_xlsx
from core.source_schools.data import normalize_source_school_document
from core.source_schools.dimensions import (
    build_dimension_coverage, build_person_dimension_labels, has_canonical_assignments,
)
from core.source_schools.presentation import as_display_text, as_list, format_life_years, get_first_field
from core.source_schools.tree import (
    build_person_primary_relation_index,
    build_source_school_overview_tree,
    build_supplementary_dimension_catalog,
    combine_supplementary_selections,
)
from core.ui.tree_renderers import build_markmap_html, draw_hierarchical_tree
from core.source_schools.tables import (
    build_evidence_dataframe,
    build_people_dataframe,
    build_sources_dataframe,
    filter_people_dataframe,
    resolve_person_names,
)


def _safe_url(url: str | None) -> bool:
    return bool(url) and urlparse(url).scheme in {"http", "https"}


def _source_label(source: Mapping[str, Any]) -> str:
    return source.get("краткое_название") or source.get("библиографическое_описание", source.get("id", ""))


def _evidence_status(value: Any) -> str:
    return "Явное утверждение" if value else "Интерпретация"


def _evidence_summary(evidence_id: str, indexes: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> str:
    evidence = indexes["evidence"].get(evidence_id)
    if not evidence:
        return "Подтверждение не найдено"
    source = indexes["sources"].get(evidence.get("идентификатор_источника"), {})
    locator = evidence.get("локатор")
    locator_text = f", {locator}" if locator else ""
    result = f"{_source_label(source)} — {evidence.get('содержание_свидетельства', '')}{locator_text}"
    if evidence.get("тип_утверждения"):
        result += f". Вид свидетельства: {as_display_text(evidence['тип_утверждения'])}."
    if evidence.get("ограничения"):
        result += f" Ограничение: {as_display_text(evidence['ограничения'])}"
    return result


def _write_named_list(title: str, value: Any) -> None:
    text = as_display_text(value)
    if text:
        st.write(f"**{title}:** {text}")


def _render_person_source_notes(person: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Показывает варианты и ограничения рядом с утверждениями конкретной персоны."""
    _write_named_list("Примечание", person.get("примечание"))
    for disagreement in person.get("разночтения", []):
        st.write(f"**Разночтение: {disagreement.get('вопрос', '')}**")
        for variant in disagreement.get("варианты", []):
            sources = "; ".join(
                _source_label(indexes["sources"][source_id])
                for source_id in variant.get("источники", [])
                if source_id in indexes["sources"]
            )
            st.write(f"{variant.get('значение', '')} — {sources}; {variant.get('локатор', '')}.")
        _write_named_list("Ограничение вывода", disagreement.get("ограничение"))
    for limitation in dict.fromkeys(person.get("источниковые_ограничения", [])):
        _write_named_list("Источниковое ограничение", limitation)


def _render_assignment_status_note(document: Mapping[str, Any], dimension: str, value_id: str) -> None:
    """Показывает статус членства отдельно от описания исторической группы."""
    if not has_canonical_assignments(document):
        return
    counts = {"подтверждено": 0, "интерпретация": 0, "не_проверено": 0}
    for item in document["школа"]["классификационные_назначения"]:
        if item.get("измерение") == dimension and item.get("значение") == value_id:
            counts[item["статус"]] += 1
    st.caption(
        f"Подтверждено: {counts['подтверждено']}; классификационные интерпретации: {counts['интерпретация']}; "
        f"непроверенные назначения: {counts['не_проверено']} (в основной список не включены). "
        "Основания каждого назначения доступны в карточке персоны."
    )


def _supplementary_value_label(value_id: str, values: Mapping[str, Any], *, show_count: bool) -> str:
    """Безопасно форматирует значение, даже если каталог обновился в живой сессии."""
    value = values.get(value_id)
    if value is None:
        return "Значение отсутствует в текущем каталоге"
    return f"{value.label} ({len(value.person_ids)})" if show_count else value.label


def _render_school_description(school: Mapping[str, Any]) -> None:
    """Отрисовывает описательную часть обзора под интерактивным графом."""
    _write_named_list("Тип школы", school.get("тип_школы"))
    st.caption(as_display_text(school.get("примечание_к_типу")))
    disciplines = school.get("дисциплинарная_принадлежность", {})
    main_idea = school.get("основная_идея", {})
    chronology = school.get("хронология", {})
    _write_named_list(
        "Дисциплинарные области",
        get_first_field(disciplines, "области", default=school.get("дисциплинарные_области")),
    )
    _write_named_list(
        "Ключевые слова",
        get_first_field(disciplines, "ключевые_слова", default=school.get("ключевые_слова")),
    )
    _write_named_list("Основная идея", main_idea)
    _write_named_list(
        "Проблема",
        get_first_field(main_idea, "центральная_проблема", default=school.get("проблема")),
    )
    _write_named_list(
        "Гипотеза",
        get_first_field(main_idea, "центральная_гипотеза", default=school.get("гипотеза")),
    )
    _write_named_list(
        "Теория",
        get_first_field(main_idea, "центральная_теория", default=school.get("теория")),
    )
    _write_named_list(
        "Метод",
        get_first_field(main_idea, "центральный_метод", default=school.get("метод")),
    )
    _write_named_list(
        "Хронология",
        get_first_field(
            chronology,
            "кратко",
            "общий_период",
            "описание",
            "дата_или_период_возникновения",
            "период_активности",
            "период_расцвета",
            "примечание_о_неопределенности_хронологии",
        ),
    )
    _write_named_list("География", school.get("география"))
    _write_named_list("Организации", school.get("организации"))


def render_overview_section(document: Mapping[str, Any], indexes: Mapping[str, Any], *, lineage_links=None) -> None:
    """Отрисовывает обзор школы."""
    school = document["школа"]
    demo = document["демо_представление"]
    st.subheader(demo["заголовок_страницы"])
    st.caption(demo["подзаголовок"])
    col_people, col_sources, col_evidence = st.columns(3)
    col_people.metric("Представители", len(school["персоны"]))
    col_sources.metric("Источники", len(school["источники"]))
    col_evidence.metric("Подтверждения", len(school["подтверждения"]))
    _write_named_list("Каноническое название", school.get("каноническое_название"))
    with st.expander("Альтернативные названия", expanded=False):
        for alternative in school.get("альтернативные_названия", []):
            st.write(
                f"{as_display_text(alternative.get('название'))} — "
                f"{as_display_text(get_first_field(alternative, 'примечание', 'примечание_об_источнике_названия'))}"
            )
    st.subheader("Структура школы")
    canonical = has_canonical_assignments(document)
    if canonical:
        st.caption(
            "Фильтры учитывают подтверждённые назначения и классификационные интерпретации с источниковым основанием. "
            "Название периода или направления может быть редакторским: источник подтверждает основание назначения, "
            "а не обязательно точную формулировку фильтра. Спорные гипотезы сохранены в разделе расхождений и в выборки не включаются. "
            "Отсутствие разметки не означает отсутствие исторической связи."
        )
    catalog = build_supplementary_dimension_catalog(document)
    coverage = build_dimension_coverage(document)
    dimension_specs = (
        ("historical_group", "Исторические группы и контексты" if canonical else "Исторические группы"),
        ("period", "Периоды"),
        ("research_direction", "Научные направления"),
    )
    selections: dict[str, list[str]] = {}
    dimension_columns = st.columns(3)
    for column, (dimension_id, label) in zip(dimension_columns, dimension_specs, strict=True):
        values = catalog.get(dimension_id, ())
        value_by_id = {value.id: value for value in values}
        widget_key = f"source_schools_supplementary_{dimension_id}"
        if widget_key in st.session_state:
            st.session_state[widget_key] = [item for item in st.session_state[widget_key] if item in value_by_id]
        with column:
            selections[dimension_id] = st.multiselect(
                label,
                list(value_by_id),
                format_func=lambda value_id, value_by_id=value_by_id: _supplementary_value_label(
                    value_id, value_by_id, show_count=canonical,
                ),
                key=widget_key,
            )
            if canonical:
                stats = coverage[dimension_id]
                st.caption(
                    f"Размечено: {stats['assigned_person_count']} из {len(school['персоны'])}; "
                    f"без разметки: {len(stats['unclassified_person_ids'])}; "
                    f"с классификационными интерпретациями: {len(stats['interpretative_person_ids'])}; "
                    f"с непроверенными назначениями: {len(stats['unverified_person_ids'])}."
                )
    active_dimension_count = sum(bool(values) for values in selections.values())
    composition_mode = st.radio(
        "Логика сочетания измерений",
        ["intersection", "union"],
        format_func=lambda value: (
            "Пересечение (И): персона должна соответствовать каждому выбранному измерению"
            if value == "intersection"
            else "Объединение (ИЛИ): достаточно соответствия любому выбранному измерению"
        ),
        horizontal=True,
        disabled=active_dimension_count < 2,
        key="source_schools_supplementary_composition",
    )
    display_mode = st.radio(
        "Режим отображения",
        ["highlight", "hide"],
        format_func=lambda value: (
            "Подсветить выбранное, остальное затенить"
            if value == "highlight"
            else "Скрыть остальное"
        ),
        horizontal=True,
        key="source_schools_supplementary_display_mode",
    )
    highlighted_person_ids = combine_supplementary_selections(
        catalog,
        selections,
        mode=composition_mode,
    )
    hidden_person_ids: set[str] | None = None
    if highlighted_person_ids is not None and display_mode == "hide":
        all_person_ids = {str(person.get("id")) for person in school.get("персоны", [])}
        hidden_person_ids = all_person_ids - highlighted_person_ids
    if highlighted_person_ids is None:
        st.caption(
            "Четыре типа связи задают положение узлов. В каждом дополнительном измерении можно выбрать несколько значений; "
            "пока выбор пуст, дерево показано полностью."
        )
    else:
        composition_label = "пересечение" if composition_mode == "intersection" and active_dimension_count > 1 else "объединение"
        action_label = "видимыми оставлены" if display_mode == "hide" else "подсвечены оранжевым"
        st.caption(
            f"{action_label.capitalize()} {len(highlighted_person_ids)} персон; внутри каждого измерения действует объединение, "
            f"между активными измерениями — {composition_label}. Структура и порядок типов связи не меняются."
        )
        if not highlighted_person_ids:
            st.warning("Выбранная комбинация не содержит общих персон. Измените значения или выберите объединение (ИЛИ).")
    mode = st.radio(
        "Режим ветвления",
        ["Одностороннее ветвление", "Двустороннее ветвление"],
        horizontal=True,
        key="source_schools_tree_branching",
    )
    tree = build_source_school_overview_tree(
        document,
        highlighted_person_ids=highlighted_person_ids,
        hidden_person_ids=hidden_person_ids,
        lineage_links=lineage_links,
    )
    html, height = build_markmap_html(
        tree.graph,
        tree.root_id,
        initial_expand_level=0,
        branching_mode=("bidirectional" if mode == "Двустороннее ветвление" else "unidirectional"),
    )
    components.html(html, height=height, scrolling=False)
    st.caption("Клик на кружок узла — свернуть или развернуть ветвь. Подчёркнутое имя — открыть дерево научного руководства в новой вкладке. Колёсико мыши — масштаб; перетаскивание — панорама.")
    st.warning(
        "Тип связи — аналитическая систематизация по характеру непосредственной связи с Выготским. "
        "Она не создаёт неподтверждённых отношений научного руководства; источниковые формулировки сохранены в карточках персон."
    )
    figure = draw_hierarchical_tree(tree.graph, tree.root_id, title="Структура школы")
    png_buffer = io.BytesIO()
    figure.savefig(png_buffer, format="png", dpi=180, bbox_inches="tight")
    st.download_button("Скачать дерево в PNG", png_buffer.getvalue(), file_name="vygotsky_cultural_historical_school.дерево.png", mime="image/png", key="source_schools_tree_png")
    st.download_button("Скачать интерактивное дерево в HTML", html.encode("utf-8"), file_name="vygotsky_cultural_historical_school.интерактивное_дерево.html", mime="text/html", key="source_schools_tree_html")
    _render_school_description(school)


def render_people_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает состав школы с фильтрами и карточкой персоны."""
    st.warning(document["демо_представление"]["методологическое_предупреждение"])
    dataframe = build_people_dataframe(document)
    query = st.text_input("Поиск по представителям", key="source_schools_people_query")
    relation_types = st.multiselect(
        "Тип связи с Выготским",
        sorted(value for value in dataframe["Тип связи"].dropna().unique() if value),
        key="source_schools_people_relation_types",
    )
    roles = st.multiselect(
        "Роль в школе",
        sorted({role for value in dataframe["Роли"] for role in str(value).split("; ") if role}),
        key="source_schools_people_roles",
    )
    groups = st.multiselect(
        "Группа или контекст",
        sorted({group for value in dataframe["Группы и контексты"] for group in str(value).split("; ") if group}),
        key="source_schools_people_groups",
    )
    source_options = {source["id"]: _source_label(source) for source in document["школа"]["источники"]}
    source_ids = st.multiselect(
        "Источник",
        list(source_options),
        format_func=lambda source_id: source_options[source_id],
        key="source_schools_people_sources",
    )
    minimum_confidence = st.slider(
        "Минимальная уверенность",
        0.0,
        1.0,
        0.0,
        0.05,
        key="source_schools_people_confidence",
    )
    filtered = filter_people_dataframe(
        dataframe,
        query=query,
        relation_types=relation_types,
        roles=roles,
        groups=groups,
        source_ids=source_ids,
        minimum_confidence=minimum_confidence,
    )
    st.write(f"Найдено представителей: {len(filtered)}")
    if filtered.empty:
        st.info("По заданным условиям представители не найдены.")
        return
    export_view = filtered.drop(columns=["ID", "Идентификаторы источников"])
    col_csv, col_xlsx = st.columns(2)
    col_csv.download_button("Скачать выбранных представителей в CSV", build_filtered_people_csv(export_view), file_name="vygotsky_cultural_historical_school.представители_выборка.csv", mime="text/csv", key="source_schools_people_export_csv")
    col_xlsx.download_button("Скачать выбранных представителей в Excel", build_filtered_people_xlsx(export_view), file_name="vygotsky_cultural_historical_school.представители_выборка.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="source_schools_people_export_xlsx")
    st.dataframe(
        export_view,
        hide_index=True,
        use_container_width=True,
        height=600,
        column_config={
            "Представитель": st.column_config.TextColumn(width="medium"),
            "Годы жизни": st.column_config.TextColumn(width="small"),
            "Тип связи": st.column_config.TextColumn(width="medium"),
            "Категория": st.column_config.TextColumn(width="small"),
            "Роли": st.column_config.TextColumn(width="medium"),
            "Связь с Выготским": st.column_config.TextColumn(width="medium"),
            "Период взаимодействия": st.column_config.TextColumn(width="small"),
            "Группы и контексты": st.column_config.TextColumn(width="medium"),
            "Основной вклад": st.column_config.TextColumn(width="large"),
            "Разночтения и ограничения": st.column_config.TextColumn(width="large"),
            "Уверенность": st.column_config.NumberColumn(format="%.2f"),
            "Число источников": st.column_config.NumberColumn(width="small", format="%d"),
        },
    )
    labels = dict(zip(filtered["ID"], filtered["Представитель"], strict=False))
    person_id = st.selectbox(
        "Карточка представителя",
        list(labels),
        format_func=lambda selected_id: labels[selected_id],
        key="source_schools_person_card",
    )
    person = indexes["persons"][person_id]
    st.markdown(f"### {get_first_field(person, 'полное_имя', 'имя')}")
    _write_named_list("Годы жизни", format_life_years(get_first_field(person, "годы_жизни", "даты")))
    _write_named_list("Тип связи с Выготским", build_person_primary_relation_index(document).get(person_id))
    _write_named_list("Категория включения как систематизация", person.get("категория_включения"))
    _write_named_list("Роли", person.get("роль_в_школе"))
    _write_named_list("Связь с Выготским", person.get("статус_связи_с_выготским"))
    _write_named_list("Период взаимодействия", person.get("период_взаимодействия"))
    _render_person_source_notes(person, indexes)
    if has_canonical_assignments(document):
        classifications = build_person_dimension_labels(document)[str(person_id)]
        for dimension, title in (("historical_group", "Группы и контексты"), ("period", "Периоды развития"), ("research_direction", "Научные направления")):
            _write_named_list(title, classifications[dimension] or ["Не размечено / недостаточно источниковых данных"])
        st.markdown("#### Основания классификационных назначений")
        value_labels = {
            (dimension, value.id.split(":", 1)[1]): value.label
            for dimension, values in build_supplementary_dimension_catalog(document).items() for value in values
        }
        for assignment in document["школа"]["классификационные_назначения"]:
            if assignment.get("персона") != person_id:
                continue
            status_label = {
                "подтверждено": "подтверждено",
                "интерпретация": "редакторская или классификационная интерпретация",
                "не_проверено": "не проверено",
            }[assignment["статус"]]
            st.write(f"**{value_labels.get((assignment['измерение'], assignment['значение']), assignment['значение'])}:** {status_label}.")
            _write_named_list("Примечание", assignment.get("примечание"))
            for attribution in assignment.get("источниковые_атрибуции", []):
                source = indexes["sources"].get(attribution.get("идентификатор_источника"), {})
                st.write(f"{_source_label(source)}; {attribution.get('локатор', '')}. {attribution.get('утверждение', '')}")
                if attribution.get("подтверждение"):
                    st.write(_evidence_summary(attribution["подтверждение"], indexes))
    else:
        _write_named_list("Группы и контексты", person.get("группы_и_контексты"))
    _write_named_list("Основной вклад", get_first_field(person, "основной_вклад", "основные_идеи_или_вклад"))
    _write_named_list("Уверенность", person.get("уверенность"))
    st.markdown("#### Источниковые атрибуции")
    for attribution in person.get("источниковые_атрибуции", []):
        source_number = build_source_number_index(document).get(attribution["идентификатор_источника"], "?")
        source = indexes["sources"][attribution["идентификатор_источника"]]
        evidence = indexes["evidence"][attribution["подтверждение"]]
        st.write(
            f"**[{source_number}] {_source_label(source)}:** {attribution.get('формулировка_роли')} / "
            f"систематизация: {attribution.get('нормализованная_роль')} — "
            f"{_evidence_status(attribution.get('явное_утверждение'))}. "
            f"Подтверждение: {evidence.get('содержание_свидетельства')} ({evidence.get('локатор')})."
        )


def render_groups_and_chronology_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает группы, направления, поколения и хронологию."""
    school = normalize_source_school_document(document)["школа"]
    structure = school["внутренняя_структура"]
    st.subheader("Исследовательские группы")
    for group in structure.get("исследовательские_группы", []):
        with st.expander(as_display_text(group.get("название", "Группа"))):
            _write_named_list("Период", group.get("период"))
            st.write("**Участники:** " + "; ".join(resolve_person_names(group.get("участники", []), indexes["persons"])))
            _render_assignment_status_note(document, "historical_group", str(group.get("id")))
            for evidence_id in group.get("подтверждения", []):
                st.write(_evidence_summary(evidence_id, indexes))
    st.subheader("Направления")
    for direction in structure.get("направления", []):
        with st.expander(as_display_text(get_first_field(direction, "название", "название_направления", default="Направление"))):
            _write_named_list("Описание", direction.get("описание"))
            ids = as_list(get_first_field(direction, "представители", "участники"))
            st.write("**Представители:** " + "; ".join(resolve_person_names(ids, indexes["persons"])))
            _render_assignment_status_note(document, "research_direction", str(direction.get("id")))
            for evidence_id in direction.get("подтверждения", []):
                st.write(_evidence_summary(evidence_id, indexes))
    st.subheader("Поколения")
    for generation in structure.get("поколения", []):
        ids = as_list(get_first_field(generation, "представители", "участники"))
        st.write(f"**{as_display_text(generation.get('название'))}:** {'; '.join(resolve_person_names(ids, indexes['persons']))}")
    st.subheader("Периоды развития")
    for period in school.get("хронология", {}).get("периоды_развития", []):
        ids = as_list(get_first_field(period, "участники", "персоны", "основные_представители"))
        with st.expander(as_display_text(get_first_field(period, "название", "название_периода", default="Период"))):
            _write_named_list("Период", get_first_field(period, "период", "временной_диапазон"))
            _write_named_list("Описание", period.get("описание"))
            if has_canonical_assignments(document):
                st.write("**Все размеченные участники:** " + "; ".join(resolve_person_names(ids, indexes["persons"])))
                ids = as_list(period.get("основные_представители"))
            st.write("**Основные представители:** " + "; ".join(resolve_person_names(ids, indexes["persons"])))
            _render_assignment_status_note(document, "period", str(period.get("id")))


def render_ideas_and_directions_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает идеи и направления."""
    school = normalize_source_school_document(document)["школа"]
    ideas = school.get("идеи_и_направления", {})
    theoretical = get_first_field(school, "теоретические_основания", default=ideas.get("теоретические_основания", {}))
    main_idea = school.get("основная_идея")
    _write_named_list("Основная идея", main_idea)
    _write_named_list("Теоретические основания", theoretical)
    _write_named_list("Ключевые понятия", get_first_field(theoretical, "понятия", "ключевые_понятия", "основные_понятия", default=ideas.get("ключевые_понятия")))
    _write_named_list("Теории", get_first_field(theoretical, "теории", default=ideas.get("теории")))
    _write_named_list("Методы", get_first_field(theoretical, "методы", default=ideas.get("методы")))
    _write_named_list("Интеллектуальные источники", get_first_field(theoretical, "интеллектуальные_источники", "источники_идей", default=ideas.get("интеллектуальные_источники")))
    _write_named_list("Основные результаты", get_first_field(school, "основные_результаты", default=ideas.get("основные_результаты")))
    _write_named_list("Связанные школы", get_first_field(school, "связи_с_другими_школами", "связанные_школы", default=ideas.get("связанные_школы")))
    for direction in school["внутренняя_структура"].get("направления", []):
        with st.expander(as_display_text(get_first_field(direction, "название", "название_направления", default="Направление"))):
            _write_named_list("Описание", direction.get("описание"))
            ids = as_list(get_first_field(direction, "представители", "участники"))
            st.write("**Представители:** " + "; ".join(resolve_person_names(ids, indexes["persons"])))
            _render_assignment_status_note(document, "research_direction", str(direction.get("id")))
            for evidence_id in direction.get("подтверждения", []):
                st.write(_evidence_summary(evidence_id, indexes))


def render_sources_and_evidence_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает источники и подтверждения."""
    st.subheader("Список использованных источников")
    st.caption(
        "Библиографические описания приведены в формате, близком к ГОСТ; автоматическая сертифицированная "
        "проверка ГОСТ не выполняется. Дата обращения показывается для электронных источников."
    )
    for row in build_numbered_bibliography(document):
        st.markdown(f"{row['№']}. {row['описание']}")
        if _safe_url(row.get("url")):
            st.link_button("Открыть источник", row["url"], key=f"source_schools_open_source_{row['№']}")
    with st.expander("Таблица источников", expanded=False):
        st.dataframe(build_sources_dataframe(document).drop(columns=["ID"]), hide_index=True, use_container_width=True)
    evidence_dataframe = build_evidence_dataframe(document)
    source_filter = st.multiselect(
        "Источник подтверждения",
        sorted(evidence_dataframe["Источник"].unique()),
        key="source_schools_evidence_sources",
    )
    type_filter = st.multiselect(
        "Тип утверждения",
        sorted(evidence_dataframe["Тип утверждения"].unique()),
        key="source_schools_evidence_types",
    )
    status_filter = st.multiselect(
        "Статус утверждения",
        ["Явное утверждение", "Интерпретация"],
        key="source_schools_evidence_status",
    )
    filtered = evidence_dataframe.copy()
    if source_filter:
        filtered = filtered[filtered["Источник"].isin(source_filter)]
    if type_filter:
        filtered = filtered[filtered["Тип утверждения"].isin(type_filter)]
    if status_filter:
        filtered = filtered[filtered["Статус"].isin(status_filter)]
    st.dataframe(filtered.drop(columns=["ID"]), hide_index=True, use_container_width=True)
    for _, row in filtered.iterrows():
        with st.expander(str(row["Содержание свидетельства"])[:80]):
            st.write(f"**{row['Источник']}:**")
            st.write(f"**Содержание свидетельства:** {row['Содержание свидетельства']}")
            st.write(f"**Локатор:** {row['Локатор']}")
            st.write(f"**Тип утверждения:** {row['Тип утверждения']}")
            st.write(f"**Статус:** {row['Статус']}")
            st.write(f"**Уверенность:** {row['Уверенность']}")


def render_disagreements_and_quality_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает расхождения и качество данных."""
    school = document["школа"]
    quality = document["контроль_качества"]
    for disagreement in school.get("историографические_расхождения", []):
        with st.expander(disagreement.get("вопрос", "Расхождение")):
            for position in disagreement.get("позиции", []):
                source_names = [
                    _source_label(indexes["sources"][source_id])
                    for source_id in position.get("источники", [])
                    if source_id in indexes["sources"]
                ]
                st.write(f"**Источникозависимая интерпретация:** {get_first_field(position, 'формулировка', 'позиция')}")
                st.write("**Источники:** " + "; ".join(source_names))
                _write_named_list("Страница / раздел", position.get("локатор"))
            _write_named_list("Ограничение вывода", disagreement.get("ограничение"))
    hypotheses = school.get("журнал_классификационных_гипотез", [])
    if hypotheses:
        with st.expander("Принадлежности, не включённые в фильтры"):
            catalog_labels = {
                (dimension, value.id.split(":", 1)[1]): value.label
                for dimension, values in build_supplementary_dimension_catalog(document).items()
                for value in values
            }
            for hypothesis in hypotheses:
                person = indexes["persons"].get(hypothesis.get("персона"), {})
                label = catalog_labels.get((hypothesis.get("измерение"), hypothesis.get("значение")), "Неустановленная принадлежность")
                st.write(f"**{get_first_field(person, 'полное_имя', 'имя')}: {label}**")
                _write_named_list("Решение", hypothesis.get("решение"))
                _write_named_list("Ограничение", hypothesis.get("ограничение"))
                for attribution in hypothesis.get("источниковые_атрибуции", []):
                    source = indexes["sources"].get(attribution.get("идентификатор_источника"), {})
                    st.write(f"{_source_label(source)}; {attribution.get('локатор', '')}. {attribution.get('утверждение', '')}")
    review_items = school.get("журнал_проверки_источников", [])
    if review_items:
        st.subheader("Результаты проверки источников")
        for item in review_items:
            with st.expander(item.get("предмет", "Результат проверки")):
                _write_named_list("Дата проверки", item.get("дата"))
                _write_named_list("Что сообщает источник", item.get("выявлено"))
                _write_named_list("Принятое решение", item.get("принятое_решение"))
                _write_named_list("Ограничения", item.get("ограничения"))
                for attribution in item.get("источниковые_атрибуции", []):
                    source = indexes["sources"].get(attribution.get("идентификатор_источника"), {})
                    st.write(f"{_source_label(source)}; с. {attribution.get('печатная_страница')}; {attribution.get('локатор', '')}; {attribution.get('тип_свидетельства', '')}.")
    st.subheader("Качество данных")
    labels = {
        "использовано_несколько_источников": "Использовано несколько источников",
        "расхождения_источников_сохранены": "Расхождения между источниками сохранены",
        "прямые_и_косвенные_связи_разделены": "Прямые и косвенные связи разделены",
        "ссылки_разрешены": "Ссылки разрешены",
        "сводка_согласована": "Сводка согласована",
    }
    checks = dict(quality.get("проверки", {}))
    for key in ("использовано_несколько_источников", "расхождения_источников_сохранены", "прямые_и_косвенные_связи_разделены"):
        if key in quality:
            checks[key] = quality[key]
    for key, value in checks.items():
        message = f"{labels.get(key, as_display_text(key))}: {'да' if value else 'требует проверки'}"
        if value:
            st.success(message)
        else:
            st.warning(message)
    _write_named_list("Недостаточно сведений", get_first_field(quality, "недостаточно_сведений", "поля_с_недостаточной_информацией"))
    _write_named_list("Интерпретативные выводы", get_first_field(quality, "интерпретативные_выводы", "потенциально_интерпретативные_выводы"))
    _write_named_list("Примечания", get_first_field(quality, "примечания", "замечания"))
    metadata = get_first_field(quality, "метаданные_извлечения", default={})
    school_metadata = get_first_field(school, "метаданные_извлечения", default={})
    if school_metadata:
        metadata = {**metadata, **school_metadata}
    for key, value in metadata.items():
        _write_named_list(as_display_text(str(key)), value)
    with st.expander("Кандидаты для дальнейшего расширения данных"):
        st.caption("Эти персоны или группы пока не входят в проверенный основной список.")
        st.write(as_display_text(school.get("кандидаты_на_расширение")))
