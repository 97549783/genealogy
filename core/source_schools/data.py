"""Загрузка, нормализация и проверка статических школ по источникам."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import streamlit as st

SOURCE_SCHOOLS_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "source_schools"
SUPPORTED_SCHEMA_KEYS: tuple[str, ...] = (
    "школа",
    "демо_представление",
    "контроль_качества",
    "_processing_metadata",
)
SUMMARY_ALIASES = {
    "число_персон": ("число_персон", "количество_персон"),
    "число_источников": ("число_источников", "количество_источников"),
    "число_подтверждений": ("число_подтверждений", "количество_подтверждений"),
    "персоны_по_категориям": ("персоны_по_категориям", "по_категориям"),
}


class SourceSchoolDataError(ValueError):
    """Ошибка структуры или связности данных школы по источникам."""


def _field(mapping: Mapping[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("название", "название_направления", "значение", "описание", "текст"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text
        return "; ".join(f"{key}: {_as_text(item)}" for key, item in value.items() if item)
    if isinstance(value, list):
        return "; ".join(_as_text(item) for item in value if _as_text(item))
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


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


def _require_item_mapping(item: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(item, Mapping):
        raise SourceSchoolDataError(f"Элемент списка {label} должен быть объектом.")
    return item


def _unique(items: list[Any], label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for raw_item in items:
        item = _require_item_mapping(raw_item, label)
        ident = item.get("id")
        if not isinstance(ident, str) or not ident.strip():
            raise SourceSchoolDataError(f"В списке {label} найден пустой идентификатор.")
        if ident in result:
            raise SourceSchoolDataError(f"Обнаружен повторяющийся идентификатор {label}: {ident}.")
        result[ident] = item
    return result


def _status_to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").lower()
    return "яв" in text and "вывед" not in text and "интерпр" not in text


def normalize_source_school_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Возвращает копию документа с совместимыми служебными полями для интерфейса."""
    normalized = copy.deepcopy(dict(document))
    school = normalized.get("школа")
    if not isinstance(school, dict):
        return normalized

    for person in school.get("персоны", []) if isinstance(school.get("персоны"), list) else []:
        if not isinstance(person, dict):
            continue
        person.setdefault("полное_имя", _field(person, "имя", "name"))
        person.setdefault("годы_жизни", _field(person, "даты", "годы"))
        person.setdefault("основной_вклад", _field(person, "основные_идеи_или_вклад", "вклад"))
        person["роль_в_школе"] = _as_list(person.get("роль_в_школе"))
        person["группы_и_контексты"] = [_as_text(item) for item in _as_list(person.get("группы_и_контексты"))]
        for attribution in person.get("источниковые_атрибуции", []):
            if isinstance(attribution, dict):
                attribution.setdefault(
                    "явное_утверждение",
                    _status_to_bool(attribution.get("явное_или_выведенное")),
                )

    for evidence in school.get("подтверждения", []) if isinstance(school.get("подтверждения"), list) else []:
        if isinstance(evidence, dict):
            evidence.setdefault(
                "явное_утверждение",
                _status_to_bool(evidence.get("явное_или_выведенное")),
            )

    return normalized


