import sqlite3
import importlib
from pathlib import Path

import pandas as pd


def _create_db(path: Path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE diss_metadata (Code TEXT, candidate_name TEXT, title TEXT)")
    conn.execute("INSERT INTO diss_metadata VALUES (' 123 ', 'Иванов И.И.', 'Тест')")
    conn.execute("INSERT INTO diss_metadata VALUES ('', 'Пустой', 'bad')")

    conn.execute("CREATE TABLE diss_scores_5_8 (Code TEXT, title TEXT, year TEXT, `1.1` TEXT)")
    conn.execute("INSERT INTO diss_scores_5_8 VALUES ('123', 'meta', '2020', '4.5')")

    conn.execute('CREATE TABLE diss_scores_2_3 (Code TEXT, "1" INTEGER, "1.1.1.1" INTEGER, "2.4.2.3" INTEGER)')
    conn.execute('INSERT INTO diss_scores_2_3 VALUES ("123", 2, 5, 7)')

    conn.execute("CREATE TABLE articles_metadata (Article_id TEXT, Authors TEXT, Title TEXT, Journal TEXT, Volume TEXT, Issue TEXT, Year TEXT, school TEXT)")
    conn.execute("INSERT INTO articles_metadata VALUES ('A1','Автор','Статья','Журнал','1','1','2024','Школа')")

    conn.execute("CREATE TABLE articles_scores_inf_edu (Article_id TEXT, `1.1` TEXT)")
    conn.execute("INSERT INTO articles_scores_inf_edu VALUES ('A1','3.2')")
    conn.commit()
    conn.close()


def test_sqlite_loaders(tmp_path, monkeypatch):
    db_path = tmp_path / "genealogy.db"
    _create_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    import core.db.connection as connection
    import core.db.dissertations as dissertations
    import core.db.scores as scores
    import core.db.articles as articles

    importlib.reload(connection)
    importlib.reload(scores)
    importlib.reload(dissertations)
    importlib.reload(articles)

    dissertations._load_dissertation_metadata_cached.clear()
    meta = dissertations.load_dissertation_metadata()
    assert set(meta["Code"].tolist()) == {"123"}

    diss_scores = scores.load_dissertation_scores()
    assert diss_scores["Code"].dtype == object
    assert pd.api.types.is_numeric_dtype(diss_scores["1.1"])
    assert "title" not in scores.get_all_feature_columns(diss_scores, key_column="Code")

    merged = articles.load_articles_data()
    assert merged["Article_id"].dtype == object
    assert pd.api.types.is_numeric_dtype(merged["1.1"])
    by_code = scores.fetch_scores_by_codes(["123"], score_columns=["1.1"])
    assert list(by_code.columns) == ["Code", "1.1"]
    assert by_code.iloc[0]["Code"] == "123"
    filtered = scores.search_dissertation_scores_by_codes_threshold(["1.1"], 4.0)
    assert "profile_total" in filtered.columns

    it_scores = scores.load_dissertation_scores(profile_source_id="it_2_3")
    assert it_scores["Code"].dtype == object
    assert pd.api.types.is_numeric_dtype(it_scores["1.1.1.1"])

    it_by_code = scores.fetch_scores_by_codes(
        ["123"],
        score_columns=["1.1.1.1"],
        table_name="diss_scores_2_3",
    )
    assert list(it_by_code.columns) == ["Code", "1.1.1.1"]

    it_node_scores = scores.fetch_dissertation_node_score_by_codes(
        {"123"},
        "2.4",
        profile_source_id="it_2_3",
    )
    assert it_node_scores.iloc[0]["Code"] == "123"
    assert it_node_scores.iloc[0]["node_score"] == 7


def test_runtime_modules_without_csv_patterns():
    banned = [
        "pd.read_csv",
        'glob("*.csv")',
        "load_scores_from_folder",
        "db_lineages",
        "articles_scores.csv",
        "CSV-файлы",
    ]
    allowed_files = {
        "tabs/profiles/topics_mode.py",
    }

    for root in (Path("tabs"), Path("core/db")):
        for path in root.rglob("*.py"):
            rel = path.as_posix()
            if rel in allowed_files:
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in banned:
                assert pattern not in text, f"Найден запрещённый паттерн {pattern} в {rel}"


def test_score_node_helpers(tmp_path, monkeypatch):
    db_path = tmp_path / "genealogy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE diss_metadata (Code TEXT, candidate_name TEXT)")
    conn.execute("INSERT INTO diss_metadata VALUES ('A','Автор')")
    conn.execute('CREATE TABLE diss_scores_5_8 (Code TEXT, title TEXT, year TEXT, "1" REAL, "1.1" REAL, "1.1.1" REAL, "1.2" REAL, "2" REAL, "10" REAL, "10.1" REAL)')
    conn.execute('INSERT INTO diss_scores_5_8 VALUES ("A","t","2020",1,2,3,4,10,7,8)')
    conn.execute('CREATE TABLE diss_scores_2_3 (Code TEXT, "1" INTEGER, "1.1.1.1" INTEGER, "2.4.2.3" INTEGER)')
    conn.execute('INSERT INTO diss_scores_2_3 VALUES ("A", 2, 5, 7)')
    conn.execute("CREATE TABLE articles_metadata (Article_id TEXT, Authors TEXT, Title TEXT, Journal TEXT, Volume TEXT, Issue TEXT, Year TEXT, school TEXT)")
    conn.execute("INSERT INTO articles_metadata VALUES ('A1','Автор','Статья','Журнал','1','1','2024','Школа')")
    conn.execute("CREATE TABLE articles_scores_inf_edu (Article_id TEXT, `1.1` TEXT)")
    conn.execute("INSERT INTO articles_scores_inf_edu VALUES ('A1','3.2')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    import core.db.connection as connection
    import core.db.scores as scores
    importlib.reload(connection)
    importlib.reload(scores)
    feats = scores.get_score_feature_columns_from_table()
    assert feats == ["1", "1.1", "1.1.1", "1.2", "2", "10", "10.1"]
    assert scores.get_score_columns_for_classifier_node("1") == ["1", "1.1", "1.1.1", "1.2"]
    assert scores.get_score_columns_for_classifier_node("1.1") == ["1.1", "1.1.1"]
    assert scores.get_score_columns_for_classifier_node("3") == []
    assert scores.get_score_columns_for_classifier_node("2.4", table_name="diss_scores_2_3") == ["2.4.2.3"]
    node_scores = scores.fetch_dissertation_scores_for_node({"A"}, "1.1")
    assert list(node_scores.columns) == ["Code", "1.1", "1.1.1"]
    averaged = scores.fetch_dissertation_node_score_by_codes({"A"}, "1.1")
    assert averaged.iloc[0]["Code"] == "A"
    assert averaged.iloc[0]["node_score"] == 2.5
