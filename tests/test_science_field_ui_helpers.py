from core.ui.filters import science_field_filter_caption, science_field_state_suffix


def test_science_field_state_suffix():
    assert science_field_state_suffix([]) == "all"
    assert science_field_state_suffix(["technical", "pedagogy"]) == "pedagogy_technical"


def test_science_field_filter_caption():
    assert science_field_filter_caption([]) == "Фильтр отраслей наук не применяется."
    assert "Технические науки" in science_field_filter_caption(["technical"])


def test_render_science_field_filter_uses_selected_mode_for_defaults():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string(
        """
import streamlit as st
from core.ui.filters import render_science_field_filter

st.session_state["selected"] = render_science_field_filter(
    key_prefix="test_sf",
    default_selected_ids=["technical"],
)
"""
    )

    app.run()
    assert app.session_state["selected"] == ["technical"]
