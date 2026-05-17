from __future__ import annotations

import sqlite3
from pathlib import Path

from core.db.articles import load_article_authors, load_article_keywords, load_articles_data, load_available_article_journals


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


def test_load_articles_data_still_merges_metadata_and_scores(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_db_without_optional_tables(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    df = load_articles_data()

    assert df.loc[0, "Article_id"] == "1329"
    assert df.loc[0, "Title"] == "Название"
    assert df.loc[0, "ISSN"] == "0234-0453"
    assert df.loc[0, "Article_URL"] == ""
    assert df.loc[0, "Article_PDF"] == ""
    assert df.loc[0, "1.1.1"] == 4.0


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
