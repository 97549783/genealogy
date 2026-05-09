from __future__ import annotations

import sqlite3
from pathlib import Path

from core.db.articles import load_article_authors, load_article_keywords, load_articles_data


def _create_db_without_optional_tables(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE articles_metadata (Article_id TEXT, Authors TEXT, Title TEXT, Journal TEXT, Volume TEXT, Issue TEXT, Year INTEGER)")
    conn.execute("INSERT INTO articles_metadata VALUES ('1329','Иванов И.И.','Название','Журнал','40','4',2025)")
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
    assert df.loc[0, "1.1.1"] == 4.0
