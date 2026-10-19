"""Осторожное сопоставление участников источниковых школ с деревьями научного руководства."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from core.db import SUPERVISOR_COLUMNS
from core.lineage.graph import rows_for
from core.lineage.names import has_expanded_name, norm

# Пересчитываем и ранее отсутствовавшие ссылки после обновления правил сопоставления.
_MATCHING_POLICY_REVISION = 2


@dataclass(frozen=True)
class SourcePersonLineage:
    root_name: str
    record_count: int


def _fully_named(name: str) -> bool:
    parts = norm(name).split()
    return has_expanded_name(name) and all(len(part) > 1 for part in parts)


def source_person_name_candidates(name: str) -> tuple[str, ...]:
    """Учитывает порядок полного имени и фамилии в скобках, не разворачивая инициалы."""
    aliases = re.findall(r"\(([^()]*)\)", name)
    plain = re.sub(r"\([^()]*\)", "", name).strip()
    parts = plain.split()
    candidates = [plain]
    if len(parts) >= 2:
        candidates.append(" ".join([parts[-1], *parts[:-1]]))
        candidates.append(" ".join([*parts[1:], parts[0]]))
        for alias in aliases:
            if len(alias.split()) == 1:
                candidates.append(" ".join([alias, *parts[:-1]]))
    return tuple(dict.fromkeys(candidate for candidate in candidates if _fully_named(candidate)))


def _valid_basis_ids(document):
    sources = {str(s.get("id")) for s in document.get("источники", [])}
    return {
        str(b["id"]) for b in document.get("основания", [])
        if b.get("источник") in sources
        and b.get("проверка", {}).get("статус") in {"сверено", "частично_сверено", "унаследовано"}
        and (b.get("локатор") or b.get("область_ссылки") == "источник_в_целом")
    }


def _grounded(item, valid_bases):
    refs = item.get("основания", [])
    # Дополнительная архивная ссылка без локатора не отменяет адресные подтверждения.
    return any(str(ref) in valid_bases for ref in refs)


def _person_candidates(person, valid_bases):
    """Общий внешний идентификатор сам по себе не устанавливает тождество с генеалогией.

    Пространство имён academic_genealogy:root_name позволяет явно сохранить
    подтверждённое вручную полное имя корня из базы с адресным основанием.
    """
    candidates = []
    identification = person.get("идентификация", {})
    if identification.get("статус") == "установлена" and _grounded(identification, valid_bases):
        candidates.extend(source_person_name_candidates(str(person.get("имя", ""))))
        for alias in person.get("варианты_имени", []):
            if isinstance(alias, Mapping) and _grounded(alias, valid_bases):
                candidates.extend(source_person_name_candidates(str(alias.get("написание", ""))))
    for identifier in person.get("внешние_идентификаторы", []):
        if (identifier.get("система") == "academic_genealogy:root_name"
                and identifier.get("решение") == "подтверждено"
                and _grounded(identifier, valid_bases)):
            candidates.extend(source_person_name_candidates(str(identifier.get("значение", ""))))
    return tuple(dict.fromkeys(candidates))


def resolve_source_school_lineages(
    document: Mapping[str, Any], df: pd.DataFrame, idx: dict,
) -> dict[str, SourcePersonLineage]:
    """Сопоставляет подтверждённые имена только с существующими однозначными деревьями руководства."""
    names_by_key: dict[str, set[str]] = {}
    for column in SUPERVISOR_COLUMNS:
        if column in df:
            for raw in df[column].dropna().astype(str).unique():
                name = raw.strip()
                if name and _fully_named(name):
                    names_by_key.setdefault(norm(name), set()).add(name)
    valid_bases = _valid_basis_ids(document)
    included = {str(m.get("персона")) for m in document.get("состав", []) if m.get("решение") == "включено"}
    links: dict[str, SourcePersonLineage] = {}
    for person in document.get("объекты", {}).get("персоны", []):
        if str(person.get("id")) not in included:
            continue
        matched_keys = {
            norm(candidate) for candidate in _person_candidates(person, valid_bases)
            if norm(candidate) in names_by_key
        }
        if len(matched_keys) != 1:
            continue
        root = sorted(names_by_key[next(iter(matched_keys))])[0]
        records = rows_for(df, idx, root)
        count = records["Code"].nunique() if "Code" in records else len(records)
        if count:
            links[str(person["id"])] = SourcePersonLineage(root_name=root, record_count=int(count))
    return links


@st.cache_data(show_spinner=False)
def _cached_source_school_lineages(db_signature, scope_signature, document_json, matching_policy_revision, _df, _idx):
    return resolve_source_school_lineages(json.loads(document_json), _df, _idx)


def get_source_school_lineages(document, df, idx, db_signature) -> dict[str, SourcePersonLineage]:
    """Обновляет кэш при изменении данных, идентификации или правил сопоставления."""
    relevant = {
        "объекты": {"персоны": document.get("объекты", {}).get("персоны", [])},
        "состав": document.get("состав", []),
        "источники": [{"id": s.get("id")} for s in document.get("источники", [])],
        "основания": document.get("основания", []),
    }
    columns = [column for column in ["Code", *SUPERVISOR_COLUMNS] if column in df]
    hashes = pd.util.hash_pandas_object(df[columns], index=True).values.tobytes()
    scope_signature = hashlib.sha256(hashes).hexdigest()
    return _cached_source_school_lineages(
        db_signature, scope_signature, json.dumps(relevant, ensure_ascii=False, sort_keys=True),
        _MATCHING_POLICY_REVISION, df, idx,
    )
