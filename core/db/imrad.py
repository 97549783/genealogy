"""Загрузка IMRAD-данных и индексов эмбеддингов из SQLite."""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from .connection import get_db_signature, get_sqlite_connection


@st.cache_data(show_spinner=False)
def _list_tables_cached(db_signature: tuple[str, float, int]) -> set[str]:
    """Возвращает множество имён таблиц в SQLite."""
    _ = db_signature
    with get_sqlite_connection() as conn:
        df = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)
    return set(df["name"].astype(str).tolist())


def _table_exists(name: str) -> bool:
    """Проверяет наличие таблицы в базе."""
    return name in _list_tables_cached(get_db_signature())


def load_imrad_diagnostics() -> dict:
    """Собирает диагностику по IMRAD-таблицам и файлам матриц."""
    return _load_imrad_diagnostics_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_imrad_diagnostics_cached(db_signature: tuple[str, float, int]) -> dict:
    """Кэшируемая диагностика IMRAD-слоя."""
    _ = db_signature
    tables = _list_tables_cached(db_signature)
    diagnostics: dict[str, object] = {
        "таблицы": sorted(tables),
        "счётчики": {},
        "варианты": pd.DataFrame(),
    }
    with get_sqlite_connection() as conn:
        for table in ["article_imrad_units", "article_imrad_unit_texts", "article_imrad_embeddings"]:
            if table in tables:
                value = pd.read_sql_query(f"SELECT COUNT(*) AS c FROM {table}", conn).iloc[0]["c"]
                diagnostics["счётчики"][table] = int(value)
            else:
                diagnostics["счётчики"][table] = None
    diagnostics["варианты"] = load_imrad_embedding_options()
    return diagnostics


def load_imrad_embedding_options() -> pd.DataFrame:
    """Загружает доступные комбинации язык/роль/модель и пути матриц."""
    return _load_imrad_embedding_options_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_imrad_embedding_options_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Кэшируемая загрузка опций для семантического поиска."""
    _ = db_signature
    needed = {"article_embedding_models", "article_imrad_embedding_files"}
    if not needed.issubset(_list_tables_cached(db_signature)):
        return pd.DataFrame()
    with get_sqlite_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT f.matrix_file_id, f.embedding_model_id, f.language, f.text_role, f.file_path,
                   f.matrix_shape, f.dtype, f.normalized, m.provider, m.model_name,
                   m.model_version, m.distance_metric, m.dimensions
            FROM article_imrad_embedding_files f
            LEFT JOIN article_embedding_models m USING(embedding_model_id)
            ORDER BY f.language, f.text_role, m.model_name, f.matrix_file_id
            """,
            conn,
        )


def load_imrad_text_index(language: str, text_role: str, embedding_model_id: str | None = None, matrix_file_id: str | None = None) -> pd.DataFrame:
    """Загружает индекс IMRAD-текстов, привязанный к строкам матрицы."""
    return _load_imrad_text_index_cached(get_db_signature(), language, text_role, embedding_model_id, matrix_file_id)


