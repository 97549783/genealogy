"""Загрузка диссертационных метаданных и профилей из SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from core.domain.science_fields import (
    SCIENCE_FIELD_COLUMN,
    SCIENCE_FIELD_OPTIONS,
    filter_df_by_science_fields,
    normalize_science_field_text,
    get_science_field_stem_variants,
)

from .connection import get_db_signature, get_sqlite_connection
from .scores import load_dissertation_scores

AUTHOR_COLUMN = "candidate_name"
SUPERVISOR_COLUMNS: List[str] = ["supervisors_1.name", "supervisors_2.name"]
FEEDBACK_FILE = Path("/app/data-nonsynchronized/feedback.csv")

SINGLE_COLUMN_CRITERIA = {
    "title": "title",
    "candidate_name": "candidate_name",
    "institution_prepared": "institution_prepared",
    "leading_organization": "leading_organization",
    "defense_location": "defense_location",
    "city": "city",
    "year": "year",
}
MULTI_COLUMN_CRITERIA = {
    "supervisors": ["supervisors_1.name", "supervisors_2.name"],
    "opponents": ["opponents_1.name", "opponents_2.name", "opponents_3.name"],
    "specialties": ["specialties_1.code", "specialties_1.name", "specialties_2.code", "specialties_2.name"],
}
SCHOOL_SEARCH_TEXT_COLUMNS = {
    "city",
    "institution_prepared",
    "defense_location",
    "leading_organization",
    "opponents_1.name",
    "opponents_2.name",
    "opponents_3.name",
    "candidate_name",
}
SCHOOL_SEARCH_NUMERIC_COLUMNS = {"year"}


def _quote_identifier(identifier: str) -> str:
    """Экранирует имя столбца SQLite."""
    return '"' + identifier.replace('"', '""') + '"'


def _existing_columns() -> set[str]:
    with get_sqlite_connection() as conn:
        rows = conn.execute("PRAGMA table_info(diss_metadata)").fetchall()
    return {row[1] for row in rows}


def _like_expr(column: str) -> str:
    return f"CASEFOLD(COALESCE(CAST({_quote_identifier(column)} AS TEXT), '')) LIKE CASEFOLD(?)"


def load_dissertation_metadata() -> pd.DataFrame:
    """Загружает метаданные диссертаций из таблицы diss_metadata."""
    return _load_dissertation_metadata_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_dissertation_metadata_cached(db_signature: tuple[str, float, int]) -> pd.DataFrame:
    """Загружает метаданные диссертаций из SQLite с кэшированием."""
    _ = db_signature
    with get_sqlite_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM diss_metadata", conn)

    if df.empty:
        raise ValueError("Таблица diss_metadata пуста")
    if "Code" not in df.columns:
        raise KeyError("В таблице diss_metadata отсутствует столбец 'Code'")
    if AUTHOR_COLUMN not in df.columns:
        raise KeyError(f"В таблице diss_metadata отсутствует столбец '{AUTHOR_COLUMN}'")

    df = df.dropna(subset=["Code"]).copy()
    df["Code"] = df["Code"].astype(str).str.strip()
    df = df[df["Code"] != ""]
    df = df.drop_duplicates(subset=["Code"], keep="first")
    return df


def _science_field_like_clauses(
    science_field_ids: list[str] | tuple[str, ...] | set[str] | None,
    existing_columns: set[str],
    column: str = SCIENCE_FIELD_COLUMN,
) -> tuple[list[str], list[str]]:
    if not science_field_ids:
        return [], []
    if column not in existing_columns:
        return [], []

    stems: list[str] = []
    for field_id in science_field_ids:
        option = SCIENCE_FIELD_OPTIONS.get(str(field_id).strip())
        if option is None:
            continue
        stems.extend(option.match_stems)

    normalized_stems = [variant for stem in stems for variant in get_science_field_stem_variants(stem)]
    clauses = [_like_expr(column) for _ in normalized_stems]
    params = [f"%{stem}%" for stem in normalized_stems]
    if not clauses:
        return [], []
    return ["(" + " OR ".join(clauses) + ")"], params


def build_science_field_like_clauses(
    selected_field_ids: list[str] | tuple[str, ...] | set[str] | None,
    column: str = SCIENCE_FIELD_COLUMN,
) -> tuple[str, list[str]]:
    existing = _existing_columns()
    if column not in existing:
        return "", []
    clauses, params = _science_field_like_clauses(selected_field_ids, existing, column=column)
    return (clauses[0], params) if clauses else ("", [])


def _search_dissertation_metadata_like(
    search_params: dict[str, str],
    science_field_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Ищет диссертации через быстрый SQL LIKE."""
    existing = _existing_columns()
    where_clauses: list[str] = []
    params: list[str] = []

    for criterion, raw_value in search_params.items():
        value = str(raw_value).strip()
        if not value or value == "Все":
            continue
        like_value = f"%{value}%"

        if criterion in SINGLE_COLUMN_CRITERIA:
            column = SINGLE_COLUMN_CRITERIA[criterion]
            if column not in existing:
                raise ValueError(f"В таблице diss_metadata отсутствуют столбцы для критерия: {criterion}")
            where_clauses.append(_like_expr(column))
            params.append(like_value)
            continue

        if criterion in MULTI_COLUMN_CRITERIA:
            cols = [col for col in MULTI_COLUMN_CRITERIA[criterion] if col in existing]
            if not cols:
                raise ValueError(f"В таблице diss_metadata отсутствуют столбцы для критерия: {criterion}")
            where_clauses.append("(" + " OR ".join(_like_expr(col) for col in cols) + ")")
            params.extend([like_value] * len(cols))

    science_clauses, science_params = _science_field_like_clauses(science_field_ids, existing)
    where_clauses.extend(science_clauses)
    params.extend(science_params)

    query = "SELECT * FROM diss_metadata"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    if "year" in existing and "candidate_name" in existing:
        query += f" ORDER BY CAST({_quote_identifier('year')} AS INTEGER) DESC, {_quote_identifier('candidate_name')} ASC"
    elif "Code" in existing:
        query += f" ORDER BY {_quote_identifier('Code')}"

    with get_sqlite_connection() as conn:
        conn.create_function("CASEFOLD", 1, normalize_science_field_text)
        return pd.read_sql_query(query, conn, params=params)




