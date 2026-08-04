"""Загрузка и проверка статических данных школ по источникам."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import streamlit as st

SOURCE_SCHOOLS_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "source_schools"
SUPPORTED_SCHEMA_KEYS: tuple[str, ...] = ("школа", "демо_представление", "контроль_качества", "_processing_metadata")

class SourceSchoolDataError(ValueError):
    """Ошибка структуры или связности данных школы по источникам."""


def _require_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise SourceSchoolDataError(f"В файле школы отсутствует обязательное поле: {key}.")
    return item


def _require_list(value: Mapping[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise SourceSchoolDataError(f"В файле школы отсутствует обязательное поле: {key}.")
    return item


def _require_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise SourceSchoolDataError(f"В файле школы отсутствует обязательное поле: {key}.")
    return item


def _unique(items: list[Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        ident = item.get("id")
        if not isinstance(ident, str) or not ident.strip():
            raise SourceSchoolDataError(f"В списке {label} найден пустой идентификатор.")
        if ident in result:
            raise SourceSchoolDataError(f"Обнаружен повторяющийся идентификатор {label}: {ident}.")
        result[ident] = item
    return result


def build_source_school_index(document: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Строит индексы персон, источников, подтверждений и групп по ID."""
    school = document["школа"]
    structure = school.get("внутренняя_структура", {})
    return {
        "persons": _unique(school.get("персоны", []), "персоны"),
        "sources": _unique(school.get("источники", []), "источника"),
        "evidence": _unique(school.get("подтверждения", []), "подтверждения"),
        "groups": _unique(structure.get("исследовательские_группы", []), "исследовательской группы"),
    }


def _check_confidence(value: Any, where: str) -> None:
    if value is None:
        return
    if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
        raise SourceSchoolDataError(f"Некорректная уверенность в поле {where}.")


def _check_person_ids(values: list[Any], persons: Mapping[str, Any], where: str) -> None:
    for ident in values or []:
        if ident not in persons:
            raise SourceSchoolDataError(f"Неизвестная персона в поле {where}: {ident}.")


