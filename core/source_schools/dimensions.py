"""Каноническое членство персон в классификациях школы по источникам."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from .presentation import as_list, get_first_field

DIMENSION_IDS = ("historical_group", "period", "research_direction")
ASSIGNMENT_STATUSES = {"подтверждено", "интерпретация", "не_проверено"}
ACCEPTED_STATUSES = {"подтверждено", "интерпретация"}


def has_canonical_assignments(document: Mapping[str, Any]) -> bool:
    """Отличает новый контракт от старого, включая пустой список назначений."""
    return "классификационные_назначения" in document.get("школа", {})


def dimension_catalogs(document: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    """Возвращает описательные каталоги, не извлекая принадлежности из текста."""
    school = document.get("школа", {})
    structure = school.get("внутренняя_структура", {})
    chronology = school.get("хронология", {}) or {}
    values = {
        "historical_group": structure.get("исследовательские_группы", []),
        "period": chronology.get("периоды_развития", []),
        "research_direction": structure.get("направления", []),
    }
    return {key: [item for item in items if isinstance(item, Mapping)] for key, items in values.items()}


def build_dimension_memberships(
    document: Mapping[str, Any], *, include_unverified: bool = False,
) -> dict[str, dict[str, tuple[str, ...]]]:
    """Читает назначения; старые документы используют только явные каталожные списки."""
    canonical = has_canonical_assignments(document)
    catalogs = dimension_catalogs(document)
    result: dict[str, dict[str, list[str]]] = {
        dimension: {str(item.get("id", index)): [] for index, item in enumerate(items)}
        for dimension, items in catalogs.items()
    }
    if canonical:
        statuses = ASSIGNMENT_STATUSES if include_unverified else ACCEPTED_STATUSES
        for assignment in document["школа"].get("классификационные_назначения", []):
            if not isinstance(assignment, Mapping) or assignment.get("статус") not in statuses:
                continue
            dimension, value = str(assignment.get("измерение")), str(assignment.get("значение"))
            if value in result.get(dimension, {}):
                result[dimension][value].append(str(assignment.get("персона")))
    else:
        legacy_fields = {
            "historical_group": ("участники",),
            "period": ("участники", "персоны", "основные_представители"),
            "research_direction": ("представители", "участники"),
        }
        for dimension, items in catalogs.items():
            for index, item in enumerate(items):
                result[dimension][str(item.get("id", index))] = [
                    str(person_id) for person_id in as_list(get_first_field(item, *legacy_fields[dimension]))
                ]
    return {
        dimension: {value: tuple(dict.fromkeys(person_ids)) for value, person_ids in values.items()}
        for dimension, values in result.items()
    }


def build_dimension_coverage(
    document: Mapping[str, Any], *, include_unverified: bool = False,
) -> dict[str, dict[str, Any]]:
    """Считает охват и сохраняет различие между отсутствием разметки и сомнением."""
    person_ids = [str(person["id"]) for person in document.get("школа", {}).get("персоны", [])]
    memberships = build_dimension_memberships(document, include_unverified=include_unverified)
    assignments = document.get("школа", {}).get("классификационные_назначения", [])
    result = {}
    for dimension, values in memberships.items():
        covered = {person_id for ids in values.values() for person_id in ids}
        interpreted = {
            str(item.get("персона")) for item in assignments if isinstance(item, Mapping)
            and item.get("измерение") == dimension and item.get("статус") == "интерпретация"
        }
        unchecked = {
            str(item.get("персона")) for item in assignments if isinstance(item, Mapping)
            and item.get("измерение") == dimension and item.get("статус") == "не_проверено"
        }
        result[dimension] = {
            "catalog_count": len(values),
            "assigned_person_count": len(covered),
            "unclassified_person_ids": tuple(item for item in person_ids if item not in covered),
            "interpretative_person_ids": tuple(item for item in person_ids if item in interpreted),
            "unverified_person_ids": tuple(item for item in person_ids if item in unchecked),
        }
    return result


def project_dimension_memberships(document: Mapping[str, Any]) -> dict[str, Any]:
    """Возвращает копию с совместимыми списками как проекцией канонических назначений."""
    projected = copy.deepcopy(dict(document))
    if not has_canonical_assignments(projected):
        return projected
    memberships = build_dimension_memberships(projected)
    for dimension, items in dimension_catalogs(projected).items():
        for item in items:
            ids = list(memberships[dimension].get(str(item.get("id")), ()))
            item["участники" if dimension != "research_direction" else "представители"] = ids
            if dimension == "research_direction" and "участники" in item:
                item["участники"] = ids
            if dimension == "period" and "персоны" in item:
                item["персоны"] = ids
    return projected


def build_person_dimension_labels(document: Mapping[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Готовит те же классификации для таблицы и карточки персоны."""
    result = {str(person["id"]): {key: [] for key in DIMENSION_IDS} for person in document["школа"]["персоны"]}
    memberships = build_dimension_memberships(document)
    for dimension, items in dimension_catalogs(document).items():
        for index, item in enumerate(items):
            label = str(get_first_field(item, "название", "название_периода", "название_направления"))
            if dimension == "historical_group" and item.get("вид") == "контекст":
                label = "Контекст: " + label
            for person_id in memberships[dimension][str(item.get("id", index))]:
                if person_id in result:
                    result[person_id][dimension].append(label)
    return result