def _apply_default_sort(df: pd.DataFrame) -> pd.DataFrame:
    """Сортирует результаты так же, как SQL-путь."""
    if df.empty:
        return df
    if "year" in df.columns and "candidate_name" in df.columns:
        years = pd.to_numeric(df["year"], errors="coerce")
        return df.assign(_year_sort=years).sort_values(["_year_sort", "candidate_name"], ascending=[False, True], na_position="last").drop(columns=["_year_sort"])
    if "Code" in df.columns:
        return df.sort_values("Code")
    return df


def _search_dissertation_metadata_fuzzy(
    search_params: dict[str, str],
    science_field_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Ищет диссертации через нечёткое сопоставление текстовых критериев."""
    from core.search.text_matching import fuzzy_match_series

    existing = _existing_columns()
    active = {k: str(v).strip() for k, v in search_params.items() if str(v).strip() and str(v).strip() != "Все"}
    if not active:
        return _search_dissertation_metadata_like(search_params, science_field_ids=science_field_ids)

    with get_sqlite_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM diss_metadata", conn)

    mask = pd.Series(True, index=df.index)
    for criterion, value in active.items():
        if criterion in SINGLE_COLUMN_CRITERIA:
            column = SINGLE_COLUMN_CRITERIA[criterion]
            if column not in existing:
                raise ValueError(f"В таблице diss_metadata отсутствуют столбцы для критерия: {criterion}")
            if criterion == "year":
                criterion_mask = df[column].astype(str).str.strip() == value
            else:
                criterion_mask = fuzzy_match_series(df[column], value)
            mask = mask & criterion_mask
            continue
        if criterion in MULTI_COLUMN_CRITERIA:
            cols = [col for col in MULTI_COLUMN_CRITERIA[criterion] if col in existing]
            if not cols:
                raise ValueError(f"В таблице diss_metadata отсутствуют столбцы для критерия: {criterion}")
            criterion_mask = pd.Series(False, index=df.index)
            for col in cols:
                criterion_mask = criterion_mask | fuzzy_match_series(df[col], value)
            mask = mask & criterion_mask

    result = _apply_default_sort(df[mask].copy())
    return filter_df_by_science_fields(result, science_field_ids)


def search_dissertation_metadata(
    search_params: dict[str, str],
    *,
    use_fuzzy: bool = False,
    science_field_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Ищет диссертации по формальным критериям."""
    if use_fuzzy:
        return _search_dissertation_metadata_fuzzy(search_params, science_field_ids=science_field_ids)
    return _search_dissertation_metadata_like(search_params, science_field_ids=science_field_ids)


def load_dissertation_filter_options() -> dict[str, list[str]]:
    """Загружает значения для выпадающих фильтров поиска диссертаций."""
    return _load_dissertation_filter_options_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _load_dissertation_filter_options_cached(db_signature: tuple[str, float, int]) -> dict[str, list[str]]:
    """Загружает значения фильтров диссертаций из SQLite с кэшированием."""
    _ = db_signature
    existing = _existing_columns()
    with get_sqlite_connection() as conn:
        years = []
        if "year" in existing:
            years = [str(r[0]).strip() for r in conn.execute('SELECT DISTINCT "year" FROM diss_metadata WHERE "year" IS NOT NULL AND TRIM(CAST("year" AS TEXT)) != "" ORDER BY CAST("year" AS INTEGER) DESC').fetchall()]

        cities = []
        if "city" in existing:
            cities = [str(r[0]).strip() for r in conn.execute('SELECT DISTINCT "city" FROM diss_metadata WHERE "city" IS NOT NULL AND TRIM(CAST("city" AS TEXT)) != "" ORDER BY "city" COLLATE NOCASE').fetchall()]

        specialty_cols = [c for c in ["specialties_1.code", "specialties_1.name", "specialties_2.code", "specialties_2.name"] if c in existing]
        specialties: list[str] = []
        if specialty_cols:
            union_query = " UNION ".join([f"SELECT {_quote_identifier(col)} AS value FROM diss_metadata" for col in specialty_cols])
            spec_query = f"SELECT DISTINCT value FROM ({union_query}) WHERE value IS NOT NULL AND TRIM(CAST(value AS TEXT)) != '' ORDER BY value COLLATE NOCASE"
            specialties = [str(r[0]).strip() for r in conn.execute(spec_query).fetchall()]

    return {"year": years, "city": cities, "specialties": specialties}


def fetch_distinct_science_field_values() -> list[str]:
    """Возвращает уникальные непустые значения отраслей наук из метаданных."""
    existing = _existing_columns()
    if SCIENCE_FIELD_COLUMN not in existing:
        return []
    with get_sqlite_connection() as conn:
        rows = conn.execute(
            f'''
            SELECT DISTINCT {_quote_identifier(SCIENCE_FIELD_COLUMN)}
            FROM diss_metadata
            WHERE {_quote_identifier(SCIENCE_FIELD_COLUMN)} IS NOT NULL
              AND TRIM(CAST({_quote_identifier(SCIENCE_FIELD_COLUMN)} AS TEXT)) != ''
            ORDER BY {_quote_identifier(SCIENCE_FIELD_COLUMN)} COLLATE NOCASE
            '''
        ).fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0]).strip()]


