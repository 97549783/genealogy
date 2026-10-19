"""Произвольные гибкие классификации на основе единого реестра v2.1."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from .model import accepted_assignments, dimension_definitions, included_persons

ACCEPTED_STATUSES = {"принято"}
ASSIGNMENT_STATUSES = {"принято", "гипотеза", "отклонено"}


def has_canonical_assignments(document: Mapping[str, Any]) -> bool:
    return "классификационные_назначения" in document


def dimension_catalogs(document: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    """Возвращает гибкие измерения; основное деление рассматривается отдельно."""
    return {key: sorted(value["значения"], key=lambda v: v["порядок"])
            for key, value in dimension_definitions(document, include_primary=False).items()}


def build_dimension_memberships(document: Mapping[str, Any], *, include_unverified: bool = False) -> dict[str, dict[str, tuple[str, ...]]]:
    """Учитывает принятые назначения; состояние сверки не активирует гипотезы.

    Аргумент ``include_unverified`` сохранён в API и не меняет решение о принятии.
    """
    result = {dimension: {value["id"]: [] for value in values}
              for dimension, values in dimension_catalogs(document).items()}
    assignments = sorted(accepted_assignments(document), key=lambda a: a.get("порядок") or 10**9)
    for assignment in assignments:
        dimension, value = assignment["измерение"], assignment["значение"]
        if value in result.get(dimension, {}):
            result[dimension][value].append(assignment["персона"])
    return {dimension: {value: tuple(dict.fromkeys(people)) for value, people in values.items()}
            for dimension, values in result.items()}


def build_dimension_coverage(document: Mapping[str, Any], *, include_unverified: bool = False) -> dict[str, dict[str, Any]]:
    persons = [p["id"] for p in included_persons(document)]
    result = {}
    for dimension, values in build_dimension_memberships(document).items():
        covered = {person for people in values.values() for person in people}
        assignments = accepted_assignments(document, dimension_id=dimension)
        interpreted = {a["персона"] for a in assignments if a["характер"] == "классификационная_интерпретация"}
        unverified = {a["персона"] for a in assignments if a.get("проверка", {}).get("статус") in {"не_проверено", "частично_сверено"}}
        result[dimension] = {
            "catalog_count": len(values), "assigned_person_count": len(covered),
            "unclassified_person_ids": tuple(p for p in persons if p not in covered),
            "interpretative_person_ids": tuple(p for p in persons if p in interpreted),
            "unverified_person_ids": tuple(p for p in persons if p in unverified),
        }
    return result


def build_person_dimension_labels(document: Mapping[str, Any]) -> dict[str, dict[str, list[str]]]:
    catalogs = dimension_catalogs(document)
    result = {person["id"]: {key: [] for key in catalogs} for person in included_persons(document)}
    memberships = build_dimension_memberships(document)
    for dimension, values in catalogs.items():
        for value in values:
            for person in memberships[dimension][value["id"]]:
                result[person][dimension].append(value["название"])
    return result


def project_dimension_memberships(document: Mapping[str, Any]) -> dict[str, Any]:
    """Возвращает независимый исходный документ без дублирования списков принадлежностей."""
    return copy.deepcopy(dict(document))


def validate_dimension_assignments(document: Mapping[str, Any]) -> None:
    from .data import validate_source_school_document
    validate_source_school_document(document)