@st.cache_data(show_spinner=False)
def _load_imrad_text_index_cached(db_signature: tuple[str, float, int], language: str, text_role: str, embedding_model_id: str | None, matrix_file_id: str | None) -> pd.DataFrame:
    """Кэшируемая загрузка индекса для поиска похожих зон."""
    _ = db_signature
    needed = {"article_imrad_units", "article_imrad_unit_texts", "article_imrad_embeddings", "article_imrad_embedding_files"}
    if not needed.issubset(_list_tables_cached(db_signature)):
        return pd.DataFrame()
    filters = ["t.language = :language", "t.text_role = :text_role"]
    params: dict[str, object] = {"language": language, "text_role": text_role}
    if embedding_model_id:
        filters.append("e.embedding_model_id = :embedding_model_id")
        params["embedding_model_id"] = embedding_model_id
    if matrix_file_id:
        filters.append("e.matrix_file_id = :matrix_file_id")
        params["matrix_file_id"] = matrix_file_id
    where_sql = " AND ".join(filters)
    with get_sqlite_connection() as conn:
        return pd.read_sql_query(
            f"""
            SELECT t.text_id, t.unit_id, t.article_id, t.language, t.text_role, t.text, t.keywords_json,
                   u.unit_level, u.imrad_block, u.imrad_subblock, u.rhetorical_zone_type,
                   u.confidence, u.is_weak, u.is_inferred, u.source_zone_ids_json, u.source_file,
                   e.embedding_model_id, e.matrix_file_id, e.matrix_row, e.vector_norm,
                   f.file_path, f.matrix_shape, f.normalized, f.dtype
            FROM article_imrad_unit_texts t
            JOIN article_imrad_units u ON u.unit_id = t.unit_id
            JOIN article_imrad_embeddings e ON e.text_id = t.text_id
            JOIN article_imrad_embedding_files f ON f.matrix_file_id = e.matrix_file_id
            WHERE {where_sql}
            """,
            conn,
            params=params,
        )


def load_article_imrad_units(article_id: str, language: str | None = None, text_role: str | None = None) -> pd.DataFrame:
    """Загружает IMRAD-блоки и полезные поля для одной статьи."""
    return _load_article_imrad_units_cached(get_db_signature(), article_id, language, text_role)


@st.cache_data(show_spinner=False)
def _load_article_imrad_units_cached(db_signature: tuple[str, float, int], article_id: str, language: str | None, text_role: str | None) -> pd.DataFrame:
    """Кэшируемая загрузка IMRAD-данных по статье."""
    _ = db_signature
    if "article_imrad_units" not in _list_tables_cached(db_signature):
        return pd.DataFrame()
    join_text = ""
    join_payload = ""
    if "article_imrad_unit_texts" in _list_tables_cached(db_signature):
        join_text = "LEFT JOIN article_imrad_unit_texts t ON t.unit_id = u.unit_id"
    if "article_imrad_unit_payloads" in _list_tables_cached(db_signature):
        join_payload = "LEFT JOIN article_imrad_unit_payloads p ON p.unit_id = u.unit_id"
    wh = ["u.article_id = :article_id"]
    params: dict[str, object] = {"article_id": article_id}
    if language:
        wh.append("(t.language = :language OR t.language IS NULL)")
        params["language"] = language
    if text_role:
        wh.append("(t.text_role = :text_role OR t.text_role IS NULL)")
        params["text_role"] = text_role
    with get_sqlite_connection() as conn:
        try:
            return pd.read_sql_query(
                f"""
                SELECT u.*, t.text_id, t.language, t.text_role, t.text, t.keywords_json,
                       p.key_assertions_json, p.extracted_json, p.evidence_quotes_json, p.keywords_ru_json, p.keywords_en_json
                FROM article_imrad_units u
                {join_text}
                {join_payload}
                WHERE {' AND '.join(wh)}
                ORDER BY u.imrad_block, u.imrad_subblock, u.unit_id
                """,
                conn,
                params=params,
            )
        except (sqlite3.OperationalError, pd.errors.DatabaseError):
            return pd.DataFrame()


def load_imrad_quotes(unit_ids: list[str]) -> pd.DataFrame:
    """Загружает цитаты для списка unit_id."""
    return _load_imrad_quotes_cached(get_db_signature(), tuple(unit_ids))


@st.cache_data(show_spinner=False)
def _load_imrad_quotes_cached(db_signature: tuple[str, float, int], unit_ids: tuple[str, ...]) -> pd.DataFrame:
    """Кэшируемая загрузка цитат IMRAD."""
    _ = db_signature
    if not unit_ids or "article_imrad_unit_quotes" not in _list_tables_cached(db_signature):
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(unit_ids))
    with get_sqlite_connection() as conn:
        return pd.read_sql_query(f"SELECT * FROM article_imrad_unit_quotes WHERE unit_id IN ({placeholders})", conn, params=list(unit_ids))
