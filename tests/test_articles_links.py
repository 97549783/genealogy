from __future__ import annotations

import pandas as pd

from tabs.articles.data import make_elibrary_url, make_journal_article_url
from tabs.articles.results_table import prepare_articles_results_table


def test_article_link_helpers() -> None:
    assert make_journal_article_url("1329") == "https://info.infojournal.ru/jour/article/view/1329"
    assert make_elibrary_url("10.32517/0234-0453-2025-40-4-76-86") == "https://elibrary.ru/10.32517/0234-0453-2025-40-4-76-86"
    assert make_elibrary_url("") == ""
    assert make_elibrary_url(None) == ""


def test_results_table_uses_legacy_article_url_when_stored_url_is_empty() -> None:
    df = pd.DataFrame([{"Article_id": "1329", "Article_URL": "", "Article_PDF": ""}])

    result = prepare_articles_results_table(df)

    assert result.loc[0, "Сайт журнала"] == "https://info.infojournal.ru/jour/article/view/1329"
    assert result.loc[0, "PDF"] == ""


def test_results_table_uses_stored_article_and_pdf_links() -> None:
    df = pd.DataFrame([
        {
            "Article_id": "mspu-1",
            "Article_URL": "https://example.test/article",
            "Article_PDF": "https://example.test/article.pdf",
        }
    ])

    result = prepare_articles_results_table(df)

    assert result.loc[0, "Сайт журнала"] == "https://example.test/article"
    assert result.loc[0, "PDF"] == "https://example.test/article.pdf"


def test_results_table_shows_thematic_profile_availability_for_unscored_articles() -> None:
    df = pd.DataFrame([
        {
            "Article_id": "mspu-1",
            "Article_URL": "https://example.test/article",
            "Article_PDF": "https://example.test/article.pdf",
            "Has_thematic_scores": False,
        }
    ])

    result = prepare_articles_results_table(df)

    assert result.loc[0, "Есть тематический профиль"] == "Нет"
    assert result.loc[0, "Сайт журнала"] == "https://example.test/article"
    assert result.loc[0, "PDF"] == "https://example.test/article.pdf"
