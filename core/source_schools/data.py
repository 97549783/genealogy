"""Загрузка школ формата v2.1 с проверкой JSON Schema и ссылочной целостности."""
from __future__ import annotations

import copy
import calendar
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .model import accepted_assignments, dimension_definitions, display_persons, included_persons, membership_index

SOURCE_SCHOOLS_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "source_schools" / "schools"
SOURCE_SCHOOLS_SCHEMA_PATH = SOURCE_SCHOOLS_DATA_DIR.parent / "schema.json"


class SourceSchoolDataError(ValueError):
    """Ошибка документа школы, ссылки или классификационного назначения."""


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str


def _semantic_issues(doc: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    records: dict[str, tuple[str, dict[str, Any], str]] = {}
    entity_types: dict[str, str] = {}
    file_owners: dict[str, str] = {}
    dimensions: dict[str, dict[str, Any]] = {}

    def error(code: str, path: str, message: str) -> None:
        issues.append(Issue(code, path, message))

    def add(kind: str, record: dict[str, Any], path: str,
            key: str = "id") -> None:
        identifier = record.get(key)
        if identifier is None:
            return  # По схеме пустой ID школы допустим только в незаполненном шаблоне.
        if identifier in records:
            error("duplicate_id", path + "/" + key,
                  f"ID {identifier!r} уже объявлен в {records[identifier][2]}")
        else:
            records[identifier] = (kind, record, path)

    school = doc.get("школа", {})
    school_id = school.get("идентификатор_школы")
    add("школа", school, "/школа", "идентификатор_школы")
    if school_id is not None:
        entity_types[school_id] = "школа"
    arrays = (
        ("персона", doc.get("объекты", {}).get("персоны", []), "/объекты/персоны"),
        ("объект", doc.get("объекты", {}).get("прочие", []), "/объекты/прочие"),
        ("сведение", doc.get("сведения", []), "/сведения"),
        ("состав", doc.get("состав", []), "/состав"),
        ("связь", doc.get("связи", []), "/связи"),
        ("назначение", doc.get("классификационные_назначения", []), "/классификационные_назначения"),
        ("источник", doc.get("источники", []), "/источники"),
        ("основание", doc.get("основания", []), "/основания"),
        ("решение", doc.get("редактура", {}).get("журнал_решений", []), "/редактура/журнал_решений"),
        ("разночтение", doc.get("редактура", {}).get("разночтения", []), "/редактура/разночтения"),
    )
    for kind, entries, prefix in arrays:
        for index, record in enumerate(entries):
            path = f"{prefix}/{index}"
            add(kind, record, path)
            if kind == "персона":
                entity_types[record["id"]] = "персона"
            elif kind == "объект":
                entity_types[record["id"]] = record["тип"]
            elif kind == "источник":
                for file_index, file_record in enumerate(record.get("файлы", [])):
                    add("файл", file_record, f"{path}/файлы/{file_index}")
                    file_owners[file_record["id"]] = record["id"]

    classifications = doc.get("классификации", {})
    primary = classifications.get("основное_деление")
    facets = classifications.get("гибкие_измерения", [])
    classified = []
    if primary is not None:
        classified.append((primary, "/классификации/основное_деление", "категории"))
    classified.extend((facet, f"/классификации/гибкие_измерения/{i}", "значения")
                      for i, facet in enumerate(facets))
    for dimension, path, values_key in classified:
        add("измерение", dimension, path)
        dimensions[dimension["id"]] = {
            "record": dimension,
            "values": {value["id"] for value in dimension.get(values_key, [])},
        }
        local_values: set[str] = set()
        for index, value in enumerate(dimension.get(values_key, [])):
            # Значения адресуются парой (измерение, значение), а не глобальным ID.
            # Допустимо повторное использование ID объекта или значения другого измерения.
            if value["id"] in local_values:
                error("duplicate_value_id", f"{path}/{values_key}/{index}/id",
                      "ID категории или значения должен быть уникальным в пределах измерения")
            local_values.add(value["id"])

    def ref(identifier: str | None, kinds: set[str], path: str,
            nullable: bool = False) -> bool:
        if identifier is None and nullable:
            return True
        target = records.get(identifier)
        if target is None:
            error("unknown_reference", path, f"Неизвестная ссылка {identifier!r}")
            return False
        if target[0] not in kinds:
            error("reference_kind", path,
                  f"Ссылка {identifier!r}: ожидался тип {sorted(kinds)}, получен {target[0]}")
            return False
        return True

    entity_kinds = {"школа", "персона", "объект"}
    fields = {entry["код"]: entry for entry in doc.get("словари", {}).get("поля_сведений", [])}
    relation_types = {entry["код"]: entry for entry in doc.get("словари", {}).get("типы_связей", [])}
    for kind, entries, prefix in arrays:
        for i, record in enumerate(entries):
            path = f"{prefix}/{i}"
            if kind == "сведение":
                ref(record.get("субъект"), entity_kinds | {"связь"}, path + "/субъект")
                field = fields.get(record.get("поле"))
                if field is None:
                    error("unknown_field", path + "/поле", "Поле не определено в словаре")
                elif field["вид_значения"] != record.get("значение", {}).get("вид"):
                    error("field_value_kind", path + "/значение", "Вид значения не соответствует определению поля")
            elif kind == "состав":
                ref(record.get("персона"), {"персона"}, path + "/персона")
            elif kind == "связь":
                ref(record.get("от"), entity_kinds, path + "/от")
                ref(record.get("к"), entity_kinds, path + "/к")
                definition = relation_types.get(record.get("тип"))
                if definition is None:
                    error("unknown_relation_type", path + "/тип", "Тип связи не определён в словаре")
                else:
                    for endpoint, allowed in (("от", "типы_начала"), ("к", "типы_конца")):
                        actual = entity_types.get(record.get(endpoint))
                        if actual is not None and actual not in definition[allowed]:
                            error("relation_endpoint_kind", path + "/" + endpoint,
                                  f"Тип объекта {actual!r} недопустим для данной связи")
            elif kind == "объект":
                if record.get("источник_публикации") is not None:
                    ref(record["источник_публикации"], {"источник"}, path + "/источник_публикации")
            elif kind == "источник":
                if record.get("родительский_источник") is not None:
                    ref(record["родительский_источник"], {"источник"}, path + "/родительский_источник")
                for j, edition in enumerate(record.get("связанные_издания", [])):
                    ref(edition["источник"], {"источник"}, f"{path}/связанные_издания/{j}/источник")

    # Все ссылки на основания, включая варианты названий, идентификацию и редактуру.
    def check_nested(value: Any, path: str = "") -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                check_nested(item, f"{path}/{index}")
        elif isinstance(value, dict):
            for key in ("основания", "связанные_основания"):
                for index, identifier in enumerate(value.get(key, [])):
                    if isinstance(identifier, str):
                        ref(identifier, {"основание"}, f"{path}/{key}/{index}")
            if "реестр" in value and "id" in value:
                ref(value["id"], {value["реестр"]}, path + "/id")
            for key, item in value.items():
                if key in {"старое_значение", "новое_значение", "параметры"}:
                    continue  # Архивные снимки не содержат действующих ссылок.
                check_nested(item, f"{path}/{key}")
    check_nested(doc)

    for i, evidence in enumerate(doc.get("основания", [])):
        path = f"/основания/{i}"
        ref(evidence.get("источник"), {"источник"}, path + "/источник")
        file_id = evidence.get("файл")
        file_valid = ref(file_id, {"файл"}, path + "/файл", nullable=True)
        if file_id is not None and file_valid:
            if file_owners.get(file_id) != evidence.get("источник"):
                error("file_source_mismatch", path + "/файл", "Файл принадлежит другому источнику")
        pages = (evidence.get("локатор") or {}).get("страницы_pdf", [])
        if pages and file_id is None:
            error("pdf_file_required", path + "/файл", "Номера страниц PDF требуют ссылки на файл")
        if pages and file_id is not None and file_valid:
            page_count = records[file_id][1].get("число_страниц_pdf")
            if page_count is not None:
                for j, page in enumerate(pages):
                    if page < 1 or page > page_count:
                        error("pdf_page_bounds", f"{path}/локатор/страницы_pdf/{j}",
                              f"Страница {page} находится вне диапазона 1..{page_count}")

    memberships: dict[str, dict[str, Any]] = {}
    for i, membership in enumerate(doc.get("состав", [])):
        person_id = membership.get("персона")
        if person_id in memberships:
            error("duplicate_membership", f"/состав/{i}/персона", "Для персоны допустима одна запись включения в состав")
        memberships[person_id] = membership

    primary_id = primary["id"] if primary is not None else None
    primary_people: set[str] = set()
    tuples: set[tuple[str, str, str]] = set()
    for i, assignment in enumerate(doc.get("классификационные_назначения", [])):
        path = f"/классификационные_назначения/{i}"
        person_id = assignment.get("персона")
        ref(person_id, {"персона"}, path + "/персона")
        triple = (person_id, assignment.get("измерение"), assignment.get("значение"))
        if triple in tuples:
            error("duplicate_assignment_tuple", path, "Сочетание персона × измерение × значение должно быть уникальным")
        tuples.add(triple)
        dimension = dimensions.get(assignment.get("измерение"))
        if dimension is None:
            error("unknown_dimension", path + "/измерение", "Неизвестное классификационное измерение")
        elif assignment.get("значение") not in dimension["values"]:
            error("unknown_dimension_value", path + "/значение", "Значение не принадлежит данному измерению")
        if assignment.get("решение") != "принято":
            continue
        member = memberships.get(person_id)
        if member is None or member.get("решение") != "включено":
            error("assignment_not_included", path + "/персона", "Принятое назначение требует включения персоны в состав")
        if primary is not None and assignment.get("измерение") == primary_id:
            if person_id in primary_people:
                error("multiple_primary", path, "Для персоны допустима не более одной принятой основной категории")
            primary_people.add(person_id)
            if assignment.get("интервалы"):
                error("primary_intervals", path + "/интервалы", "Основное деление задаёт итоговую классификацию без временных интервалов")
            if (member is not None and member.get("отношение_к_школе") not in primary["область_применения"]
                    or person_id in primary["исключённые_персоны"]):
                error("primary_ineligible", path, "Персона находится вне области применения основного деления")

    if primary is not None:
        for i, person_id in enumerate(primary["исключённые_персоны"]):
            ref(person_id, {"персона"}, f"/классификации/основное_деление/исключённые_персоны/{i}")
    for facet, path, values_key in classified:
        for i, value in enumerate(facet.get(values_key, [])):
            if value.get("объект") is not None:
                ref(value["объект"], entity_kinds, f"{path}/{values_key}/{i}/объект")

    # Опорными утверждениями служат сведения и связи. Включение в состав
    # и классификация являются редакторскими решениями, а не независимыми свидетельствами.
    graph: dict[str, list[str]] = {}
    for kind, entries, prefix in arrays:
        if kind not in {"сведение", "связь", "состав", "назначение"}:
            continue
        for i, record in enumerate(entries):
            targets = record.get("опирается_на", [])
            graph[record["id"]] = targets
            for j, target in enumerate(targets):
                ref(target, {"сведение", "связь"}, f"{prefix}/{i}/опирается_на/{j}")
    state: dict[str, int] = {}
    def visit(identifier: str) -> None:
        state[identifier] = 1
        for target in graph.get(identifier, []):
            if target not in graph:
                continue
            if state.get(target) == 1:
                error("dependency_cycle", records[identifier][2] + "/опирается_на",
                      f"Цикл зависимостей проходит через {target!r}")
            elif state.get(target, 0) == 0:
                visit(target)
        state[identifier] = 2
    for identifier in graph:
        if state.get(identifier, 0) == 0:
            visit(identifier)

    center = doc.get("отображение", {}).get("центр", {})
    if center.get("id") is not None:
        kinds = {"персона"} if center.get("тип") == "персона" else {"школа"}
        ref(center["id"], kinds, "/отображение/центр/id")
        if center.get("тип") == "школа" and center["id"] != school_id:
            error("center_school_mismatch", "/отображение/центр/id", "Центр должен ссылаться на описываемую школу")

    if doc.get("метаданные", {}).get("статус") == "готово":
        has_identity = all(school.get(key) for key in (
            "идентификатор_школы", "каноническое_название", "границы_описания"))
        has_content = any(record.get("решение") == "принято" for record in
                          doc.get("сведения", []) + doc.get("связи", []))
        if not has_identity or not doc.get("источники") or not has_content:
            error("empty_ready", "/метаданные/статус",
                  "Готовый документ требует идентификации, границ описания, источника и принятых содержательных записей")
    return issues



def _extra_semantic_checks(document: Mapping[str, Any]) -> list[str]:
    errors = []
    dictionaries = document["словари"]
    for key in ("поля_сведений", "типы_связей"):
        codes = [item["код"] for item in dictionaries[key]]
        if len(codes) != len(set(codes)):
            errors.append(f"Словарь {key}: повторяющиеся коды")
    fields = {item["код"]: item for item in dictionaries["поля_сведений"]}
    main_counts = Counter((item["субъект"], item["поле"]) for item in document["сведения"]
                          if item["решение"] == "принято" and item["роль_значения"] == "основное")
    for (subject, field), count in main_counts.items():
        if fields.get(field, {}).get("кардинальность") == "одно_основное" and count > 1:
            errors.append(f"Сведение {subject}/{field}: более одного основного значения")
    known_fields = set(fields)
    known_dimensions = set(dimension_definitions(document, include_primary=False))
    for code in document["отображение"]["поля_карточки"]:
        if code not in known_fields:
            errors.append(f"Неизвестное поле карточки: {code}")
    for column in document["отображение"]["колонки_таблицы_по_умолчанию"]:
        if column.startswith("field:") and column[6:] not in known_fields:
            errors.append(f"Неизвестное поле таблицы: {column}")
        if column.startswith("facet:") and column[6:] not in known_dimensions:
            errors.append(f"Неизвестный фильтр таблицы: {column}")
    center = document["отображение"]["центр"]
    if center["тип"] == "персона" and center["id"] is not None:
        if center["id"] not in {p["id"] for p in display_persons(document)}:
            errors.append("Центральная персона должна быть включена в отображаемый состав школы")
    # Принятая запись может опираться только на принятое утверждение.
    assertions = {r["id"]: r for key in ("сведения", "связи") for r in document[key]}
    for key in ("сведения", "связи", "состав", "классификационные_назначения"):
        for record in document[key]:
            if record["решение"] in {"принято", "включено"}:
                for target in record.get("опирается_на", []):
                    if target in assertions and assertions[target]["решение"] != "принято":
                        errors.append(f"Принятая запись {record['id']} опирается на непринятую {target}")
    return errors


def _date_issues(document: Mapping[str, Any]) -> list[str]:
    """Проверяет компоненты действующих дат, сохраняя архивные исходные написания."""
    errors = []
    def date_range(value: Mapping[str, Any], maximum: bool = False):
        year = value.get("год")
        if year is None or value.get("эра") is None or value.get("определённость") != "точно":
            return None
        year = -year if value["эра"] == "до_н_э" else year
        month = value.get("месяц") or (12 if maximum else 1)
        day = value.get("день") or (31 if maximum else 1)
        return year, month, day
    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}/{index}")
        elif isinstance(value, dict):
            if {"год", "месяц", "день", "эра", "точность", "определённость"}.issubset(value):
                year, month, day = value["год"], value["месяц"], value["день"]
                if month and day:
                    max_day = 29 if month == 2 else (30 if month in {4, 6, 9, 11} else 31)
                    cal = value.get("календарь")
                    if month == 2 and year and cal in {"григорианский", "юлианский"}:
                        astronomical_year = 1 - year if value["эра"] == "до_н_э" else year
                        leap = calendar.isleap(astronomical_year) if cal == "григорианский" else astronomical_year % 4 == 0
                        max_day = 29 if leap else 28
                    if day > max_day:
                        errors.append(f"{path}: невозможный день месяца")
                if value["точность"] == "год" and (month is not None or day is not None):
                    errors.append(f"{path}: точность до года несовместима с указанным месяцем/днём")
                if value["точность"] == "месяц" and day is not None:
                    errors.append(f"{path}: точность до месяца несовместима с указанным днём")
            if {"начало", "конец", "исходная_запись"}.issubset(value):
                start, end = value["начало"], value["конец"]
                if start.get("состояние") == end.get("состояние") == "известна":
                    earliest_start = date_range(start["дата"])
                    latest_end = date_range(end["дата"], maximum=True)
                    if earliest_start and latest_end and earliest_start > latest_end:
                        errors.append(f"{path}: конец интервала предшествует началу")
            for key, item in value.items():
                if key not in {"старое_значение", "новое_значение", "параметры"}:
                    walk(item, f"{path}/{key}")
    walk(dict(document))
    return errors


