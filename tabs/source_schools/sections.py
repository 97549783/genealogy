"""Отрисовка внутренних режимов демо-раздела школ по источникам."""
from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse

import streamlit as st

from core.source_schools.presentation import as_display_text, as_list, get_first_field
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
    return f"{_source_label(source)} — {evidence.get('содержание_свидетельства', '')}{locator_text}"


def _write_named_list(title: str, value: Any) -> None:
    text = as_display_text(value)
    if text:
        st.write(f"**{title}:** {text}")


def render_overview_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
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
            st.write(f"{as_display_text(alternative.get('название'))} — {as_display_text(alternative.get('примечание'))}")
    _write_named_list("Тип школы", school.get("тип_школы"))
    st.caption(as_display_text(school.get("примечание_к_типу")))
    disciplines = school.get("дисциплинарная_принадлежность", {})
    main_idea = school.get("основная_идея", {})
    chronology = school.get("хронология", {})
    _write_named_list("Дисциплинарные области", get_first_field(disciplines, "области", default=school.get("дисциплинарные_области")))
    _write_named_list("Ключевые слова", get_first_field(disciplines, "ключевые_слова", default=school.get("ключевые_слова")))
    _write_named_list("Основная идея", main_idea)
    _write_named_list("Проблема", get_first_field(main_idea, "центральная_проблема", default=school.get("проблема")))
    _write_named_list("Гипотеза", get_first_field(main_idea, "центральная_гипотеза", default=school.get("гипотеза")))
    _write_named_list("Теория", get_first_field(main_idea, "центральная_теория", default=school.get("теория")))
    _write_named_list("Метод", get_first_field(main_idea, "центральный_метод", default=school.get("метод")))
    _write_named_list("Хронология", get_first_field(chronology, "кратко", "общий_период", "описание"))
    _write_named_list("География", school.get("география"))
    _write_named_list("Организации", school.get("организации"))


def render_people_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает состав школы с фильтрами и карточкой персоны."""
    st.warning(document["демо_представление"]["методологическое_предупреждение"])
    dataframe = build_people_dataframe(document)
    query = st.text_input("Поиск по представителям", key="source_schools_people_query")
    categories = st.multiselect(
        "Категория включения",
        sorted(dataframe["Категория"].dropna().unique()),
        key="source_schools_people_categories",
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
        categories=categories,
        roles=roles,
        groups=groups,
        source_ids=source_ids,
        minimum_confidence=minimum_confidence,
    )
    st.write(f"Найдено представителей: {len(filtered)}")
    if filtered.empty:
        st.info("По заданным условиям представители не найдены.")
        return
    st.dataframe(
        filtered.drop(columns=["ID", "Идентификаторы источников"]),
        hide_index=True,
        use_container_width=True,
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
    _write_named_list("Годы жизни", get_first_field(person, "годы_жизни", "даты"))
    _write_named_list("Категория включения как систематизация", person.get("категория_включения"))
    _write_named_list("Роли", person.get("роль_в_школе"))
    _write_named_list("Связь с Выготским", person.get("статус_связи_с_выготским"))
    _write_named_list("Период взаимодействия", person.get("период_взаимодействия"))
    _write_named_list("Группы и контексты", person.get("группы_и_контексты"))
    _write_named_list("Основной вклад", get_first_field(person, "основной_вклад", "основные_идеи_или_вклад"))
    _write_named_list("Уверенность", person.get("уверенность"))
    st.markdown("#### Источниковые атрибуции")
    for attribution in person.get("источниковые_атрибуции", []):
        source = indexes["sources"][attribution["идентификатор_источника"]]
        evidence = indexes["evidence"][attribution["подтверждение"]]
        st.write(
            f"**{_source_label(source)}:** {attribution.get('формулировка_роли')} / "
            f"систематизация: {attribution.get('нормализованная_роль')} — "
            f"{_evidence_status(attribution.get('явное_утверждение'))}. "
            f"Подтверждение: {evidence.get('содержание_свидетельства')} ({evidence.get('локатор')})."
        )


def render_groups_and_chronology_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает группы, направления, поколения и хронологию."""
    school = document["школа"]
    structure = school["внутренняя_структура"]
    st.subheader("Исследовательские группы")
    for group in structure.get("исследовательские_группы", []):
        with st.expander(as_display_text(group.get("название", "Группа"))):
            _write_named_list("Период", group.get("период"))
            st.write("**Участники:** " + "; ".join(resolve_person_names(group.get("участники", []), indexes["persons"])))
            for evidence_id in group.get("подтверждения", []):
                st.write(_evidence_summary(evidence_id, indexes))
    st.subheader("Направления")
    for direction in structure.get("направления", []):
        with st.expander(as_display_text(get_first_field(direction, "название", "название_направления", default="Направление"))):
            _write_named_list("Описание", direction.get("описание"))
            ids = as_list(get_first_field(direction, "представители", "участники"))
            st.write("**Представители:** " + "; ".join(resolve_person_names(ids, indexes["persons"])))
            for evidence_id in direction.get("подтверждения", []):
                st.write(_evidence_summary(evidence_id, indexes))
    st.subheader("Поколения")
    for generation in structure.get("поколения", []):
        ids = as_list(get_first_field(generation, "представители", "участники"))
        st.write(f"**{as_display_text(generation.get('название'))}:** {'; '.join(resolve_person_names(ids, indexes['persons']))}")
    st.subheader("Периоды развития")
    for period in school.get("хронология", {}).get("периоды_развития", []):
        ids = as_list(get_first_field(period, "персоны", "основные_представители"))
        with st.expander(as_display_text(get_first_field(period, "название", "название_периода", default="Период"))):
            _write_named_list("Период", get_first_field(period, "период", "временной_диапазон"))
            _write_named_list("Описание", period.get("описание"))
            st.write("**Основные представители:** " + "; ".join(resolve_person_names(ids, indexes["persons"])))


