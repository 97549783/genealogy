from __future__ import annotations

import importlib
import sqlite3
import time

import pandas as pd


def test_load_data_reads_sqlite_and_preserves_expected_columns(monkeypatch, tmp_path):
    db_path = tmp_path / "genealogy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE diss_metadata (Code TEXT, candidate_name TEXT, `supervisors_1.name` TEXT)")
    conn.execute("INSERT INTO diss_metadata VALUES (' 100 ', 'Автор 1', 'Руководитель 1')")
    conn.execute("INSERT INTO diss_metadata VALUES ('', 'Пустой', 'x')")
    conn.commit()
    conn.close()

    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    import core.db.dissertations as dissertations
    importlib.reload(dissertations)
    dissertations._load_dissertation_metadata_cached.clear()

    result = dissertations.load_data()

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 1
    assert dissertations.AUTHOR_COLUMN == "candidate_name"
    assert dissertations.SUPERVISOR_COLUMNS == ["supervisors_1.name", "supervisors_2.name"]
    assert result["Code"].tolist() == ["100"]


def test_fetch_dissertation_metadata_by_codes(monkeypatch, tmp_path):
    db_path = tmp_path / "genealogy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE diss_metadata (Code TEXT, candidate_name TEXT, year TEXT)")
    conn.executemany("INSERT INTO diss_metadata VALUES (?,?,?)", [("1", "А", "2020"), ("2", "Б", "2021")])
    conn.commit()
    conn.close()
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    import core.db.dissertations as dissertations
    importlib.reload(dissertations)
    empty = dissertations.fetch_dissertation_metadata_by_codes([])
    assert empty.empty
    subset = dissertations.fetch_dissertation_metadata_by_codes(["1"], columns=["year"])
    assert set(subset.columns) == {"Code", "year"}
    assert subset.iloc[0]["Code"] == "1"
    try:
        dissertations.fetch_dissertation_metadata_by_codes(["1"], columns=["bad"])
        assert False
    except ValueError:
        assert True


def test_db_signature_changes_after_file_update(monkeypatch, tmp_path):
    db_path = tmp_path / "genealogy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    import core.db.connection as connection
    importlib.reload(connection)

    sig1 = connection.get_db_signature()
    time.sleep(1.1)

    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    sig2 = connection.get_db_signature()
    assert sig1 != sig2


def test_search_and_filter_options_from_sql(monkeypatch, tmp_path):
    db_path = tmp_path / "genealogy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE diss_metadata ("
        "Code TEXT, candidate_name TEXT, title TEXT, year TEXT, city TEXT, institution_prepared TEXT, "
        "`supervisors_1.name` TEXT, `supervisors_2.name` TEXT, "
        "`opponents_1.name` TEXT, `opponents_2.name` TEXT, `opponents_3.name` TEXT, "
        "`specialties_1.code` TEXT, `specialties_1.name` TEXT, `specialties_2.code` TEXT, `specialties_2.name` TEXT)"
    )
    conn.executemany(
        "INSERT INTO diss_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("1", "Иванов И.И.", "Анализ методики", "2020", "Москва", "МГУ", "Петров П.П.", "", "Сидоров С.С.", "", "", "13.00.01", "Общая педагогика", "", ""),
            ("2", "Смирнова А.А.", "Цифровая дидактика", "2021", "Санкт-Петербург", "СПбГУ", "Кузнецов К.К.", "", "Орлова О.О.", "", "", "13.00.08", "Теория и методика", "", ""),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    import core.db.dissertations as dissertations
    importlib.reload(dissertations)

    assert len(dissertations.search_dissertation_metadata({"title": "методики"})) == 1
    assert len(dissertations.search_dissertation_metadata({"candidate_name": "смирнова"})) == 1
    assert len(dissertations.search_dissertation_metadata({"city": "санкт"})) == 1
    assert len(dissertations.search_dissertation_metadata({"year": "2020"})) == 1
    assert len(dissertations.search_dissertation_metadata({"institution_prepared": "мгу"})) == 1
    assert len(dissertations.search_dissertation_metadata({"supervisors": "петров"})) == 1
    assert len(dissertations.search_dissertation_metadata({"opponents": "орлова"})) == 1
    assert len(dissertations.search_dissertation_metadata({"specialties": "13.00.08"})) == 1
    assert len(dissertations.search_dissertation_metadata({"city": "санкт", "year": "2021"})) == 1

    options = dissertations.load_dissertation_filter_options()
    assert options["year"] == ["2021", "2020"]
    assert options["city"] == ["Москва", "Санкт-Петербург"]
    assert "13.00.01" in options["specialties"]
    assert "13.00.08" in options["specialties"]
    assert "" not in options["specialties"]
