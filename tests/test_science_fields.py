import pandas as pd

from core.domain.science_fields import (
    filter_df_by_science_fields,
    normalize_science_field_text,
    science_field_matches,
)


def test_normalize_science_field_text():
    assert normalize_science_field_text(" ПЕДАГОГИЧЕСКИЕ   НАУКИ ") == "педагогические науки"
    assert normalize_science_field_text("Ёж") == "еж"


def test_science_field_matches_by_stem():
    assert science_field_matches("Педагогические науки", ["pedagogy"])
    assert science_field_matches("педагогика", ["pedagogy"])
    assert science_field_matches("Психологические науки", ["psychology"])
    assert science_field_matches("Философские науки", ["philosophy"])
    assert science_field_matches("Технические науки", ["technical"])
    assert science_field_matches("Физико-математические науки", ["phys_math"])
    assert science_field_matches("Физико-математические науки", ["phys_math"])
    assert not science_field_matches("Технические науки", ["pedagogy"])


def test_filter_df_by_science_fields():
    df = pd.DataFrame(
        {
            "Code": ["A", "B", "C"],
            "degree.science_field": [
                "Педагогические науки",
                "Технические науки",
                "Физико-математические науки",
            ],
        }
    )
    out = filter_df_by_science_fields(df, ["technical", "phys_math"])
    assert out["Code"].tolist() == ["B", "C"]


def test_filter_df_by_science_fields_empty_selection_returns_all():
    df = pd.DataFrame({"Code": ["A"]})
    assert filter_df_by_science_fields(df, []).equals(df)
