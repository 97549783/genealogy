from __future__ import annotations

import importlib
import sqlite3

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
    dissertations.load_dissertation_metadata.clear()
    dissertations.load_data.clear()

    result = dissertations.load_data()

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 1
    assert dissertations.AUTHOR_COLUMN == "candidate_name"
    assert dissertations.SUPERVISOR_COLUMNS == ["supervisors_1.name", "supervisors_2.name"]
    assert result["Code"].tolist() == ["100"]
