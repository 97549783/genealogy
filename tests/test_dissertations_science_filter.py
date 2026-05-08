import pandas as pd


def test_filter_dissertations_forwards_science_field_ids(monkeypatch):
    from tabs.dissertations import search

    captured = {}

    def fake_search(search_params, *, use_fuzzy=False, science_field_ids=None):
        captured["science_field_ids"] = science_field_ids
        return pd.DataFrame()

    monkeypatch.setattr(search, "search_dissertation_metadata", fake_search)

    search.filter_dissertations(
        None,
        {},
        science_field_ids=["technical", "phys_math"],
    )

    assert captured["science_field_ids"] == ["technical", "phys_math"]
