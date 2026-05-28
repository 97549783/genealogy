"""Загрузка IMRAD-данных и индексов эмбеддингов из SQLite."""

from __future__ import annotations

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


def load_imrad_diagnostics() -> dict:
    """Собирает диагностику по IMRAD-таблицам и файлам матриц."""
    return _load_imrad_diagnostics_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_imrad_diagnostics_cached(db_signature: tuple[str, float, int]) -> dict:
    _ = db_signature
    tables = _list_tables_cached(db_signature)
    diagnostics: dict[str, object] = {"счётчики": {}, "варианты": pd.DataFrame()}
    with get_sqlite_connection() as conn:
        for table in ["article_imrad_units", "article_imrad_unit_texts", "article_imrad_embeddings"]:
            diagnostics["счётчики"][table] = int(pd.read_sql_query(f"SELECT COUNT(*) AS c FROM {table}", conn).iloc[0]["c"]) if table in tables else None
    diagnostics["варианты"] = load_imrad_embedding_options()
    return diagnostics


def load_imrad_embedding_options() -> pd.DataFrame:
    return _load_imrad_embedding_options_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_imrad_embedding_options_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    _ = db_signature
    if not {"article_embedding_models", "article_imrad_embedding_files"}.issubset(_list_tables_cached(db_signature)):
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
    return _load_imrad_text_index_cached(get_db_signature(), language, text_role, embedding_model_id, matrix_file_id)


