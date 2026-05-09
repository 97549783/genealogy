"""Отображение таблиц со списком статей."""

from __future__ import annotations

import pandas as pd

from .data import make_elibrary_url, make_journal_article_url


def prepare_articles_results_table(df: pd.DataFrame) -> pd.DataFrame:
    """Готовит таблицу результатов со ссылками на журнал и Elibrary."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["Сайт журнала", "Elibrary"])
    work = df.copy()
    out = pd.DataFrame()
    out["Сайт журнала"] = work.get("Article_id", pd.Series(index=work.index, dtype=object)).apply(make_journal_article_url)
    out["Elibrary"] = work.get("DOI", pd.Series(index=work.index, dtype=object)).apply(make_elibrary_url)
    mapping = {
        "Year": "Год", "Title": "Название", "Authors": "Авторы", "Journal": "Журнал",
        "Volume": "Том", "Issue": "Выпуск", "Pages": "Страницы", "DOI": "DOI", "Keywords": "Ключевые слова",
    }
    for source, target in mapping.items():
        if source in work.columns:
            out[target] = work[source]
    return out
