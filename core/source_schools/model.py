"""Чтение универсального документа школы без изменения данных: схема 2.1.

Вспомогательные функции возвращают представления, не записывая их в исходный JSON.
Списки персон и фильтры определяются решениями о включении в состав
и принятыми классификационными назначениями. Связи не означают членства в школе.
"""
from __future__ import annotations

from typing import Any, Mapping

MEMBERSHIP_GROUP_LABELS = {
    "представитель": "Представители",
    "связанное_лицо": "Связанные лица",
    "не_установлено": "Отношение к школе не установлено",
}


def uses_membership_division(document: Mapping[str, Any]) -> bool:
    """Основные ветви берутся из состава, если не задано отдельное основное деление."""
    return (document.get("классификации", {}).get("основное_деление") is None
            and document.get("отображение", {}).get("без_основного_деления") == "по_отношению_к_школе")


def school_id(document: Mapping[str, Any]) -> str:
    return str(document["школа"]["идентификатор_школы"])


def included_persons(document: Mapping[str, Any], *, include_related: bool = True) -> list[Mapping[str, Any]]:
    memberships = {m["персона"]: m for m in document.get("состав", [])}
    return [p for p in document.get("объекты", {}).get("персоны", [])
            if (m := memberships.get(p["id"])) and m.get("решение") == "включено"
            and (include_related or m.get("отношение_к_школе") == "представитель")]