def validate_dimension_assignments(document: Mapping[str, Any]) -> None:
    """Проверяет адресную атрибуцию person × измерение × значение нового контракта."""
    if not has_canonical_assignments(document):
        return
    # Импорт внутри функции сохраняет независимость преобразований от загрузчика.
    from .data import SourceSchoolDataError

    school = document["школа"]
    assignments = school["классификационные_назначения"]
    if not isinstance(assignments, list):
        raise SourceSchoolDataError("Классификационные назначения должны быть списком.")
    catalog_ids = {}
    for dimension, items in dimension_catalogs(document).items():
        ids = [item.get("id") for item in items]
        if any(not isinstance(item, str) or not item.strip() for item in ids) or len(ids) != len(set(ids)):
            raise SourceSchoolDataError(f"Каталог {dimension} требует уникальные стабильные id.")
        if any(item in {"__unclassified__", "__interpretative__", "__unverified__"} for item in ids):
            raise SourceSchoolDataError(f"Каталог {dimension} использует зарезервированный id.")
        catalog_ids[dimension] = set(ids)
    persons = {item["id"] for item in school["персоны"]}
    sources = {item["id"] for item in school["источники"]}
    evidence = {item["id"]: item for item in school["подтверждения"]}
    seen, seen_ids = set(), set()
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise SourceSchoolDataError("Классификационное назначение должно быть объектом.")
        ident = assignment.get("id")
        if not isinstance(ident, str) or not ident.strip() or ident in seen_ids:
            raise SourceSchoolDataError("Назначение требует уникальный непустой id.")
        seen_ids.add(ident)
        person, dimension, value = (assignment.get(key) for key in ("персона", "измерение", "значение"))
        if person not in persons or value not in catalog_ids.get(dimension, set()):
            raise SourceSchoolDataError(f"Назначение {ident} содержит неизвестную персону, измерение или значение.")
        key = person, dimension, value
        if key in seen:
            raise SourceSchoolDataError(f"Повторное классификационное назначение: {key}.")
        seen.add(key)
        status = assignment.get("статус")
        if status not in ASSIGNMENT_STATUSES:
            raise SourceSchoolDataError(f"Назначение {ident} содержит неизвестный статус.")
        attributions = assignment.get("источниковые_атрибуции", [])
        if not isinstance(attributions, list) or (status in ACCEPTED_STATUSES and not attributions):
            raise SourceSchoolDataError(f"Назначение {ident} не имеет адресной источниковой атрибуции.")
        for attribution in attributions:
            if not isinstance(attribution, Mapping) or attribution.get("идентификатор_источника") not in sources:
                raise SourceSchoolDataError(f"Назначение {ident} ссылается на неизвестный источник.")
            evidence_id = attribution.get("подтверждение")
            if evidence_id is not None and (
                evidence_id not in evidence
                or evidence[evidence_id].get("идентификатор_источника") != attribution["идентификатор_источника"]
            ):
                raise SourceSchoolDataError(f"Назначение {ident} имеет несогласованное подтверждение источника.")
            if status in ACCEPTED_STATUSES and not (evidence_id or attribution.get("локатор")):
                raise SourceSchoolDataError(f"Назначение {ident} требует подтверждение или локатор источника.")
