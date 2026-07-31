"""Доступ к базе извлечённых разделов характеристик диссертаций."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Collection
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from tabs.dissertation_characteristics.labels import SEARCHABLE_SECTION_KEYS, SECTION_LABELS_RU
from core.semantic.models import VectorMetadata

REQUIRED_TEXT_COLUMNS = {"text_id", "Code", "section_key", "section_order", "text", "text_hash", "matrix_row"}
REQUIRED_TABLES = {"dissertation_section_texts", "dissertation_vector_meta"}
SQL_BATCH_SIZE = 500
INDEX_COLUMNS = ["text_id", "Code", "section_key", "section_order", "matrix_row"]
TEXT_COLUMNS = ["text_id", "Code", "section_key", "section_order", "text", "text_hash", "matrix_row"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_dissertation_sections_db_path() -> Path:
    """Возвращает путь к отдельной базе разделов диссертаций."""
    env_path = os.getenv("DISSERTATION_SECTIONS_DB_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (_repo_root() / "data-nonsynchronized" / "dissertation_sections" / "dissertation_sections.db").resolve()


def get_dissertation_sections_connection() -> sqlite3.Connection:
    """Открывает соединение с базой разделов без изменения данных."""
    path = resolve_dissertation_sections_db_path()
    if not path.exists():
        raise FileNotFoundError(f"База разделов диссертаций не найдена: {path}")
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_dissertation_sections_db_signature() -> tuple[str, float, int] | None:
    """Возвращает подпись файла базы для сброса кэша Streamlit."""
    path = resolve_dissertation_sections_db_path()
    if not path.exists():
        return None
    stat = path.stat()
    return (str(path), stat.st_mtime, stat.st_size)


def _empty_index(include_text: bool = False) -> pd.DataFrame:
    columns = TEXT_COLUMNS if include_text else INDEX_COLUMNS
    return pd.DataFrame(columns=[*columns, "section_label"])


def _with_section_label(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        if "section_label" not in df.columns:
            df = df.copy()
            df["section_label"] = pd.Series(dtype="object")
        return df
    df = df.copy()
    df["section_label"] = df["section_key"].map(SECTION_LABELS_RU).fillna(df["section_key"])
    return df.reset_index(drop=True)


def _batched(values: tuple[str, ...], size: int = SQL_BATCH_SIZE):
    for start in range(0, len(values), size):
        yield values[start : start + size]


@st.cache_data(show_spinner=False)
def _load_vector_metadata_cached(db_signature: tuple[str, float, int] | None) -> dict[str, str]:
    """Загружает метаданные матрицы с учётом подписи базы."""
    if db_signature is None:
        return {}
    with get_dissertation_sections_connection() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "dissertation_vector_meta" not in tables:
            return {}
        rows = conn.execute("SELECT key, value FROM dissertation_vector_meta").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def load_vector_metadata() -> dict[str, str]:
    """Загружает метаданные матрицы векторов."""
    return _load_vector_metadata_cached(get_dissertation_sections_db_signature())


def load_typed_vector_metadata() -> VectorMetadata | None:
    """Возвращает типизированные метаданные текущей матрицы векторов."""
    metadata = load_vector_metadata()
    signature = get_dissertation_matrix_signature()
    if not metadata or signature is None:
        return None
    try:
        dimensions = int(metadata.get("dimensions", "0"))
    except ValueError:
        return None
    if dimensions <= 0:
        return None
    normalized = str(metadata.get("normalized", "true")).casefold() in {"1", "true", "yes", "да"}
    return VectorMetadata(
        model_name=str(metadata.get("model_name", "")), normalized=normalized,
        dimensions=dimensions, matrix_signature=signature,
    )


def resolve_matrix_path_from_metadata(metadata: dict[str, str] | None = None) -> Path | None:
    """Преобразует путь матрицы из метаданных в абсолютный путь."""
    metadata = metadata if metadata is not None else load_vector_metadata()
    value = str(metadata.get("matrix_file", "")).strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (resolve_dissertation_sections_db_path().parent / path).resolve()


def get_dissertation_matrix_signature() -> tuple[str, float, int] | None:
    """Возвращает подпись файла матрицы для сброса кэша."""
    path = resolve_matrix_path_from_metadata()
    if path is None or not path.exists():
        return None
    stat = path.stat()
    return (str(path), stat.st_mtime, stat.st_size)


@st.cache_data(show_spinner=False)
def _load_diagnostics_cached(db_signature: tuple[str, float, int] | None) -> dict:
    """Проверяет готовность базы разделов и матрицы с кэшированием."""
    path = resolve_dissertation_sections_db_path()
    diag = {"db_path": str(path), "db_exists": path.exists(), "warnings": []}
    if db_signature is None or not path.exists():
        diag["warnings"].append("База разделов диссертаций не найдена.")
        return diag
    try:
        with get_dissertation_sections_connection() as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            diag["tables"] = sorted(tables)
            missing_tables = sorted(REQUIRED_TABLES - tables)
            diag["missing_tables"] = missing_tables
            if missing_tables:
                diag["warnings"].append("В базе разделов отсутствуют обязательные таблицы.")
                return diag
            cols = {r[1] for r in conn.execute("PRAGMA table_info(dissertation_section_texts)")}
            diag["missing_columns"] = sorted(REQUIRED_TEXT_COLUMNS - cols)
            if diag["missing_columns"]:
                diag["warnings"].append("В таблице разделов отсутствуют обязательные столбцы.")
            diag["row_count"] = conn.execute("SELECT COUNT(*) FROM dissertation_section_texts").fetchone()[0]
            diag["code_count"] = conn.execute("SELECT COUNT(DISTINCT Code) FROM dissertation_section_texts").fetchone()[0]
            placeholders = ",".join("?" for _ in SEARCHABLE_SECTION_KEYS)
            diag["searchable_row_count"] = conn.execute(f"SELECT COUNT(*) FROM dissertation_section_texts WHERE section_key IN ({placeholders})", SEARCHABLE_SECTION_KEYS).fetchone()[0]
            diag["matrix_row_count"] = conn.execute(f"SELECT COUNT(*) FROM dissertation_section_texts WHERE section_key IN ({placeholders}) AND matrix_row IS NOT NULL", SEARCHABLE_SECTION_KEYS).fetchone()[0]
            max_row = conn.execute("SELECT MAX(matrix_row) FROM dissertation_section_texts WHERE matrix_row IS NOT NULL").fetchone()[0]
            metadata = {str(r[0]): str(r[1]) for r in conn.execute("SELECT key, value FROM dissertation_vector_meta")}
            diag["metadata"] = metadata
            diag["metadata_present"] = bool(metadata)
        matrix_path = resolve_matrix_path_from_metadata(metadata)
        diag["matrix_path"] = str(matrix_path) if matrix_path else ""
        diag["matrix_exists"] = bool(matrix_path and matrix_path.exists())
        if matrix_path and matrix_path.exists():
            matrix = np.load(matrix_path, mmap_mode="r")
            diag["matrix_shape"] = tuple(matrix.shape)
            if len(matrix.shape) != 2:
                diag["warnings"].append("Матрица векторов должна быть двумерной.")
            dims = metadata.get("dimensions")
            if dims and len(matrix.shape) == 2 and int(dims) != int(matrix.shape[1]):
                diag["warnings"].append("Размерность матрицы не совпадает с метаданными.")
            diag["matrix_rows_valid"] = max_row is None or int(max_row) < int(matrix.shape[0])
            if not diag["matrix_rows_valid"]:
                diag["warnings"].append("В базе есть ссылки на строки за пределами матрицы.")
        else:
            diag["warnings"].append("Файл матрицы векторов не найден.")
    except sqlite3.Error as exc:
        diag["warnings"].append(f"Не удалось прочитать базу разделов диссертаций: ошибка SQLite ({exc.__class__.__name__}).")
        diag["error_type"] = exc.__class__.__name__
    except OSError as exc:
        diag["warnings"].append(f"Не удалось открыть файл базы или матрицы: системная ошибка ({exc.__class__.__name__}).")
        diag["error_type"] = exc.__class__.__name__
    except ValueError as exc:
        diag["warnings"].append(f"Не удалось проверить параметры матрицы: неверное значение ({exc.__class__.__name__}).")
        diag["error_type"] = exc.__class__.__name__
    return diag


def load_dissertation_sections_diagnostics() -> dict:
    """Проверяет готовность базы разделов и матрицы к работе."""
    return _load_diagnostics_cached(get_dissertation_sections_db_signature())


@st.cache_data(show_spinner=False)
def _load_dissertation_section_codes_cached(db_signature: tuple[str, float, int] | None, allowed_codes: tuple[str, ...] | None) -> pd.DataFrame:
    """Загружает только связанные Code без текстов и строк разделов."""
    if db_signature is None:
        return pd.DataFrame(columns=["Code"])
    if allowed_codes is not None and not allowed_codes:
        return pd.DataFrame(columns=["Code"])
    frames: list[pd.DataFrame] = []
    try:
        with get_dissertation_sections_connection() as conn:
            if allowed_codes is None:
                frames.append(pd.read_sql_query("SELECT DISTINCT Code FROM dissertation_section_texts", conn))
            else:
                for code_batch in _batched(allowed_codes):
                    placeholders = ",".join("?" for _ in code_batch)
                    frames.append(
                        pd.read_sql_query(
                            f"SELECT DISTINCT Code FROM dissertation_section_texts WHERE Code IN ({placeholders})",
                            conn,
                            params=list(code_batch),
                        )
                    )
    except Exception:
        return pd.DataFrame(columns=["Code"])
    if not frames:
        return pd.DataFrame(columns=["Code"])
    return (pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]).drop_duplicates("Code").reset_index(drop=True)


def load_dissertation_section_codes(allowed_codes: list[str] | set[str] | tuple[str, ...] | None = None) -> pd.DataFrame:
    """Возвращает только Code диссертаций, для которых есть извлечённые разделы."""
    normalized_codes: tuple[str, ...] | None = None
    if allowed_codes is not None:
        normalized_codes = tuple(sorted({str(code).strip() for code in allowed_codes if str(code).strip()}))
    return _load_dissertation_section_codes_cached(get_dissertation_sections_db_signature(), normalized_codes)


@st.cache_data(show_spinner=False)
def _load_dissertation_section_index_cached(
    db_signature: tuple[str, float, int] | None,
    allowed_codes: tuple[str, ...] | None,
    searchable_only: bool,
    include_text: bool,
) -> pd.DataFrame:
    """Загружает лёгкий индекс разделов, применяя ограничение Code на стороне SQLite."""
    if db_signature is None:
        return _empty_index(include_text=include_text)
    if allowed_codes is not None and not allowed_codes:
        return _empty_index(include_text=include_text)

    columns = TEXT_COLUMNS if include_text else INDEX_COLUMNS
    select_clause = ", ".join(columns)
    section_filter = ""
    section_params: list[str] = []
    if searchable_only:
        section_filter = "section_key IN (" + ",".join("?" for _ in SEARCHABLE_SECTION_KEYS) + ")"
        section_params = list(SEARCHABLE_SECTION_KEYS)

    frames: list[pd.DataFrame] = []
    try:
        with get_dissertation_sections_connection() as conn:
            if allowed_codes is None:
                where_clause = f" WHERE {section_filter}" if section_filter else ""
                frames.append(pd.read_sql_query(f"SELECT {select_clause} FROM dissertation_section_texts{where_clause}", conn, params=section_params))
            else:
                for code_batch in _batched(allowed_codes):
                    code_filter = "Code IN (" + ",".join("?" for _ in code_batch) + ")"
                    filters = [code_filter]
                    params: list[str] = list(code_batch)
                    if section_filter:
                        filters.append(section_filter)
                        params.extend(section_params)
                    where_clause = " WHERE " + " AND ".join(filters)
                    frames.append(pd.read_sql_query(f"SELECT {select_clause} FROM dissertation_section_texts{where_clause}", conn, params=params))
    except Exception:
        return _empty_index(include_text=include_text)

    if not frames:
        return _empty_index(include_text=include_text)
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    return _with_section_label(df)


def load_dissertation_section_index(
    allowed_codes: list[str] | set[str] | tuple[str, ...] | None = None,
    searchable_only: bool = False,
    include_text: bool = False,
) -> pd.DataFrame:
    """Загружает индекс разделов без полного текста, если он явно не запрошен."""
    normalized_codes: tuple[str, ...] | None = None
    if allowed_codes is not None:
        normalized_codes = tuple(sorted({str(code).strip() for code in allowed_codes if str(code).strip()}))
    return _load_dissertation_section_index_cached(
        get_dissertation_sections_db_signature(),
        normalized_codes,
        bool(searchable_only),
        bool(include_text),
    )


@st.cache_data(show_spinner=False)
def _load_dissertation_section_index_for_selection_cached(
    db_signature: tuple[str, float, int] | None,
    allowed_codes: tuple[str, ...] | None,
    section_keys: tuple[str, ...],
    include_text: bool,
) -> pd.DataFrame:
    """Загружает выбранные разделы, применяя оба фильтра в SQLite."""
    if db_signature is None or not section_keys or (allowed_codes is not None and not allowed_codes):
        return _empty_index(include_text)
    columns = TEXT_COLUMNS if include_text else INDEX_COLUMNS
    select_clause = ", ".join(columns)
    section_clause = "section_key IN (" + ",".join("?" for _ in section_keys) + ")"
    frames: list[pd.DataFrame] = []
    try:
        with get_dissertation_sections_connection() as conn:
            if allowed_codes is None:
                frames.append(pd.read_sql_query(
                    f"SELECT {select_clause} FROM dissertation_section_texts WHERE {section_clause}",
                    conn, params=list(section_keys),
                ))
            else:
                for code_batch in _batched(allowed_codes):
                    code_clause = "Code IN (" + ",".join("?" for _ in code_batch) + ")"
                    frames.append(pd.read_sql_query(
                        f"SELECT {select_clause} FROM dissertation_section_texts WHERE {code_clause} AND {section_clause}",
                        conn, params=[*code_batch, *section_keys],
                    ))
    except (OSError, sqlite3.Error):
        return _empty_index(include_text)
    if not frames:
        return _empty_index(include_text)
    return _with_section_label(pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0])


def load_dissertation_section_index_for_selection(
    *, allowed_codes: Collection[str] | None, section_keys: Collection[str],
    include_text: bool = False,
) -> pd.DataFrame:
    """Возвращает канонический лёгкий индекс для явно выбранных разделов."""
    requested = {str(key).strip() for key in section_keys if str(key).strip()}
    unknown = requested - set(SEARCHABLE_SECTION_KEYS)
    if unknown:
        raise ValueError("Выбраны неизвестные разделы характеристик.")
    ordered_keys = tuple(key for key in SEARCHABLE_SECTION_KEYS if key in requested)
    normalized_codes = None
    if allowed_codes is not None:
        normalized_codes = tuple(sorted({str(code).strip() for code in allowed_codes if str(code).strip()}))
    return _load_dissertation_section_index_for_selection_cached(
        get_dissertation_sections_db_signature(), normalized_codes, ordered_keys, bool(include_text)
    )


@st.cache_data(show_spinner=False)
def _load_dissertation_sections_by_code_cached(db_signature: tuple[str, float, int] | None, code: str) -> pd.DataFrame:
    """Загружает полный текст разделов одной диссертации."""
    if db_signature is None:
        return _empty_index(include_text=True)
    try:
        with get_dissertation_sections_connection() as conn:
            df = pd.read_sql_query(
                "SELECT text_id, Code, section_key, section_order, text, text_hash, matrix_row FROM dissertation_section_texts WHERE Code = ? ORDER BY section_order, section_key",
                conn,
                params=[str(code)],
            )
    except Exception:
        return _empty_index(include_text=True)
    return _with_section_label(df)


def load_dissertation_sections_by_code(code: str) -> pd.DataFrame:
    """Загружает разделы одной диссертации в порядке исходной характеристики."""
    return _load_dissertation_sections_by_code_cached(get_dissertation_sections_db_signature(), str(code))


@st.cache_data(show_spinner=False)
def _load_dissertation_section_texts_by_ids_cached(db_signature: tuple[str, float, int] | None, text_ids: tuple[str, ...]) -> pd.DataFrame:
    """Загружает полный текст только для выбранных результатов поиска."""
    if db_signature is None or not text_ids:
        return _empty_index(include_text=True)
    frames: list[pd.DataFrame] = []
    try:
        with get_dissertation_sections_connection() as conn:
            for id_batch in _batched(text_ids):
                placeholders = ",".join("?" for _ in id_batch)
                frames.append(
                    pd.read_sql_query(
                        f"SELECT text_id, Code, section_key, section_order, text, text_hash, matrix_row FROM dissertation_section_texts WHERE text_id IN ({placeholders})",
                        conn,
                        params=list(id_batch),
                    )
                )
    except Exception:
        return _empty_index(include_text=True)
    if not frames:
        return _empty_index(include_text=True)
    return _with_section_label(pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0])


def load_dissertation_section_texts_by_ids(text_ids: list[str] | tuple[str, ...] | pd.Series) -> pd.DataFrame:
    """Возвращает тексты разделов для финального набора результатов поиска."""
    normalized_ids = tuple(sorted({str(value).strip() for value in text_ids if pd.notna(value) and str(value).strip()}))
    return _load_dissertation_section_texts_by_ids_cached(get_dissertation_sections_db_signature(), normalized_ids)