def render_ideas_and_directions_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает идеи и направления."""
    school = document["школа"]
    ideas = school.get("идеи_и_направления", school)
    _write_named_list("Основная идея", school.get("основная_идея"))
    for key, label in (
        (("теоретические_основания",), "Теоретические основания"),
        (("ключевые_понятия", "основные_понятия"), "Ключевые понятия"),
        (("теории", "центральная_теория"), "Теории"),
        (("методы", "центральный_метод"), "Методы"),
        (("интеллектуальные_источники", "источники_идей"), "Интеллектуальные источники"),
        (("основные_результаты",), "Основные результаты"),
        (("связанные_школы", "связи_с_другими_школами"), "Связанные школы"),
    ):
        _write_named_list(label, get_first_field(ideas, *key))
    for direction in school["внутренняя_структура"].get("направления", []):
        with st.expander(as_display_text(get_first_field(direction, "название", "название_направления", default="Направление"))):
            _write_named_list("Описание", direction.get("описание"))
            ids = as_list(get_first_field(direction, "представители", "участники"))
            st.write("**Представители:** " + "; ".join(resolve_person_names(ids, indexes["persons"])))
            for evidence_id in direction.get("подтверждения", []):
                st.write(_evidence_summary(evidence_id, indexes))


def render_sources_and_evidence_section(document: Mapping[str, Any], indexes: Mapping[str, Any]) -> None:
    """Отрисовывает источники и подтверждения."""
    st.dataframe(build_sources_dataframe(document).drop(columns=["ID"]), hide_index=True, use_container_width=True)
    for source in document["школа"]["источники"]:
        with st.expander(_source_label(source)):
            st.write(source.get("библиографическое_описание", ""))
            if _safe_url(source.get("url")):
                st.link_button("Открыть источник", source["url"])
            if source.get("дата_обращения"):
                st.caption(f"Дата обращения: {source['дата_обращения']}")
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
            st.write(f"**Источник:** {row['Источник']}")
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
    st.subheader("Качество данных")
    checks = quality.get("проверки", {})
    for key in ("использовано_несколько_источников", "расхождения_источников_сохранены", "прямые_и_косвенные_связи_разделены"):
        if key in quality:
            checks[key] = quality[key]
    for key, value in checks.items():
        message = f"{key}: {'да' if value else 'требует проверки'}"
        if value:
            st.success(message)
        else:
            st.warning(message)
    _write_named_list("Недостаточно сведений", get_first_field(quality, "недостаточно_сведений", "поля_с_недостаточной_информацией"))
    _write_named_list("Интерпретативные выводы", get_first_field(quality, "интерпретативные_выводы", "потенциально_интерпретативные_выводы"))
    _write_named_list("Примечания", get_first_field(quality, "примечания", "замечания"))
    for key, value in get_first_field(quality, "метаданные_извлечения", default={}).items():
        _write_named_list(str(key), value)
    with st.expander("Кандидаты для дальнейшего расширения данных"):
        st.caption("Эти персоны или группы пока не входят в проверенный основной список.")
        st.write(as_display_text(school.get("кандидаты_на_расширение")))
