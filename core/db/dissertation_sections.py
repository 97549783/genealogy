"""Доступ к базе извлечённых разделов характеристик диссертаций."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

from tabs.dissertation_characteristics.labels import SEARCHABLE_SECTION_KEYS, SECTION_LABELS_RU

REQUIRED_TEXT_COLUMNS = {"text_id", "Code", "section_key", "section_order", "text", "text_hash", "matrix_row"}
REQUIRED_TABLES = {"dissertation_section_texts", "dissertation_vector_meta"}


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


def _empty_index() -> pd.DataFrame:
    return pd.DataFrame(columns=["text_id", "Code", "section_key", "section_order", "text", "text_hash", "matrix_row", "section_label"])


def load_vector_metadata() -> dict[str, str]:
    """Загружает метаданные матрицы векторов."""
    with get_dissertation_sections_connection() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "dissertation_vector_meta" not in tables:
            return {}
        rows = conn.execute("SELECT key, value FROM dissertation_vector_meta").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


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


def load_dissertation_sections_diagnostics() -> dict:
    """Проверяет готовность базы разделов и матрицы к работе."""
    path = resolve_dissertation_sections_db_path()
    diag = {"db_path": str(path), "db_exists": path.exists(), "warnings": []}
    if not path.exists():
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
    except Exception:
        diag["warnings"].append("Не удалось проверить базу разделов диссертаций.")
    return diag


def load_dissertation_section_index(allowed_codes: list[str] | set[str] | None = None, searchable_only: bool = False) -> pd.DataFrame:
    """Загружает индекс разделов с необязательным ограничением по Code."""
    try:
        sql = "SELECT text_id, Code, section_key, section_order, text, text_hash, matrix_row FROM dissertation_section_texts"
        params: list[str] = []
        if searchable_only:
            sql += " WHERE section_key IN (" + ",".join("?" for _ in SEARCHABLE_SECTION_KEYS) + ")"
            params.extend(SEARCHABLE_SECTION_KEYS)
        with get_dissertation_sections_connection() as conn:
            df = pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return _empty_index()
    if allowed_codes is not None:
        codes = {str(code) for code in allowed_codes if str(code).strip()}
        df = df[df["Code"].astype(str).isin(codes)] if codes else df.iloc[0:0]
    df["section_label"] = df["section_key"].map(SECTION_LABELS_RU).fillna(df["section_key"])
    return df.reset_index(drop=True)


def load_dissertation_sections_by_code(code: str) -> pd.DataFrame:
    """Загружает разделы одной диссертации в порядке исходной характеристики."""
    try:
        with get_dissertation_sections_connection() as conn:
            df = pd.read_sql_query(
                "SELECT text_id, Code, section_key, section_order, text, text_hash, matrix_row FROM dissertation_section_texts WHERE Code = ? ORDER BY section_order, section_key",
                conn,
                params=[str(code)],
            )
    except Exception:
        return _empty_index()
    df["section_label"] = df["section_key"].map(SECTION_LABELS_RU).fillna(df["section_key"])
    return df