def _ready_issues(document: Mapping[str, Any]) -> list[str]:
    """Готовый документ требует проверенных прослеживаемых оснований; черновики допускают пробелы."""
    if document["метаданные"]["статус"] != "готово":
        return []
    errors = []
    bases = {r["id"]: r for r in document["основания"]}
    sources = {r["id"]: r for r in document["источники"]}
    assertions = {r["id"]: r for key in ("сведения", "связи") for r in document[key]}
    used_bases, inherited = set(), []
    def check_review(record: Mapping[str, Any], label: str) -> None:
        review = record.get("проверка", {})
        if review.get("статус") == "унаследовано":
            inherited.append(record)
            if not review.get("примечание") or not record.get("происхождение"):
                errors.append(f"{label}: унаследованная проверка требует оговорки и происхождения")
        elif review.get("статус") != "сверено":
            errors.append(f"{label}: действующая запись не сверена")
    def support(record: Mapping[str, Any], visited: set[str]) -> set[str]:
        result = set(record.get("основания", []))
        for target in record.get("опирается_на", []):
            if target not in visited and target in assertions:
                result.update(support(assertions[target], visited | {target}))
        return result
    for key in ("сведения", "связи", "состав", "классификационные_назначения"):
        for record in document[key]:
            if record["решение"] not in {"принято", "включено"}:
                continue
            check_review(record, record["id"])
            evidence_ids = support(record, {record["id"]})
            if not evidence_ids:
                errors.append(f"{record['id']}: отсутствует источниковая опора")
            used_bases.update(evidence_ids)
    for eid in sorted(used_bases):
        evidence = bases[eid]
        check_review(evidence, eid)
        check_review(sources[evidence["источник"]], evidence["источник"])
        if evidence["область_ссылки"] == "не_установлена" or (
            evidence["область_ссылки"] == "конкретное_место" and evidence["локатор"] is None
        ):
            errors.append(f"{eid}: не установлен адрес источниковой опоры")
    if inherited:
        admitted_ids = {ref["id"] for decision in document["редактура"]["журнал_решений"]
                        if decision.get("принятое_решение") and decision["проверка"]["статус"] == "сверено"
                        for ref in decision["записи"]}
        for record in inherited:
            if record["id"] not in admitted_ids:
                errors.append(f"{record['id']}: нет проверенного редакторского решения о допуске унаследованной проверки")
    return errors