def membership_index(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {m["персона"]: m for m in document.get("состав", [])}


def display_persons(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Включённый состав с учётом заданных школой отображаемых отношений."""
    allowed = document.get("отображение", {}).get("показывать_отношения_к_школе", ["представитель", "связанное_лицо", "не_установлено"])
    memberships = membership_index(document)
    return [p for p in included_persons(document) if memberships[p["id"]]["отношение_к_школе"] in allowed]


def field_definitions(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {f["код"]: f for f in document.get("словари", {}).get("поля_сведений", [])}


def dimension_definitions(document: Mapping[str, Any], *, include_primary: bool = True) -> dict[str, Mapping[str, Any]]:
    classifications = document.get("классификации", {})
    definitions = []
    primary = classifications.get("основное_деление")
    if include_primary and primary:
        definitions.append(primary)
    definitions.extend(sorted(classifications.get("гибкие_измерения", []), key=lambda d: d["порядок"]))
    return {d["id"]: d for d in definitions}


def accepted_assignments(document: Mapping[str, Any], *, person_id: str | None = None,
                         dimension_id: str | None = None) -> list[Mapping[str, Any]]:
    included = {p["id"] for p in included_persons(document)}
    return [a for a in document.get("классификационные_назначения", [])
            if a.get("решение") == "принято" and a.get("персона") in included
            and (person_id is None or a["персона"] == person_id)
            and (dimension_id is None or a["измерение"] == dimension_id)]


def accepted_information(document: Mapping[str, Any], subject: str | None = None,
                         field: str | None = None, *, include_variants: bool = False) -> list[Mapping[str, Any]]:
    return sorted([r for r in document.get("сведения", [])
                   if r.get("решение") == "принято"
                   and (include_variants or r.get("роль_значения") != "вариант")
                   and (subject is None or r["субъект"] == subject)
                   and (field is None or r["поле"] == field)], key=lambda r: r["порядок"])


def format_date(value: Mapping[str, Any] | None) -> str:
    if not value:
        return ""
    if value.get("исходная_запись"):
        return str(value["исходная_запись"])
    year = str(value.get("год") or "")
    if value.get("эра") == "до_н_э" and year:
        year += " до н. э."
    return year


def format_value(value: Mapping[str, Any] | None) -> str:
    if not value:
        return ""
    kind, raw = value.get("вид"), value.get("значение")
    if kind == "дата":
        return format_date(raw)
    if kind == "интервал":
        if raw.get("исходная_запись"):
            return str(raw["исходная_запись"])
        def bound(name: str) -> str:
            boundary = raw.get(name, {})
            return format_date(boundary.get("дата")) if boundary.get("состояние") == "известна" else "…"
        return f"{bound('начало')} — {bound('конец')}"
    if kind == "логическое":
        return "Да" if raw else "Нет"
    return "" if raw is None else str(raw)


def information_text(document: Mapping[str, Any], subject: str, field: str, *, include_variants: bool = False) -> str:
    return "\n\n".join(format_value(r["значение"]) for r in accepted_information(
        document, subject, field, include_variants=include_variants))


def format_locator(locator: Mapping[str, Any] | None) -> str:
    if not locator:
        return ""
    parts = []
    if locator.get("печатные_страницы"):
        parts.append("с. " + ", ".join(map(str, locator["печатные_страницы"])))
    if locator.get("страницы_pdf"):
        parts.append("PDF " + ", ".join(map(str, locator["страницы_pdf"])))
    parts.extend(str(locator[key]) for key in ("обозначение", "раздел", "архивный_шифр", "временная_метка", "якорь") if locator.get(key))
    return "; ".join(parts)


def primary_category_index(document: Mapping[str, Any]) -> dict[str, str]:
    """Сопоставляет ID включённых персон с названиями принятых основных категорий."""
    primary = document.get("классификации", {}).get("основное_деление")
    if not primary:
        return {}
    labels = {c["id"]: c["название"] for c in primary["категории"]}
    return {a["персона"]: labels[a["значение"]] for a in accepted_assignments(document, dimension_id=primary["id"])}


def person_basis_ids(document: Mapping[str, Any], person_id: str) -> tuple[str, ...]:
    """Разрешает прямые основания и зависимости утверждений без повторного учёта."""
    assertions = {r["id"]: r for key in ("сведения", "связи") for r in document.get(key, [])}
    records = []
    person = next((p for p in document.get("объекты", {}).get("персоны", []) if p["id"] == person_id), {})
    records.append(person.get("идентификация", {}))
    records.extend(person.get("варианты_имени", []))
    records.extend(m for m in document.get("состав", []) if m["персона"] == person_id)
    records.extend(r for r in document.get("сведения", []) if r["субъект"] == person_id and r["решение"] == "принято")
    records.extend(r for r in document.get("связи", []) if person_id in (r["от"], r["к"]) and r["решение"] == "принято")
    records.extend(accepted_assignments(document, person_id=person_id))
    bases, visited = set(), set()
    def collect(record: Mapping[str, Any]) -> None:
        bases.update(record.get("основания", []))
        for identifier in record.get("опирается_на", []):
            if identifier not in visited and identifier in assertions:
                visited.add(identifier)
                collect(assertions[identifier])
    for record in records:
        collect(record)
    return tuple(e["id"] for e in document.get("основания", []) if e["id"] in bases)


def person_source_ids(document: Mapping[str, Any], person_id: str) -> tuple[str, ...]:
    bases = set(person_basis_ids(document, person_id))
    sources = {e["источник"] for e in document.get("основания", []) if e["id"] in bases}
    return tuple(s["id"] for s in document.get("источники", []) if s["id"] in sources)


def person_qualifications(document: Mapping[str, Any], person_id: str) -> str:
    """Сохраняет неопределённость и варианты при экспорте персон без выбора основной версии."""
    person = next((p for p in document["объекты"]["персоны"] if p["id"] == person_id), {})
    records = [person, person.get("идентификация", {})]
    records.extend(m for m in document["состав"] if m["персона"] == person_id)
    records.extend(r for r in document["сведения"] if r["субъект"] == person_id)
    records.extend(r for r in document["связи"] if person_id in (r["от"], r["к"]))
    records.extend(a for a in document["классификационные_назначения"] if a["персона"] == person_id)
    parts = []
    for record in records:
        if record.get("примечание"):
            parts.append(record["примечание"])
        parts.extend(record.get("ограничения", []))
    fields = field_definitions(document)
    for record in records:
        if record.get("роль_значения") == "вариант":
            label = fields.get(record["поле"], {}).get("название", record["поле"])
            parts.append(f"Вариант ({label}; {record['решение']}): {format_value(record['значение'])}")
    record_ids = {r["id"] for r in records if "id" in r}
    for disagreement in document["редактура"]["разночтения"]:
        if any(ref["id"] in record_ids for variant in disagreement["варианты"] for ref in variant["записи"]):
            variants = "; ".join(v["формулировка"] for v in disagreement["варианты"])
            parts.append(f"{disagreement['тема']}: {variants}")
            if disagreement.get("редакторское_решение"):
                parts.append(disagreement["редакторское_решение"])
    return "\n\n".join(dict.fromkeys(parts))
