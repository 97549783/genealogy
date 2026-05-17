"""Отображение таблиц со списком статей."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .data import make_elibrary_url, make_journal_article_url


def _filled_text(value: Any) -> str:
    """Возвращает очищенный текст или пустую строку."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _journal_url(row: pd.Series) -> str:
    """Возвращает сохранённую ссылку статьи или старую ссылку по идентификатору."""
    stored_url = _filled_text(row.get("Article_URL"))
    if stored_url:
        return stored_url
    article_id = _filled_text(row.get("Article_id"))
    return make_journal_article_url(article_id) if article_id else ""


def prepare_articles_results_table(df: pd.DataFrame) -> pd.DataFrame:
    """Готовит таблицу результатов со ссылками на журнал, PDF и Elibrary."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["Сайт журнала", "PDF", "Elibrary"])
    work = df.copy()
    out = pd.DataFrame()
    out["Сайт журнала"] = work.apply(_journal_url, axis=1)
    out["PDF"] = work.get("Article_PDF", pd.Series(index=work.index, dtype=object)).map(_filled_text)
    out["Elibrary"] = work.get("DOI", pd.Series(index=work.index, dtype=object)).apply(make_elibrary_url)
    mapping = {
        "Year": "Год", "Title": "Название", "Authors": "Авторы", "Journal": "Журнал",
        "Volume": "Том", "Issue": "Выпуск", "Pages": "Страницы", "DOI": "DOI", "Keywords": "Ключевые слова",
    }
    for source, target in mapping.items():
        if source in work.columns:
            out[target] = work[source]
    return out
