from __future__ import annotations

from contextlib import nullcontext
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from core.ui import table_display as td


def _df(n: int) -> pd.DataFrame:
    return pd.DataFrame({"Code": [f"C{i:03d}" for i in range(n)], "candidate_name": [f"Автор {i}" for i in range(n)]})


def test_paginate_dataframe_edges_and_order() -> None:
    empty_page, page, total = td.paginate_dataframe(_df(0), 1, 100)
    assert empty_page.empty
    assert page == 1
    assert total == 1

    page_df, page, total = td.paginate_dataframe(_df(50), 1, 100)
    assert len(page_df) == 50
    assert page == 1
    assert total == 1

    page_df, page, total = td.paginate_dataframe(_df(200), 2, 100)
    assert len(page_df) == 100
    assert page == 2
    assert total == 2
    assert page_df["Code"].tolist()[0] == "C100"

    page_df, page, total = td.paginate_dataframe(_df(201), 3, 100)
    assert page_df["Code"].tolist() == ["C200"]
    assert page == 3
    assert total == 3

    below, page, _ = td.paginate_dataframe(_df(5), 0, 2)
    assert page == 1
    assert below["Code"].tolist() == ["C000", "C001"]

    above, page, _ = td.paginate_dataframe(_df(5), 99, 2)
    assert page == 3
    assert above["Code"].tolist() == ["C004"]


def test_result_signature_uses_context_parts_instead_of_full_value_hash() -> None:
    first = pd.DataFrame([{"Code": "A", "title": "Старое", "year": "2020"}])
    second = pd.DataFrame([{"Code": "A", "title": "Новое", "year": "2020"}])
    assert td.build_dissertation_result_signature(first) == td.build_dissertation_result_signature(second)
    assert td.build_dissertation_result_signature(first, context_parts=(("db", 1.0, 1),)) != td.build_dissertation_result_signature(second, context_parts=(("db", 2.0, 1),))


class _FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    column_config = st.column_config
    session_state: dict

    def __init__(self, clicked: str | None = None):
        self.session_state = {}
        self.clicked = clicked
        self.dataframe_rows = None
        self.downloads = []
        self.errors = []

    def expander(self, *args, **kwargs):
        return nullcontext()

    def info(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def selectbox(self, *args, **kwargs):
        return 100

    def number_input(self, *args, **kwargs):
        return kwargs.get("value", 1)

    def dataframe(self, df, **kwargs):
        self.dataframe_rows = len(df)

    def columns(self, n):
        return [_FakeColumn() for _ in range(n)]

    def button(self, label, **kwargs):
        return self.clicked == label

    def spinner(self, *args, **kwargs):
        return nullcontext()

    def download_button(self, **kwargs):
        self.downloads.append(kwargs)

    def error(self, message):
        self.errors.append(message)


def test_widget_initial_render_is_lazy_and_paginates(monkeypatch) -> None:
    fake = _FakeStreamlit()
    monkeypatch.setattr(td, "build_tree_st_dataframe_df", lambda subset: (pd.DataFrame({"x": range(len(subset))}), {}))
    monkeypatch.setattr(td, "build_dissertations_xlsx_bytes", lambda subset: (_ for _ in ()).throw(AssertionError("xlsx")))
    monkeypatch.setattr(td, "build_dissertations_csv_bytes", lambda subset: (_ for _ in ()).throw(AssertionError("csv")))
    monkeypatch.setattr(td, "st", fake, raising=False)
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake)

    td.render_dissertations_widget(_df(250), key="review", page_size=100)

    assert fake.dataframe_rows == 100
    assert fake.downloads == []


def test_widget_prepares_only_requested_export_and_uses_full_subset(monkeypatch) -> None:
    subset = _df(250)
    fake = _FakeStreamlit(clicked="Подготовить Excel")
    calls = {"xlsx": None, "csv": 0}
    monkeypatch.setattr(td, "build_tree_st_dataframe_df", lambda page: (pd.DataFrame({"x": range(len(page))}), {}))

    def _xlsx(data: pd.DataFrame) -> bytes:
        calls["xlsx"] = len(data)
        return b"xlsx"

    def _csv(data: pd.DataFrame) -> bytes:
        calls["csv"] += 1
        return b"csv"

    monkeypatch.setattr(td, "build_dissertations_xlsx_bytes", _xlsx)
    monkeypatch.setattr(td, "build_dissertations_csv_bytes", _csv)
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake)

    td.render_dissertations_widget(subset, key="review", page_size=100)

    assert calls == {"xlsx": 250, "csv": 0}
    assert fake.downloads[0]["data"] == b"xlsx"


def test_widget_invalidates_prepared_bytes_when_signature_changes(monkeypatch) -> None:
    fake = _FakeStreamlit()
    fake.session_state["prepared_export_review"] = {"signature": "old", "xlsx": b"old", "csv": b"old"}
    monkeypatch.setattr(td, "build_tree_st_dataframe_df", lambda page: (pd.DataFrame({"x": range(len(page))}), {}))
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake)

    td.render_dissertations_widget(_df(10), key="review", result_signature="new")

    assert fake.session_state["prepared_export_review"] == {"signature": "new", "xlsx": None, "csv": None}


def test_app_test_pagination_does_not_modify_widget_key_after_creation() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
from core.ui.table_display import render_dissertations_widget

render_dissertations_widget(
    pd.DataFrame({"Code": [str(i) for i in range(201)], "candidate_name": [f"Автор {i}" for i in range(201)]}),
    key="review",
    page_size=200,
)
"""
    )
    app.run(timeout=10)
    assert not app.exception


def test_widget_prepares_only_csv_when_requested(monkeypatch) -> None:
    subset = _df(250)
    fake = _FakeStreamlit(clicked="Подготовить CSV")
    calls = {"xlsx": 0, "csv": None}
    monkeypatch.setattr(td, "build_tree_st_dataframe_df", lambda page: (pd.DataFrame({"x": range(len(page))}), {}))
    monkeypatch.setattr(td, "build_dissertations_xlsx_bytes", lambda data: calls.__setitem__("xlsx", calls["xlsx"] + 1) or b"xlsx")

    def _csv(data: pd.DataFrame) -> bytes:
        calls["csv"] = len(data)
        return b"csv"

    monkeypatch.setattr(td, "build_dissertations_csv_bytes", _csv)
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake)

    td.render_dissertations_widget(subset, key="review", page_size=100)

    assert calls == {"xlsx": 0, "csv": 250}
    assert fake.downloads[0]["data"] == b"csv"


def test_widget_reuses_prepared_bytes_on_unrelated_rerun(monkeypatch) -> None:
    fake = _FakeStreamlit()
    fake.session_state["prepared_export_review"] = {"signature": "same", "xlsx": b"ready", "csv": None}
    monkeypatch.setattr(td, "build_tree_st_dataframe_df", lambda page: (pd.DataFrame({"x": range(len(page))}), {}))
    monkeypatch.setattr(td, "build_dissertations_xlsx_bytes", lambda data: (_ for _ in ()).throw(AssertionError("xlsx")))
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake)

    td.render_dissertations_widget(_df(10), key="review", result_signature="same")

    assert fake.downloads[0]["data"] == b"ready"


def test_result_signature_does_not_hash_complete_dataframe(monkeypatch) -> None:
    monkeypatch.setattr(
        td.pd.util,
        "hash_pandas_object",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full dataframe hash")),
    )
    signature = td.build_dissertation_result_signature(_df(1000), context_parts=(("db", 1.0, 1), "query"))
    assert signature
