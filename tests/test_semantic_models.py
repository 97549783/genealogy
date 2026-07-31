"""Проверки контрактов выбора семантических разделов."""

import pytest

from core.semantic.models import build_section_selection
from tabs.dissertation_characteristics.labels import SEARCHABLE_SECTION_KEYS


def test_selection_uses_canonical_order() -> None:
    selection = build_section_selection(
        "selected", ["research_methods", "research_goal"],
        {"research_methods": 2, "research_goal": 1},
    )
    assert selection.section_keys == ("research_goal", "research_methods")
    assert selection.weights == (("research_goal", 1.0), ("research_methods", 2.0))


def test_all_selection_has_default_weights() -> None:
    selection = build_section_selection()
    assert selection.section_keys == tuple(SEARCHABLE_SECTION_KEYS)
    assert set(dict(selection.weights).values()) == {1.0}


@pytest.mark.parametrize("weight", [0, -1, float("nan"), float("inf")])
def test_invalid_weight_is_rejected(weight: float) -> None:
    with pytest.raises(ValueError, match="Веса"):
        build_section_selection("selected", ["research_goal"], {"research_goal": weight})
