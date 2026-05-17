from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from core.db.articles import load_article_authors, load_article_keywords, load_articles_data, load_available_article_journals
from tabs.articles.data import filter_articles_by_journals, filter_articles_with_thematic_scores
from tabs.articles.tab import build_available_journal_options


def _create_db_without_optional_tables(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE articles_metadata (
            Article_id TEXT, Authors TEXT, Title TEXT, Journal TEXT, ISSN TEXT, Volume TEXT,
            Issue TEXT, Year INTEGER, Abstract TEXT, Keywords TEXT, DOI TEXT, Pages TEXT,
            Funding TEXT, Article_URL TEXT, Article_PDF TEXT, Published_at TEXT, Section TEXT,
            UDK TEXT, Citation TEXT, Issue_URL TEXT, Issue_PDF TEXT, Issue_title TEXT,
            Issue_serial INTEGER, Issue_in_year INTEGER, Issue_total_pages INTEGER,
            First_page INTEGER, Last_page INTEGER, Source_pages_text TEXT, Source_article_url TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO articles_metadata VALUES (
            '1329','Иванов И.И.','Название','Журнал','0234-0453','40','4',2025,
            '', '', '10.1', '1-2', '', '', '', '', '', '', '', '', '', '',
            1, 4, 100, 1, 2, '', ''
        )
        """
    )
    conn.execute("CREATE TABLE articles_scores_inf_edu (Article_id TEXT, `1.1.1` REAL)")
    conn.execute("INSERT INTO articles_scores_inf_edu VALUES ('1329', 4.0)")
    conn.commit()
    conn.close()


def test_article_optional_loaders_return_expected_empty_columns(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_db_without_optional_tables(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    assert load_article_authors().columns.tolist() == ["id", "Article_id", "ISSN", "Author_order", "Name", "Affiliation", "Country", "City", "Details"]
    assert load_article_keywords().columns.tolist() == ["id", "Article_id", "ISSN", "Keyword_order", "Keyword"]


def test_load_articles_data_keeps_metadata_only_articles(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_db_without_optional_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO articles_metadata VALUES (
                '2000','Петров П.П.','Без профиля','Другой журнал','2072-9014','1','1',2024,
                '', '', '', '', '', 'https://example.test/a', 'https://example.test/a.pdf', '', '', '', '', '', '', '',
                1, 1, 10, 1, 2, '', ''
            )
            """
        )
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    df = load_articles_data().sort_values("Article_id").reset_index(drop=True)

    assert df["Article_id"].tolist() == ["1329", "2000"]
    assert bool(df.loc[0, "Has_thematic_scores"]) is True
    assert bool(df.loc[1, "Has_thematic_scores"]) is False
    assert df.loc[0, "1.1.1"] == 4.0
    assert pd.isna(df.loc[1, "1.1.1"])
    assert df.loc[1, "Article_URL"] == "https://example.test/a"
    assert df.loc[1, "Article_PDF"] == "https://example.test/a.pdf"


def test_load_available_article_journals_returns_aggregates(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_db_without_optional_tables(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    df = load_available_article_journals()

    assert df.loc[0, "ISSN"] == "0234-0453"
    assert df.loc[0, "Journal"] == "Журнал"
    assert df.loc[0, "article_count"] == 1
    assert df.loc[0, "first_year"] == 2025
    assert df.loc[0, "last_year"] == 2025


def test_journal_options_and_filter_include_metadata_only_articles() -> None:
    df = pd.DataFrame([
        {"Article_id": "1329", "Journal": "Журнал", "ISSN": "0234-0453", "Year": 2025, "Has_thematic_scores": True, "1.1.1": 4.0},
        {"Article_id": "2000", "Journal": "Другой журнал", "ISSN": "2072-9014", "Year": 2024, "Has_thematic_scores": False, "1.1.1": pd.NA},
    ])

    options = build_available_journal_options(df)
    filtered = filter_articles_by_journals(df, ["2072-9014"])

    assert {option["key"] for option in options} == {"0234-0453", "2072-9014"}
    assert filtered["Article_id"].tolist() == ["2000"]
    assert bool(filtered.iloc[0]["Has_thematic_scores"]) is False


def test_filter_articles_with_thematic_scores_keeps_only_scored_articles() -> None:
    df = pd.DataFrame([
        {"Article_id": "1329", "Has_thematic_scores": True},
        {"Article_id": "2000", "Has_thematic_scores": False},
    ])

    result = filter_articles_with_thematic_scores(df)

    assert result["Article_id"].tolist() == ["1329"]
