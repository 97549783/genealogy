"""Общие функции загрузки тематических профилей диссертаций."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.domain.profile_sources import ProfileSource, get_profile_source

from .connection import get_db_signature, get_sqlite_connection

NON_SCORE_COLUMNS = {
    "Code",
    "Article_id",
    "title",
    "supervisor",
    "institution_prepared",
    "year",
}

_ALLOWED_SCORE_TABLES = {
    "diss_scores_5_8",
    "diss_scores_2_3",
    "articles_scores_inf_edu",
}


def _validate_table_name(table_name: str) -> str:
    """Проверяет имя таблицы перед подстановкой в SQL-запрос."""
    if table_name not in _ALLOWED_SCORE_TABLES:
        raise ValueError(f"Недопустимое имя таблицы профилей: {table_name}")
    return table_name


def load_scores_from_sqlite(table_name: str, key_column: str = "Code") -> pd.DataFrame:
    """Загружает и нормализует профили из таблицы SQLite."""
    return _load_scores_from_sqlite_cached(table_name, key_column, get_db_signature())


@st.cache_data(show_spinner=False)
def _load_scores_from_sqlite_cached(
    table_name: str,
    key_column: str,
    db_signature: tuple[str, float, int],
) -> pd.DataFrame:
    """Загружает и нормализует профили из таблицы SQLite с кэшированием."""
    _ = db_signature
    safe_table = _validate_table_name(table_name)
    with get_sqlite_connection() as conn:
        scores = pd.read_sql_query(f'SELECT * FROM "{safe_table}"', conn)

    if key_column not in scores.columns:
        raise KeyError(f"В таблице профилей отсутствует столбец '{key_column}'")

    scores = scores.dropna(subset=[key_column])
    scores[key_column] = scores[key_column].astype(str).str.strip().astype(object)
    scores = scores[scores[key_column].str.len() > 0]
    scores = scores.drop_duplicates(subset=[key_column], keep="first")

    feature_columns = get_all_feature_columns(scores, key_column=key_column)
    if not feature_columns:
        raise ValueError("Не найдены столбцы с тематическими компонентами")

    scores[feature_columns] = scores[feature_columns].apply(pd.to_numeric, errors="coerce")
    scores[feature_columns] = scores[feature_columns].fillna(0.0)
    return scores


def load_dissertation_scores(profile_source_id: str = "pedagogy_5_8") -> pd.DataFrame:
    """Загружает профили диссертаций из SQLite для выбранного источника профилей."""
    source = get_profile_source(profile_source_id)
    return load_scores_from_sqlite(source.score_table, key_column=source.key_column)


def load_dissertation_scores_for_source(source: ProfileSource) -> pd.DataFrame:
    """Загружает профили диссертаций для уже выбранного источника профилей."""
    return load_scores_from_sqlite(source.score_table, key_column=source.key_column)


def _source_table_and_key(profile_source_id: str | None) -> tuple[str, str]:
    source = get_profile_source(profile_source_id)
    return source.score_table, source.key_column


def load_article_scores() -> pd.DataFrame:
    """Загружает профили статей из SQLite."""
    return load_scores_from_sqlite("articles_scores_inf_edu", key_column="Article_id")


def get_all_feature_columns(scores_df: pd.DataFrame, key_column: str = "Code") -> list[str]:
    """Возвращает все столбцы признаков, кроме служебного Code."""
    excluded = set(NON_SCORE_COLUMNS)
    excluded.add(key_column)
    return [column for column in scores_df.columns if column not in excluded]


def get_numeric_code_feature_columns(scores_df: pd.DataFrame) -> list[str]:
    """Возвращает признаки-коды классификатора, начинающиеся с цифры."""
    return [
        column
        for column in scores_df.columns
        if column != "Code" and len(column) > 0 and column[0].isdigit()
    ]


def _quote_identifier(identifier: str) -> str:
    """Экранирует имя идентификатора SQLite."""
    return '"' + identifier.replace('"', '""') + '"'


def _table_columns(table_name: str) -> list[str]:
    with get_sqlite_connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    return [row[1] for row in rows]


def get_score_feature_columns_from_table(
    table_name: str = "diss_scores_5_8",
    key_column: str = "Code",
) -> list[str]:
    """Возвращает список признаков профилей из таблицы SQLite."""
    return _get_score_feature_columns_from_table_cached(
        table_name=table_name,
        key_column=key_column,
        db_signature=get_db_signature(),
    )


@st.cache_data(show_spinner=False)
def _get_score_feature_columns_from_table_cached(
    table_name: str,
    key_column: str,
    db_signature: tuple[str, float, int],
) -> list[str]:
    """Возвращает кэшированный список признаков профилей."""
    _ = db_signature
    safe_table = _validate_table_name(table_name)
    columns = _table_columns(safe_table)
    return [c for c in columns if c not in NON_SCORE_COLUMNS and c != key_column]


def _is_classifier_node_column(column: str, classifier_node: str) -> bool:
    """Проверяет принадлежность признака узлу классификатора."""
    return column == classifier_node or column.startswith(classifier_node + ".")


def get_score_columns_for_classifier_node(
    classifier_node: str,
    table_name: str = "diss_scores_5_8",
    key_column: str = "Code",
) -> list[str]:
    """Возвращает признаки, относящиеся к выбранному узлу классификатора."""
    node = str(classifier_node).strip()
    if not node:
        return []
    features = get_score_feature_columns_from_table(table_name=table_name, key_column=key_column)
    return [c for c in features if _is_classifier_node_column(c, node)]


def fetch_dissertation_scores_for_node(
    codes: list[str] | set[str],
    classifier_node: str,
    profile_source_id: str = "pedagogy_5_8",
) -> pd.DataFrame:
    """Загружает только признаки выбранного узла классификатора для списка диссертаций."""
    table_name, key_column = _source_table_and_key(profile_source_id)
    node_features = get_score_columns_for_classifier_node(
        classifier_node,
        table_name=table_name,
        key_column=key_column,
    )
    normalized_codes = [str(code).strip() for code in codes if str(code).strip()]
    if not normalized_codes:
        return pd.DataFrame(columns=[key_column, *node_features])
    if not node_features:
        return pd.DataFrame(columns=[key_column])
    out = fetch_scores_by_codes(
        codes=normalized_codes,
        score_columns=node_features,
        table_name=table_name,
        key_column=key_column,
    )
    if key_column in out.columns:
        out[key_column] = out[key_column].astype(str).str.strip()
    return out


def fetch_dissertation_node_score_by_codes(
    codes: list[str] | set[str],
    classifier_node: str,
    profile_source_id: str = "pedagogy_5_8",
) -> pd.DataFrame:
    """Возвращает Code и средний балл по выбранному узлу классификатора."""
    _, key_column = _source_table_and_key(profile_source_id)
    scores = fetch_dissertation_scores_for_node(
        codes,
        classifier_node,
        profile_source_id=profile_source_id,
    )
    if scores.empty or key_column not in scores.columns:
        return pd.DataFrame(columns=[key_column, "node_score"])
    feature_columns = [c for c in scores.columns if c != key_column]
    if not feature_columns:
        return pd.DataFrame(columns=[key_column, "node_score"])
    result = scores[[key_column]].copy()
    result[key_column] = result[key_column].astype(str).str.strip()
    result["node_score"] = scores[feature_columns].mean(axis=1)
    result = result[result[key_column] != ""].drop_duplicates(subset=[key_column], keep="first")
    return result


def fetch_scores_by_codes(
    codes: list[str] | set[str],
    score_columns: list[str] | None = None,
    table_name: str = "diss_scores_5_8",
    key_column: str = "Code",
) -> pd.DataFrame:
    """Загружает профили по списку ключей и выбранным признакам."""
    safe_table = _validate_table_name(table_name)
    all_columns = _table_columns(safe_table)
    if key_column not in all_columns:
        raise ValueError(f"В таблице '{safe_table}' отсутствует ключевой столбец '{key_column}'")

    feature_columns = [c for c in all_columns if c not in NON_SCORE_COLUMNS and c != key_column]
    if score_columns is None:
        selected_features = feature_columns
    else:
        unknown = [c for c in score_columns if c not in feature_columns]
        if unknown:
            raise ValueError(f"Неизвестные столбцы профилей: {', '.join(unknown)}")
        selected_features = list(dict.fromkeys(score_columns))
    select_columns = [key_column, *selected_features]

    normalized = [str(code).strip() for code in codes if str(code).strip()]
    if not normalized:
        return pd.DataFrame(columns=select_columns)

    frames: list[pd.DataFrame] = []
    with get_sqlite_connection() as conn:
        for i in range(0, len(normalized), 500):
            chunk = normalized[i:i + 500]
            placeholders = ",".join(["?"] * len(chunk))
            col_sql = ", ".join(_quote_identifier(c) for c in select_columns)
            query = (
                f"SELECT {col_sql} FROM {_quote_identifier(safe_table)} "
                f"WHERE {_quote_identifier(key_column)} IN ({placeholders})"
            )
            frames.append(pd.read_sql_query(query, conn, params=chunk))

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=select_columns)
    for column in selected_features:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    return out


def search_dissertation_scores_by_codes_threshold(
    selected_score_columns: list[str],
    min_score: float,
    return_columns: list[str] | None = None,
    profile_source_id: str = "pedagogy_5_8",
) -> pd.DataFrame:
    """Ищет диссертации по порогу выбранных тематических признаков."""
    if not selected_score_columns:
        raise ValueError("Нужно выбрать хотя бы один тематический признак.")
    table_name, key_column = _source_table_and_key(profile_source_id)
    all_columns = _table_columns(table_name)
    feature_columns = [c for c in all_columns if c not in NON_SCORE_COLUMNS and c != key_column]
    unknown = [c for c in selected_score_columns if c not in feature_columns]
    if unknown:
        raise ValueError(f"Неизвестные тематические признаки: {', '.join(unknown)}")
    return_cols = selected_score_columns if return_columns is None else return_columns
    bad_return = [c for c in return_cols if c not in feature_columns and c != key_column]
    if bad_return:
        raise ValueError(f"Недопустимые столбцы возврата: {', '.join(bad_return)}")

    where_sql = " AND ".join(f'COALESCE({_quote_identifier(c)}, 0) >= ?' for c in selected_score_columns)
    total_sql = " + ".join(f'COALESCE({_quote_identifier(c)}, 0)' for c in selected_score_columns)
    select_columns = list(dict.fromkeys([key_column, *return_cols]))
    select_sql = ", ".join(_quote_identifier(c) for c in select_columns)
    query = (
        f'SELECT {select_sql}, ({total_sql}) AS profile_total FROM {_quote_identifier(table_name)} '
        f"WHERE {where_sql} ORDER BY profile_total DESC"
    )
    with get_sqlite_connection() as conn:
        out = pd.read_sql_query(query, conn, params=[min_score] * len(selected_score_columns))
    for column in selected_score_columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    return out