@lru_cache(maxsize=4)
def _schema_validator(path: str, modified: int) -> Draft202012Validator:
    try:
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    except (OSError, ValueError) as exc:
        raise SourceSchoolDataError("Не удалось прочитать схему школ v2.1") from exc


def validate_source_school_document(document: Mapping[str, Any]) -> None:
    """Проверяет форму документа, затем ссылки и правила основного деления."""
    if not isinstance(document, Mapping) or document.get("версия_схемы") != "2.1":
        raise SourceSchoolDataError("Школа должна использовать единый формат JSON версии 2.1")
    try:
        validator = _schema_validator(str(SOURCE_SCHOOLS_SCHEMA_PATH), SOURCE_SCHOOLS_SCHEMA_PATH.stat().st_mtime_ns)
    except OSError as exc:
        raise SourceSchoolDataError("Схема школ v2.1 не найдена") from exc
    errors = sorted(validator.iter_errors(document), key=lambda e: str(list(e.absolute_path)))
    if errors:
        error = errors[0]
        path = "/".join(map(str, error.absolute_path)) or "документ"
        raise SourceSchoolDataError(f"Неверная структура JSON ({path}): {error.message}")
    issues = _semantic_issues(dict(document))
    if issues:
        raise SourceSchoolDataError("Нарушена связность JSON: " + "; ".join(f"{e.path}: {e.message}" for e in issues[:5]))
    extra_errors = _extra_semantic_checks(document) + _date_issues(document) + _ready_issues(document)
    if extra_errors:
        raise SourceSchoolDataError("; ".join(extra_errors[:5]))


