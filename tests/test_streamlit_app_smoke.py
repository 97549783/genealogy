from __future__ import annotations

import sqlite3
from pathlib import Path

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


def test_streamlit_app_imports_and_builds_navigation(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 0
    assert any("main-navigation" in item.value and "Анализ статей (демо)" in item.value and "Школы по источникам (демо)" in item.value for item in app.markdown)


def test_streamlit_app_has_registry_labels_in_navigation(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.run(timeout=30)

    assert not app.exception
    navigation = next(item.value for item in app.markdown if "main-navigation" in item.value)
    assert "Поиск диссертаций" in navigation
    assert "Поиск информации о диссертациях" not in navigation
    assert "Поиск по тематическим профилям" not in navigation
    assert "Школы по источникам (демо)" in navigation


def test_streamlit_app_admin_secret_short_circuits(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.query_params["secret"] = "nb39fdv94beraaagv2evdc9ewr3fokv"
    app.run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 0
    assert any("Обратная связь" in t.value for t in app.title)
    assert not any("main-navigation" in item.value for item in app.markdown)


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

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.run(timeout=30)

    assert not app.exception
    assert len(app.tabs) == 0
    assert any("aria-current=\"page\"" in item.value for item in app.markdown)

    all_text = _visible_text(app)

    assert "Режим поиска" not in all_text
    assert "Загружено" not in all_text


def test_streamlit_app_renders_new_dissertation_search_tab(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.query_params["tab"] = "dissertation_search"
    app.run(timeout=30)

    assert not app.exception
    all_text = _visible_text(app)
    assert "Поиск диссертаций" in all_text


def test_streamlit_app_renders_source_schools_tab(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_minimal_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.query_params["tab"] = "source_schools"
    app.run(timeout=30)

    assert not app.exception
    all_text = _visible_text(app)
    assert "Школы по источникам (демо)" in all_text
    assert app.selectbox[0].label == "Научная школа"
    assert "Лев Семёнович Выготский" in app.selectbox[0].options
