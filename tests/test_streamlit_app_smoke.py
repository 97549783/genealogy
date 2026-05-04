from __future__ import annotations

import sqlite3

from streamlit.testing.v1 import AppTest


def _create_minimal_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE diss_metadata (Code TEXT, candidate_name TEXT, `supervisors_1.name` TEXT, `supervisors_2.name` TEXT)")
    conn.execute("INSERT INTO diss_metadata VALUES ('1','Иванов И.И.','Петров П.П.','')")
    conn.execute("CREATE TABLE diss_scores_5_8 (Code TEXT, `1` REAL)")
    conn.execute("INSERT INTO diss_scores_5_8 VALUES ('1', 1.0)")
    conn.execute("CREATE TABLE articles_metadata (Article_id TEXT, Authors TEXT, Title TEXT, Journal TEXT, Volume TEXT, Issue TEXT, Year TEXT, school TEXT)")
    conn.execute("INSERT INTO articles_metadata VALUES ('a1','A','T','J','1','1','2024','S')")
    conn.execute("CREATE TABLE articles_scores_inf_edu (Article_id TEXT, `1` REAL)")
    conn.execute("INSERT INTO articles_scores_inf_edu VALUES ('a1', 1.0)")
    conn.commit()
    conn.close()


def test_streamlit_app_imports_and_builds_tabs(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file("streamlit_app.py")
    app.run(timeout=30)
    assert not app.exception


def test_streamlit_app_respects_tab_query_param(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file("streamlit_app.py")
    app.query_params["tab"] = "profiles"
    app.run(timeout=30)
    assert not app.exception
    assert app.query_params["tab"] == ["profiles"]


def test_streamlit_app_admin_secret_short_circuits(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file("streamlit_app.py")
    app.query_params["secret"] = "nb39fdv94beraaagv2evdc9ewr3fokv"
    app.run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 0
    assert any("Обратная связь" in t.value for t in app.title)