def normalize_source_school_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Возвращает независимый документ v2.1 без преобразования прежнего формата."""
    return copy.deepcopy(dict(document))


def build_source_school_index(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Индексирует исходные записи без выведения принадлежностей и копирования прежних полей."""
    return {
        "persons": {r["id"]: r for r in document["объекты"]["персоны"]},
        "objects": {r["id"]: r for r in document["объекты"]["прочие"]},
        "sources": {r["id"]: r for r in document["источники"]},
        "evidence": {r["id"]: r for r in document["основания"]},
        "information": {r["id"]: r for r in document["сведения"]},
        "relations": {r["id"]: r for r in document["связи"]},
        "memberships": membership_index(document),
        "dimensions": dimension_definitions(document),
        "assignments": {r["id"]: r for r in document["классификационные_назначения"]},
    }


def build_source_school_summary(document: Mapping[str, Any]) -> dict[str, Any]:
    members = document["состав"]
    included = [m for m in members if m["решение"] == "включено"]
    primary = document["классификации"]["основное_деление"]
    category_counts = {c["id"]: 0 for c in primary["категории"]} if primary else {}
    if primary:
        for assignment in accepted_assignments(document, dimension_id=primary["id"]):
            category_counts[assignment["значение"]] += 1
    result = {
        "person_count": len(document["объекты"]["персоны"]),
        "included_count": len(included),
        "displayed_count": len(display_persons(document)),
        "representative_count": sum(m["отношение_к_школе"] == "представитель" for m in included),
        "related_count": sum(m["отношение_к_школе"] == "связанное_лицо" for m in included),
        "candidate_count": sum(m["решение"] == "кандидат" for m in members),
        "source_count": len(document["источники"]),
        "evidence_count": len(document["основания"]),
        "relation_count": sum(r["решение"] == "принято" for r in document["связи"]),
        "assignment_count": len(accepted_assignments(document)),
        "flexible_assignment_count": sum(a["измерение"] != (primary or {}).get("id") for a in accepted_assignments(document)),
        "primary_assignment_count": sum(category_counts.values()),
        "primary_counts": category_counts,
        "status": document["метаданные"]["статус"],
    }
    result.update({"число_персон": result["included_count"], "число_источников": result["source_count"],
                   "число_подтверждений": result["evidence_count"], "персоны_по_категориям": category_counts})
    return result


