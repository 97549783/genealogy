from __future__ import annotations

from tabs.registry import DEFAULT_TAB_ID, TAB_ID_TO_LABEL, TAB_LABEL_TO_ID


def test_registry_includes_comparison_tabs_and_maps_are_consistent() -> None:
    assert "school_comparison" in TAB_ID_TO_LABEL
    assert "articles_comparison" in TAB_ID_TO_LABEL

    for tab_id, label in TAB_ID_TO_LABEL.items():
        assert TAB_LABEL_TO_ID[label] == tab_id

    assert DEFAULT_TAB_ID == "lineages"
