"""Подготовка наборов статей для режимов анализа."""

from __future__ import annotations

from typing import Any, Dict, List, Set

import pandas as pd

from core.db.articles import load_article_authors
from .author_matching import canon_article_author_name, get_school_member_initials

ALL_JOURNALS_KEY = "all"

ARTICLE_OUTPUT_COLUMNS = [
    "school", "Article_id", "Authors", "Title", "Journal", "ISSN", "Volume", "Issue", "Year",
    "Abstract", "Keywords", "DOI", "Pages", "Funding", "Article_URL", "Article_PDF",
    "Published_at", "Section", "UDK", "Citation", "Issue_URL", "Issue_PDF",
    "Issue_title", "Issue_serial", "Issue_in_year", "Issue_total_pages", "First_page",
    "Last_page", "Source_pages_text", "Source_article_url", "Year_num",
]


def normalize_journal_key(value: Any) -> str:
    """Нормализует ISSN или другой ключ журнала для фильтрации."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower()


def filter_articles_by_journals(df_articles: pd.DataFrame, selected_journal_keys: list[str]) -> pd.DataFrame:
    """Фильтрует статьи по выбранным журналам."""
    if df_articles is None or df_articles.empty:
        return df_articles
    selected = {normalize_journal_key(value) for value in (selected_journal_keys or [])}
    selected.discard("")
    if not selected or normalize_journal_key(ALL_JOURNALS_KEY) in selected:
        return df_articles

    work = df_articles.copy()
    if "ISSN" not in work.columns:
        return work.iloc[0:0].copy()

    issn_keys = work["ISSN"].map(normalize_journal_key)
    mask = issn_keys.isin(selected)

    if "Journal" in work.columns:
        journal_fallback_keys = work["Journal"].map(lambda value: f"journal:{normalize_journal_key(value)}")
        mask = mask | ((issn_keys == "") & journal_fallback_keys.isin(selected))

    return work[mask].copy()


def make_journal_article_url(article_id: Any) -> str:
    """Создаёт ссылку на страницу статьи на сайте журнала."""
    return f"https://info.infojournal.ru/jour/article/view/{article_id}"


def make_elibrary_url(doi: Any) -> str:
    """Создаёт ссылку на Elibrary по DOI, если DOI заполнен."""
    if doi is None or pd.isna(doi):
        return ""
    value = str(doi).strip()
    return f"https://elibrary.ru/{value}" if value else ""


def _article_ids_for_initials(
    member_initials: Set[str],
    article_authors: pd.DataFrame,
) -> Set[str]:
    """Возвращает идентификаторы статей по совпадению авторов из `article_authors`."""
    if not member_initials or article_authors is None or article_authors.empty:
        return set()
    if "Article_id" not in article_authors.columns or "Name" not in article_authors.columns:
        return set()
    work = article_authors[["Article_id", "Name"]].dropna(subset=["Article_id", "Name"]).copy()
    work["_article_id"] = work["Article_id"].astype(str).str.strip()
    work["_canon"] = work["Name"].astype(str).map(canon_article_author_name)
    work = work[(work["_article_id"] != "") & work["_canon"].isin(member_initials)]
    return set(work["_article_id"].astype(str))


def _ensure_article_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ARTICLE_OUTPUT_COLUMNS:
        if col not in out.columns and col != "school":
            out[col] = ""
    out["Year_num"] = pd.to_numeric(out.get("Year"), errors="coerce") if "Year" in out.columns else 0
    return out


def build_articles_dataset_for_school(
    selected_option: str,
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    df_articles: pd.DataFrame,
    scope: str,
    df_article_authors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Строит набор статей для одной выбранной школы."""
    return build_articles_dataset_for_schools([selected_option], options_meta, df_lineage, idx_lineage, df_articles, scope, df_article_authors=df_article_authors)


def build_articles_dataset_for_schools(
    selected_options: List[str],
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    df_articles: pd.DataFrame,
    scope: str,
    df_article_authors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Строит объединённый набор статей для нескольких школ."""
    if df_articles is None or df_articles.empty or "Article_id" not in df_articles.columns:
        return pd.DataFrame()
    article_authors = df_article_authors if df_article_authors is not None else load_article_authors()
    work = _ensure_article_columns(df_articles)
    work["_article_id"] = work["Article_id"].astype(str).str.strip()
    combined: List[pd.DataFrame] = []
    for option in selected_options:
        initials = get_school_member_initials(option, options_meta, df_lineage, idx_lineage, scope)
        if not initials:
            continue
        article_ids = _article_ids_for_initials(initials, article_authors)
        if not article_ids:
            continue
        sub = work[work["_article_id"].isin(article_ids)].copy()
        if sub.empty:
            continue
        sub["school"] = option
        combined.append(sub)
    if not combined:
        return pd.DataFrame()
    out = pd.concat(combined, ignore_index=True).drop(columns=["_article_id"], errors="ignore")
    ordered = [col for col in ARTICLE_OUTPUT_COLUMNS if col in out.columns]
    rest = [col for col in out.columns if col not in ordered]
    return out[ordered + rest]