def build_source_school_index(document: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Строит индексы персон, источников, подтверждений и групп по ID."""
    normalized = normalize_source_school_document(document)
    school = normalized["школа"]
    structure = school.get("внутренняя_структура", {})
    return {
        "persons": _unique(school.get("персоны", []), "персоны"),
        "sources": _unique(school.get("источники", []), "источника"),
        "evidence": _unique(school.get("подтверждения", []), "подтверждения"),
        "groups": _unique(structure.get("исследовательские_группы", []), "исследовательской группы"),
    }


def _check_confidence(value: Any, where: str) -> None:
    if value is None or value == "":
        return
    if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
        raise SourceSchoolDataError(f"Некорректная уверенность в поле {where}.")


def _check_person_ids(values: list[Any], persons: Mapping[str, Any], where: str) -> None:
    for ident in values or []:
        if ident not in persons:
            raise SourceSchoolDataError(f"Неизвестная персона в поле {where}: {ident}.")


def _summary_value(block: Mapping[str, Any], canonical_key: str) -> Any:
    for key in SUMMARY_ALIASES[canonical_key]:
        if key in block:
            return block[key]
    return None


def _validate_summary(block_name: str, block: Mapping[str, Any], counts: Mapping[str, Any]) -> None:
    for key, value in counts.items():
        actual = _summary_value(block, key)
        if actual is None and block_name == "контроль_качества" and key == "персоны_по_категориям":
            continue
        if actual != value:
            raise SourceSchoolDataError(f"Сводные показатели устарели: {block_name}.{key}.")


def validate_source_school_document(document: Mapping[str, Any]) -> None:
    """Проверяет обязательные поля, идентификаторы и ссылки."""
    if not isinstance(document, Mapping):
        raise SourceSchoolDataError("Файл школы должен содержать JSON-объект.")
    normalized = normalize_source_school_document(document)
    school = _require_mapping(normalized, "школа")
    demo = _require_mapping(normalized, "демо_представление")
    quality = _require_mapping(normalized, "контроль_качества")

    for key in ("идентификатор_школы", "каноническое_название"):
        _require_text(school, key)
    for key in ("персоны", "источники", "подтверждения", "историографические_расхождения"):
        _require_list(school, key)
    _require_mapping(school, "внутренняя_структура")
    for key in (
        "название_в_выпадающем_списке",
        "заголовок_страницы",
        "подзаголовок",
        "методологическое_предупреждение",
    ):
        _require_text(demo, key)
    _require_list(demo, "рекомендуемые_разделы")

    indexes = build_source_school_index(normalized)
    persons = indexes["persons"]
    sources = indexes["sources"]
    evidence = indexes["evidence"]

    for source in sources.values():
        url = source.get("url")
        if url is not None and not isinstance(url, str):
            raise SourceSchoolDataError(f"Некорректный URL источника: {source.get('id')}.")
        if url and urlparse(url).scheme and urlparse(url).scheme not in {"http", "https"}:
            raise SourceSchoolDataError(f"Источник {source.get('id')} содержит небезопасную ссылку.")

    for evidence_record in evidence.values():
        source_id = evidence_record.get("идентификатор_источника")
        if source_id not in sources:
            raise SourceSchoolDataError(
                f"Подтверждение {evidence_record.get('id')} ссылается на неизвестный источник: {source_id}."
            )
        _check_confidence(evidence_record.get("уверенность"), f"подтверждения.{evidence_record.get('id')}")

    for person in persons.values():
        person_id = person.get("id")
        for evidence_id in person.get("подтверждения", []):
            if evidence_id not in evidence:
                raise SourceSchoolDataError(
                    f"Персона {person_id} ссылается на неизвестное подтверждение: {evidence_id}."
                )
        _check_confidence(person.get("уверенность"), f"персоны.{person_id}")
        for attribution in person.get("источниковые_атрибуции", []):
            if not isinstance(attribution, Mapping):
                raise SourceSchoolDataError(f"Атрибуция персоны {person_id} должна быть объектом.")
            source_id = attribution.get("идентификатор_источника")
            evidence_id = attribution.get("подтверждение")
            if source_id not in sources:
                raise SourceSchoolDataError(f"Персона {person_id} ссылается на неизвестный источник: {source_id}.")
            if evidence_id not in evidence:
                raise SourceSchoolDataError(
                    f"Персона {person_id} ссылается на неизвестное подтверждение: {evidence_id}."
                )
            if evidence[evidence_id].get("идентификатор_источника") != source_id:
                raise SourceSchoolDataError(
                    f"Атрибуция персоны {person_id} связывает источник {source_id} с подтверждением другого источника: {evidence_id}."
                )
            _check_confidence(attribution.get("уверенность"), f"атрибуции.{person_id}")

    structure = school["внутренняя_структура"]
    for group in structure.get("исследовательские_группы", []):
        _check_person_ids(group.get("участники", []), persons, f"группа {group.get('id')}")
        for evidence_id in group.get("подтверждения", []):
            if evidence_id not in evidence:
                raise SourceSchoolDataError(
                    f"Группа {group.get('id')} ссылается на неизвестное подтверждение: {evidence_id}."
                )
    for item in structure.get("направления", []):
        _check_person_ids(_as_list(_field(item, "представители", "участники")), persons, "направления")
    for item in structure.get("поколения", []):
        _check_person_ids(_as_list(_field(item, "представители", "участники")), persons, "поколения")
    for period in school.get("хронология", {}).get("периоды_развития", []):
        _check_person_ids(_as_list(_field(period, "персоны", "основные_представители")), persons, "хронология")
    for disagreement in school.get("историографические_расхождения", []):
        for position in disagreement.get("позиции", []):
            for source_id in position.get("источники", []):
                if source_id not in sources:
                    raise SourceSchoolDataError(
                        f"Историографическая позиция ссылается на неизвестный источник: {source_id}."
                    )

    counts: dict[str, Any] = {
        "число_персон": len(persons),
        "число_источников": len(sources),
        "число_подтверждений": len(evidence),
    }
    by_category: dict[str, int] = {}
    for person in persons.values():
        category = person.get("категория_включения", "")
        by_category[category] = by_category.get(category, 0) + 1
    counts["персоны_по_категориям"] = by_category
    _validate_summary("демо_представление.сводные_показатели", demo.get("сводные_показатели", {}), counts)
    _validate_summary("контроль_качества", quality, counts)


def load_source_school_file(path: Path) -> dict[str, Any]:
    """Загружает, нормализует и проверяет один JSON-файл."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceSchoolDataError(f"Файл школы содержит некорректный JSON: {path.name}.") from exc
    except FileNotFoundError as exc:
        raise SourceSchoolDataError(f"Файл школы не найден: {path.name}.") from exc
    except UnicodeDecodeError as exc:
        raise SourceSchoolDataError(f"Файл школы должен быть сохранён в UTF-8: {path.name}.") from exc
    except OSError as exc:
        raise SourceSchoolDataError(f"Не удалось прочитать файл школы: {path.name}.") from exc
    try:
        normalized = normalize_source_school_document(document)
        validate_source_school_document(normalized)
    except (AttributeError, TypeError, KeyError) as exc:
        raise SourceSchoolDataError(f"Файл школы имеет неподдерживаемую структуру: {path.name}.") from exc
    return normalized


def _catalog_signature(data_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not data_dir.exists():
        return ()
    return tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in sorted(data_dir.glob("*.json")))


@st.cache_data(show_spinner=False)
def _cached_catalog(path_text: str, signature: tuple[tuple[str, int, int], ...]) -> list[dict[str, Any]]:
    return _load_catalog_uncached(Path(path_text))


def _load_catalog_uncached(data_dir: Path) -> list[dict[str, Any]]:
    if not data_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for path in sorted(data_dir.glob("*.json")):
        document = load_source_school_file(path)
        school_id = document["школа"]["идентификатор_школы"]
        label = document["демо_представление"]["название_в_выпадающем_списке"]
        if school_id in seen_ids:
            raise SourceSchoolDataError(f"Обнаружен повторяющийся идентификатор школы: {school_id}.")
        if label in seen_labels:
            raise SourceSchoolDataError(f"Обнаружено повторяющееся название школы: {label}.")
        seen_ids.add(school_id)
        seen_labels.add(label)
        entries.append({"school_id": school_id, "label": label, "path": str(path), "document": document})
    return entries


def load_source_school_catalog(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Загружает и проверяет все JSON-файлы каталога."""
    directory = data_dir or SOURCE_SCHOOLS_DATA_DIR
    if data_dir is None:
        return _cached_catalog(str(directory), _catalog_signature(directory))
    return _load_catalog_uncached(directory)
