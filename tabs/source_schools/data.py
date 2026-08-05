"""Совместимый импорт загрузчика школ по источникам из общего слоя."""
from core.source_schools.data import (
    SOURCE_SCHOOLS_DATA_DIR,
    SUPPORTED_SCHEMA_KEYS,
    SourceSchoolDataError,
    build_source_school_index,
    load_source_school_catalog,
    load_source_school_file,
    validate_source_school_document,
)

__all__ = [
    "SOURCE_SCHOOLS_DATA_DIR",
    "SUPPORTED_SCHEMA_KEYS",
    "SourceSchoolDataError",
    "build_source_school_index",
    "load_source_school_catalog",
    "load_source_school_file",
    "validate_source_school_document",
]
