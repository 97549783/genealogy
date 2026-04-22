from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_streamlit_app_imports_and_builds_tabs() -> None:
    app = AppTest.from_file("streamlit_app.py")
    app.run(timeout=30)
    assert not app.exception
    assert len(app.tabs) >= 8


def test_streamlit_app_respects_tab_query_param() -> None:
    app = AppTest.from_file("streamlit_app.py")
    app.query_params["tab"] = "profiles"
    app.run(timeout=30)
    assert not app.exception
    assert app.tabs[2].label == "Поиск по тематическим профилям"
    assert app.query_params["tab"] == ["profiles"]


def test_streamlit_app_admin_secret_short_circuits() -> None:
    app = AppTest.from_file("streamlit_app.py")
    app.query_params["secret"] = "nb39fdv94beraaagv2evdc9ewr3fokv"
    app.run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 0
    assert any("Обратная связь" in t.value for t in app.title)
