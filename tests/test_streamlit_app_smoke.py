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
    assert any(tab.label == "Анализ статей (демо)" for tab in app.tabs)


def test_streamlit_app_has_clean_dissertation_search_top_tab(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file("streamlit_app.py")
    app.run(timeout=30)

    assert not app.exception
    assert any(tab.label == "Поиск диссертаций" for tab in app.tabs)
    assert not any(tab.label == "Поиск информации о диссертациях" for tab in app.tabs)
    assert not any(tab.label == "Поиск по тематическим профилям" for tab in app.tabs)


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


def _visible_text(app: AppTest) -> str:
    return "\n".join(
        getattr(item, "value", "")
        for collection in [
            app.markdown,
            app.caption,
            app.success,
            app.warning,
            app.error,
            app.text,
            app.title,
            app.subheader,
        ]
        for item in collection
    )


def test_streamlit_app_lazy_renders_only_default_tab(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file("streamlit_app.py")
    app.run(timeout=30)

    assert not app.exception
    assert any(tab.label == "Построение деревьев" for tab in app.tabs)

    all_text = _visible_text(app)

    assert "Режим поиска" not in all_text
    assert "Загружено" not in all_text


def test_streamlit_app_renders_new_dissertation_search_tab(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file("streamlit_app.py")
    app.query_params["tab"] = "dissertation_search"
    app.run(timeout=30)

    assert not app.exception
    all_text = _visible_text(app)
    assert "Поиск диссертаций" in all_text