def load_data() -> pd.DataFrame:
    """Совместимая обёртка для загрузки метаданных диссертаций."""
    return load_dissertation_metadata()


def load_basic_scores(profile_source_id: str = "pedagogy_5_8") -> pd.DataFrame:
    """Совместимая обёртка для загрузки профилей диссертаций."""
    return load_dissertation_scores(profile_source_id=profile_source_id)


def _get_table_columns(table_name: str) -> set[str]:
    """Возвращает набор столбцов таблицы SQLite."""
    with get_sqlite_connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def fetch_dissertation_metadata_by_codes(
    codes: list[str] | set[str],
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Загружает метаданные диссертаций по списку Code."""
    normalized = [str(code).strip() for code in codes if str(code).strip()]
    if not normalized:
        selected = ["Code"] if columns is None else list(dict.fromkeys(["Code", *columns]))
        return pd.DataFrame(columns=selected)

    existing = _get_table_columns("diss_metadata")
    if columns is None:
        selected = ["Code", *[c for c in sorted(existing) if c != "Code"]]
    else:
        unknown = [c for c in columns if c not in existing]
        if unknown:
            raise ValueError(f"Неизвестные столбцы метаданных: {', '.join(unknown)}")
        selected = list(dict.fromkeys(["Code", *columns]))

    frames: list[pd.DataFrame] = []
    with get_sqlite_connection() as conn:
        for i in range(0, len(normalized), 500):
            chunk = normalized[i:i + 500]
            placeholders = ",".join(["?"] * len(chunk))
            col_sql = ", ".join(_quote_identifier(c) for c in selected)
            query = f'SELECT {col_sql} FROM diss_metadata WHERE "Code" IN ({placeholders})'
            frames.append(pd.read_sql_query(query, conn, params=chunk))

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=selected)
    if "Code" in out.columns:
        out["Code"] = out["Code"].astype(str).str.strip()
    return out


def fetch_dissertation_codes_by_year_range(year_from: int, year_to: int) -> set[str]:
    """Возвращает Code диссертаций, защищённых в заданном диапазоне лет."""
    if year_from > year_to:
        raise ValueError("Начальный год не может быть больше конечного года.")
    with get_sqlite_connection() as conn:
        rows = conn.execute(
            """
            SELECT "Code"
            FROM diss_metadata
            WHERE "Code" IS NOT NULL
              AND TRIM(CAST("Code" AS TEXT)) != ''
              AND CAST("year" AS INTEGER) BETWEEN ? AND ?
            """,
            (year_from, year_to),
        ).fetchall()
    return {str(row[0]).strip() for row in rows if str(row[0]).strip()}


def fetch_dissertation_codes_by_year(year: int) -> set[str]:
    """Возвращает Code диссертаций, защищённых в заданный год."""
    return fetch_dissertation_codes_by_year_range(year, year)


def fetch_dissertation_text_candidates(
    columns: list[str],
    query: str,
    *,
    use_like_prefilter: bool = True,
) -> pd.DataFrame:
    """Возвращает кандидатов для текстового поиска.

Если use_like_prefilter=True, SQLite заранее ограничивает строки через LIKE.
Если False, возвращаются все непустые значения выбранных колонок, чтобы Python мог выполнить нечёткое сопоставление.
"""
    if any(col not in SCHOOL_SEARCH_TEXT_COLUMNS for col in columns):
        bad = [col for col in columns if col not in SCHOOL_SEARCH_TEXT_COLUMNS]
        raise ValueError(f"Недопустимые столбцы для поиска: {', '.join(bad)}")
    normalized_query = str(query).strip()
    if not normalized_query:
        return pd.DataFrame(columns=["Code", "column", "value"])

    existing = _get_table_columns("diss_metadata")
    safe_columns = [col for col in columns if col in existing]
    if not safe_columns:
        raise ValueError("В базе отсутствуют запрошенные столбцы для поиска.")

    frames: list[pd.DataFrame] = []
    like_value = f"%{normalized_query}%"
    with get_sqlite_connection() as conn:
        for col in safe_columns:
            where_like = f" AND {_like_expr(col)}" if use_like_prefilter else ""
            query_sql = f"""
                SELECT
                    CAST("Code" AS TEXT) AS Code,
                    ? AS "column",
                    CAST({_quote_identifier(col)} AS TEXT) AS value
                FROM diss_metadata
                WHERE "Code" IS NOT NULL
                  AND TRIM(CAST("Code" AS TEXT)) != ''
                  AND {_quote_identifier(col)} IS NOT NULL
                  AND TRIM(CAST({_quote_identifier(col)} AS TEXT)) != ''
                  {where_like}
            """
            params = [col]
            if use_like_prefilter:
                params.append(like_value)
            frames.append(pd.read_sql_query(query_sql, conn, params=params))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["Code", "column", "value"])
    if out.empty:
        return out
    out["Code"] = out["Code"].astype(str).str.strip()
    out["value"] = out["value"].astype(str).str.strip()
    return out[(out["Code"] != "") & (out["value"] != "")].reset_index(drop=True)


def fetch_candidate_name_options() -> list[str]:
    """Возвращает список ФИО авторов диссертаций для выбора в интерфейсе."""
    return _fetch_candidate_name_options_cached(get_db_signature())


@st.cache_data(show_spinner=False)
def _fetch_candidate_name_options_cached(db_signature: tuple[str, float, int]) -> list[str]:
    """Загружает список ФИО авторов из SQLite с кэшированием."""
    _ = db_signature
    with get_sqlite_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT "candidate_name"
            FROM diss_metadata
            WHERE "candidate_name" IS NOT NULL
              AND TRIM(CAST("candidate_name" AS TEXT)) != ''
            ORDER BY "candidate_name" COLLATE NOCASE
            """
        ).fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0]).strip()]