def validate_source_school_document(document: Mapping[str, Any]) -> None:
    """Проверяет обязательные поля, идентификаторы и ссылки."""
    if not isinstance(document, Mapping):
        raise SourceSchoolDataError("Файл школы должен содержать JSON-объект.")
    school = _require_mapping(document, "школа")
    demo = _require_mapping(document, "демо_представление")
    quality = _require_mapping(document, "контроль_качества")
    for key in ["идентификатор_школы", "каноническое_название"]:
        _require_text(school, key)
    for key in ["персоны", "источники", "подтверждения", "историографические_расхождения"]:
        _require_list(school, key)
    _require_mapping(school, "внутренняя_структура")
    for key in ["название_в_выпадающем_списке", "заголовок_страницы", "подзаголовок", "методологическое_предупреждение"]:
        _require_text(demo, key)
    _require_list(demo, "рекомендуемые_разделы")
    indexes = build_source_school_index(document)
    persons, sources, evidence = indexes["persons"], indexes["sources"], indexes["evidence"]
    for source in sources.values():
        url = source.get("url")
        if url is not None and not isinstance(url, str):
            raise SourceSchoolDataError(f"Некорректный URL источника: {source.get('id')}.")
        if url and urlparse(url).scheme and urlparse(url).scheme not in {"http", "https"}:
            source_id = source.get("id")
            raise SourceSchoolDataError(f"Источник {source_id} содержит небезопасную ссылку.")
    for ev in evidence.values():
        sid = ev.get("идентификатор_источника")
        if sid not in sources:
            raise SourceSchoolDataError(f"Подтверждение {ev.get('id')} ссылается на неизвестный источник: {sid}.")
        _check_confidence(ev.get("уверенность"), f"подтверждения.{ev.get('id')}")
    for person in persons.values():
        for eid in person.get("подтверждения", []):
            if eid not in evidence:
                raise SourceSchoolDataError(f"Персона {person.get('id')} ссылается на неизвестное подтверждение: {eid}.")
        _check_confidence(person.get("уверенность"), f"персоны.{person.get('id')}")
        for attr in person.get("источниковые_атрибуции", []):
            sid, eid = attr.get("идентификатор_источника"), attr.get("подтверждение")
            if sid not in sources:
                raise SourceSchoolDataError(f"Персона {person.get('id')} ссылается на неизвестный источник: {sid}.")
            if eid not in evidence:
                raise SourceSchoolDataError(f"Персона {person.get('id')} ссылается на неизвестное подтверждение: {eid}.")
            _check_confidence(attr.get("уверенность"), f"атрибуции.{person.get('id')}")
    structure = school["внутренняя_структура"]
    for group in structure.get("исследовательские_группы", []):
        _check_person_ids(group.get("участники", []), persons, f"группа {group.get('id')}")
        for eid in group.get("подтверждения", []):
            if eid not in evidence:
                raise SourceSchoolDataError(f"Группа {group.get('id')} ссылается на неизвестное подтверждение: {eid}.")
    for item in structure.get("направления", []) + structure.get("поколения", []):
        _check_person_ids(item.get("представители", []), persons, "внутренняя структура")
    for period in school.get("хронология", {}).get("периоды_развития", []):
        _check_person_ids(period.get("персоны", []), persons, "хронология")
    for row in school.get("историографические_расхождения", []):
        for pos in row.get("позиции", []):
            for sid in pos.get("источники", []):
                if sid not in sources:
                    raise SourceSchoolDataError(f"Историографическая позиция ссылается на неизвестный источник: {sid}.")
    counts = {"число_персон": len(persons), "число_источников": len(sources), "число_подтверждений": len(evidence)}
    by_cat: dict[str, int] = {}
    for p in persons.values():
        by_cat[p.get("категория_включения", "")] = by_cat.get(p.get("категория_включения", ""), 0) + 1
    counts["персоны_по_категориям"] = by_cat
    for block_name, block in [("демо_представление.сводные_показатели", demo.get("сводные_показатели", {})), ("контроль_качества", quality)]:
        for key, value in counts.items():
            if block.get(key) != value:
                raise SourceSchoolDataError(f"Сводные показатели устарели: {block_name}.{key}.")


def load_source_school_file(path: Path) -> dict[str, Any]:
    """Загружает и проверяет один JSON-файл."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceSchoolDataError(f"Файл школы содержит некорректный JSON: {path.name}.") from exc
    validate_source_school_document(document)
    return document


@st.cache_data(show_spinner=False)
def _cached_catalog(path_text: str) -> list[dict[str, Any]]:
    return _load_catalog_uncached(Path(path_text))


def _load_catalog_uncached(data_dir: Path) -> list[dict[str, Any]]:
    if not data_dir.exists():
        return []
    entries=[]; seen_ids=set(); seen_labels=set()
    for path in sorted(data_dir.glob("*.json")):
        doc = load_source_school_file(path)
        sid = doc["школа"]["идентификатор_школы"]
        label = doc["демо_представление"]["название_в_выпадающем_списке"]
        if sid in seen_ids:
            raise SourceSchoolDataError(f"Обнаружен повторяющийся идентификатор школы: {sid}.")
        if label in seen_labels:
            raise SourceSchoolDataError(f"Обнаружено повторяющееся название школы: {label}.")
        seen_ids.add(sid); seen_labels.add(label)
        entries.append({"school_id": sid, "label": label, "path": str(path), "document": doc})
    return entries


def load_source_school_catalog(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Загружает и проверяет все JSON-файлы каталога."""
    directory = data_dir or SOURCE_SCHOOLS_DATA_DIR
    return _cached_catalog(str(directory)) if data_dir is None else _load_catalog_uncached(directory)
