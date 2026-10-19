"""Универсальные данные школ по источникам: JSON Schema 2.1."""
from .data import (
    SOURCE_SCHOOLS_DATA_DIR,
    SourceSchoolDataError,
    build_source_school_index,
    build_source_school_summary,
    load_source_school_catalog,
    load_source_school_document,
    validate_source_school_document,
)

__all__ = [
    "SOURCE_SCHOOLS_DATA_DIR", "SourceSchoolDataError", "build_source_school_index",
    "build_source_school_summary", "load_source_school_catalog", "load_source_school_document",
    "validate_source_school_document",
]
