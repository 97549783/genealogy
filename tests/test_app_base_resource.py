from __future__ import annotations

import pandas as pd
import pytest

from core.app import bootstrap


def _df() -> pd.DataFrame:
    return pd.DataFrame([
        {"Code": "1", "candidate_name": "Автор", "supervisors_1.name": "Руководитель", "supervisors_2.name": ""},
    ])


@pytest.fixture(autouse=True)
def clear_base_resource_cache():
    bootstrap._load_base_app_data.clear()
    yield
    bootstrap._load_base_app_data.clear()


def test_base_app_data_reuses_metadata_and_index_for_same_signature(monkeypatch):
    calls = {"read": 0, "index": 0}
    df = _df()
    idx = {"Руководитель": {0}}

    def _read():
        calls["read"] += 1
        return df

    def _build(data, columns):
        calls["index"] += 1
        return idx

    monkeypatch.setattr(bootstrap, "read_dissertation_metadata", _read)
    monkeypatch.setattr(bootstrap, "build_index", _build)

    sig = ("db.sqlite", 1.0, 100)
    first = bootstrap._load_base_app_data(sig)
    second = bootstrap._load_base_app_data(sig)

    assert calls == {"read": 1, "index": 1}
    assert first.df is second.df is df
    assert first.idx is second.idx is idx


def test_base_app_data_rebuilds_for_changed_signature(monkeypatch):
    calls = {"read": 0, "index": 0}

    def _read():
        calls["read"] += 1
        return _df()

    def _build(data, columns):
        calls["index"] += 1
        return {"Руководитель": {0}}

    monkeypatch.setattr(bootstrap, "read_dissertation_metadata", _read)
    monkeypatch.setattr(bootstrap, "build_index", _build)

    first = bootstrap._load_base_app_data(("db.sqlite", 1.0, 100))
    second = bootstrap._load_base_app_data(("db.sqlite", 2.0, 100))

    assert calls == {"read": 2, "index": 2}
    assert first.df is not second.df
    assert first.idx is not second.idx


def test_base_app_data_missing_required_columns_raises_descriptive_error(monkeypatch):
    monkeypatch.setattr(
        bootstrap,
        "read_dissertation_metadata",
        lambda: pd.DataFrame([{"Code": "1", "candidate_name": "Автор"}]),
    )

    with pytest.raises(KeyError, match="Отсутствуют нужные колонки"):
        bootstrap._load_base_app_data(("db.sqlite", 1.0, 100))