@st.cache_data(show_spinner=False)
def _load_imrad_text_index_cached(db_signature: tuple[str, float, int], language: str, text_role: str, embedding_model_id: str | None, matrix_file_id: str | None) -> pd.DataFrame:
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
            WHERE {' AND '.join(filters)}
            """,
            conn,
            params=params,
        )


def select_default_imrad_embedding_option(options_df: pd.DataFrame) -> pd.Series | None:
    """Выбирает слой эмбеддингов по внутреннему приоритету."""
    if options_df is None or options_df.empty:
        return None
    work = options_df.copy()
    model = work.get("model_name", pd.Series([""] * len(work))).astype(str).str.lower()
    c1 = (work["language"].astype(str) == "en") & (work["text_role"].astype(str) == "compact_en") & model.str.contains("multilingual-e5-base", na=False)
    if c1.any():
        return work[c1].iloc[0]
    c2 = (work["language"].astype(str) == "en") & (work["text_role"].astype(str) == "compact_en")
    if c2.any():
        return work[c2].iloc[0]
    return work.iloc[0]


def load_fully_vectorized_article_ids(language: str, text_role: str, embedding_model_id: str | None = None, matrix_file_id: str | None = None, excluded_blocks: set[str] | None = None) -> set[str]:
    """Возвращает идентификаторы статей, где все релевантные разделы векторизованы."""
    blocks = tuple(sorted(excluded_blocks or {"SUPPLEMENTARY_OR_TEXTUAL"}))
    return _load_fully_vectorized_article_ids_cached(get_db_signature(), language, text_role, embedding_model_id, matrix_file_id, blocks)


@st.cache_data(show_spinner=False)
def _load_fully_vectorized_article_ids_cached(db_signature: tuple[str, float, int], language: str, text_role: str, embedding_model_id: str | None, matrix_file_id: str | None, excluded_blocks: tuple[str, ...]) -> set[str]:
    _ = db_signature
    needed = {"article_imrad_units", "article_imrad_unit_texts", "article_imrad_embeddings", "article_imrad_embedding_files"}
    if not needed.issubset(_list_tables_cached(db_signature)):
        return set()
    params: dict[str, object] = {"language": language, "text_role": text_role}
    exclude_sql = ""
    if excluded_blocks:
        placeholders = ",".join([f":ex{i}" for i in range(len(excluded_blocks))])
        exclude_sql = f"AND COALESCE(u.imrad_block, '') NOT IN ({placeholders})"
        params.update({f"ex{i}": block for i, block in enumerate(excluded_blocks)})
    model_sql = ""
    if embedding_model_id:
        model_sql = "AND e.embedding_model_id = :embedding_model_id"
        params["embedding_model_id"] = embedding_model_id
    matrix_sql = ""
    if matrix_file_id:
        matrix_sql = "AND e.matrix_file_id = :matrix_file_id"
        params["matrix_file_id"] = matrix_file_id
    with get_sqlite_connection() as conn:
        df = pd.read_sql_query(
            f"""
            WITH eligible AS (
                SELECT u.article_id, COUNT(DISTINCT u.unit_id) AS eligible_count
                FROM article_imrad_units u
                WHERE COALESCE(u.imrad_block, '') != '' {exclude_sql}
                GROUP BY u.article_id
            ),
            embedded AS (
                SELECT u.article_id, COUNT(DISTINCT u.unit_id) AS embedded_count
                FROM article_imrad_units u
                JOIN article_imrad_unit_texts t ON t.unit_id = u.unit_id
                JOIN article_imrad_embeddings e ON e.text_id = t.text_id
                JOIN article_imrad_embedding_files f ON f.matrix_file_id = e.matrix_file_id
                WHERE t.language = :language AND t.text_role = :text_role {exclude_sql} {model_sql} {matrix_sql}
                GROUP BY u.article_id
            )
            SELECT el.article_id
            FROM eligible el
            LEFT JOIN embedded em ON em.article_id = el.article_id
            WHERE el.eligible_count > 0 AND el.eligible_count = COALESCE(em.embedded_count, 0)
            """,
            conn,
            params=params,
        )
    return set(df["article_id"].astype(str).tolist())


def load_imrad_display_texts_ru(unit_ids: list[str]) -> pd.DataFrame:
    """Загружает русский текст и ключевые слова для отображения разделов."""
    return _load_imrad_display_texts_ru_cached(get_db_signature(), tuple(unit_ids))


@st.cache_data(show_spinner=False)
def _load_imrad_display_texts_ru_cached(db_signature: tuple[str, float, int], unit_ids: tuple[str, ...]) -> pd.DataFrame:
    _ = db_signature
    empty = pd.DataFrame(columns=["unit_id", "display_text_ru", "display_keywords_ru"])
    if not unit_ids or "article_imrad_unit_texts" not in _list_tables_cached(db_signature):
        return empty
    placeholders = ",".join(["?"] * len(unit_ids))
    payload_join = ""
    payload_col = "NULL AS keywords_ru_json"
    if "article_imrad_unit_payloads" in _list_tables_cached(db_signature):
        payload_join = "LEFT JOIN article_imrad_unit_payloads p ON p.unit_id = t.unit_id"
        payload_col = "p.keywords_ru_json"
    with get_sqlite_connection() as conn:
        df = pd.read_sql_query(
            f"""
            SELECT t.unit_id, t.text_role, t.text, t.keywords_json, {payload_col}
            FROM article_imrad_unit_texts t
            {payload_join}
            WHERE t.unit_id IN ({placeholders})
              AND t.language = 'ru'
              AND t.text_role IN ('compact_ru','canonical_ru')
            """,
            conn,
            params=list(unit_ids),
        )
    if df.empty:
        return empty
    df["rank"] = df["text_role"].map({"compact_ru": 0, "canonical_ru": 1}).fillna(99)
    df = df.sort_values(["unit_id", "rank"]).drop_duplicates("unit_id")
    out = df[["unit_id", "text", "keywords_ru_json", "keywords_json"]].rename(columns={"text": "display_text_ru"})
    out["display_keywords_ru"] = out["keywords_ru_json"].fillna("")
    mask = out["display_keywords_ru"].astype(str).str.strip() == ""
    out.loc[mask, "display_keywords_ru"] = out.loc[mask, "keywords_json"]
    return out[["unit_id", "display_text_ru", "display_keywords_ru"]]


def load_article_imrad_units(article_id: str, language: str | None = None, text_role: str | None = None) -> pd.DataFrame:
    return _load_article_imrad_units_cached(get_db_signature(), article_id, language, text_role)


@st.cache_data(show_spinner=False)
def _load_article_imrad_units_cached(db_signature: tuple[str, float, int], article_id: str, language: str | None, text_role: str | None) -> pd.DataFrame:
    _ = db_signature
    tables = _list_tables_cached(db_signature)
    if "article_imrad_units" not in tables:
        return pd.DataFrame()
    text_join = ""
    text_select = "NULL AS text_id, NULL AS language, NULL AS text_role, NULL AS text, NULL AS keywords_json"
    if "article_imrad_unit_texts" in tables:
        conds = ["t.unit_id = u.unit_id"]
        if language:
            conds.append("t.language = :language")
        if text_role:
            conds.append("t.text_role = :text_role")
        text_join = f"LEFT JOIN article_imrad_unit_texts t ON {' AND '.join(conds)}"
        text_select = "t.text_id, t.language, t.text_role, t.text, t.keywords_json"
    payload_join = ""
    payload_select = "NULL AS key_assertions_json, NULL AS extracted_json, NULL AS evidence_quotes_json, NULL AS keywords_ru_json, NULL AS keywords_en_json"
    if "article_imrad_unit_payloads" in tables:
        payload_join = "LEFT JOIN article_imrad_unit_payloads p ON p.unit_id = u.unit_id"
        payload_select = "p.key_assertions_json, p.extracted_json, p.evidence_quotes_json, p.keywords_ru_json, p.keywords_en_json"
    with get_sqlite_connection() as conn:
        return pd.read_sql_query(
            f"""
            SELECT u.*, {text_select}, {payload_select}
            FROM article_imrad_units u
            {text_join}
            {payload_join}
            WHERE u.article_id = :article_id
            ORDER BY u.imrad_block, u.imrad_subblock, u.unit_id
            """,
            conn,
            params={"article_id": article_id, "language": language, "text_role": text_role},
        )


def load_imrad_quotes(unit_ids: list[str]) -> pd.DataFrame:
    return _load_imrad_quotes_cached(get_db_signature(), tuple(unit_ids))


@st.cache_data(show_spinner=False)
def _load_imrad_quotes_cached(db_signature: tuple[str, float, int], unit_ids: tuple[str, ...]) -> pd.DataFrame:
    _ = db_signature
    if not unit_ids or "article_imrad_unit_quotes" not in _list_tables_cached(db_signature):
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(unit_ids))
    with get_sqlite_connection() as conn:
        return pd.read_sql_query(f"SELECT * FROM article_imrad_unit_quotes WHERE unit_id IN ({placeholders})", conn, params=list(unit_ids))