def load_source_school_document(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SourceSchoolDataError(f"Не удалось прочитать JSON школы {path.name}: {exc}") from exc
    validate_source_school_document(document)
    return document


# Псевдоним API: прежний формат v1 не читается и не преобразуется.
load_source_school_file = load_source_school_document


@lru_cache(maxsize=4)
def _cached_catalog(directory_text: str, signature: tuple[tuple[str, int, int], ...], schema_modified: int) -> list[dict[str, Any]]:
    directory = Path(directory_text)
    entries, seen = [], set()
    for path in sorted(directory.glob("*.json")):
        document = load_source_school_document(path)
        if document["метаданные"]["статус"] == "шаблон":
            continue
        school = document["школа"]
        identifier = school["идентификатор_школы"]
        if identifier in seen:
            raise SourceSchoolDataError(f"Повторяющийся идентификатор школы: {identifier}")
        seen.add(identifier)
        entries.append({"school_id": identifier, "label": school["каноническое_название"],
                        "path": str(path), "document": document, "status": document["метаданные"]["статус"]})
    return entries


def load_source_school_catalog(data_dir: Path | str | None = None, *, directory: Path | str | None = None) -> list[dict[str, Any]]:
    directory = Path(directory or data_dir or SOURCE_SCHOOLS_DATA_DIR)
    if not directory.exists():
        return []
    try:
        signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns)
                          for path in sorted(directory.glob("*.json")))
        schema_modified = SOURCE_SCHOOLS_SCHEMA_PATH.stat().st_mtime_ns
    except OSError as exc:
        raise SourceSchoolDataError("Не удалось прочитать каталог или схему школ") from exc
    # Изменение возвращённой копии не влияет на последующие загрузки.
    return copy.deepcopy(_cached_catalog(str(directory.resolve()), signature, schema_modified))
