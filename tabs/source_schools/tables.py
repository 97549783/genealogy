"""Совместимый импорт таблиц школ по источникам из общего слоя."""
from core.source_schools.tables import (
    build_evidence_dataframe,
    build_people_dataframe,
    build_sources_dataframe,
    filter_people_dataframe,
    resolve_person_names,
)

__all__ = [
    "build_evidence_dataframe",
    "build_people_dataframe",
    "build_sources_dataframe",
    "filter_people_dataframe",
    "resolve_person_names",
]
