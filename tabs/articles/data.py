"""Подготовка наборов статей для режимов анализа."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

import pandas as pd

from .author_matching import canon_initials, get_school_member_initials

ARTICLE_OUTPUT_COLUMNS = [
    "school", "Article_id", "Authors", "Title", "Journal", "ISSN", "Volume", "Issue", "Year",
    "Abstract", "Keywords", "DOI", "Pages", "Funding", "Year_num",
]


def make_journal_article_url(article_id: Any) -> str:
    """Создаёт ссылку на страницу статьи на сайте журнала."""
    return f"https://info.infojournal.ru/jour/article/view/{article_id}"


def make_elibrary_url(doi: Any) -> str:
    """Создаёт ссылку на Elibrary по DOI, если DOI заполнен."""
    if doi is None or pd.isna(doi):
        return ""
    value = str(doi).strip()
    return f"https://elibrary.ru/{value}" if value else ""


def _authors_set(raw: Any) -> Set[str]:
    return {canon_initials(part) for part in re.split(r"[;]", str(raw or "")) if canon_initials(part)}


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
) -> pd.DataFrame:
    """Строит набор статей для одной выбранной школы."""
    return build_articles_dataset_for_schools([selected_option], options_meta, df_lineage, idx_lineage, df_articles, scope)


def build_articles_dataset_for_schools(
    selected_options: List[str],
    options_meta: Dict[str, str],
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    df_articles: pd.DataFrame,
    scope: str,
) -> pd.DataFrame:
    """Строит объединённый набор статей для нескольких школ."""
    if df_articles is None or df_articles.empty or "Authors" not in df_articles.columns:
        return pd.DataFrame()
    work = _ensure_article_columns(df_articles)
    work["_authors_set"] = work["Authors"].apply(_authors_set)
    combined: List[pd.DataFrame] = []
    for option in selected_options:
        initials = get_school_member_initials(option, options_meta, df_lineage, idx_lineage, scope)
        if not initials:
            continue
        sub = work[work["_authors_set"].apply(lambda values: not values.isdisjoint(initials))].copy()
        if sub.empty:
            continue
        sub["school"] = option
        combined.append(sub)
    if not combined:
        return pd.DataFrame()
    out = pd.concat(combined, ignore_index=True).drop(columns=["_authors_set"], errors="ignore")
    ordered = [col for col in ARTICLE_OUTPUT_COLUMNS if col in out.columns]
    rest = [col for col in out.columns if col not in ordered]
    return out[ordered + rest]
