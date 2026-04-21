import pandas as pd

from core.db.scores import (
    get_all_feature_columns,
    get_numeric_code_feature_columns,
    load_scores_from_folder,
)


def test_load_scores_from_folder_normalizes_codes_and_numeric_values(tmp_path):
    (tmp_path / "scores_a.csv").write_text(
        "Code,1,topic_text\n"
        "  A1  ,1.5,2\n"
        ",5,6\n"
        "A2,abc,3\n",
        encoding="utf-8",
    )
    (tmp_path / "scores_b.csv").write_text(
        "Code,1,topic_text\n"
        "A1,9,9\n"
        "A3,4.5,xyz\n",
        encoding="utf-8",
    )

    result = load_scores_from_folder(str(tmp_path))

    assert result["Code"].tolist() == ["A1", "A2", "A3"]
    assert result.loc[result["Code"] == "A1", "1"].iloc[0] == 1.5
    assert result.loc[result["Code"] == "A2", "1"].iloc[0] == 0.0
    assert result.loc[result["Code"] == "A3", "topic_text"].iloc[0] == 0.0


def test_load_scores_from_folder_respects_specific_files(tmp_path):
    (tmp_path / "a.csv").write_text("Code,1\nX1,1\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("Code,1\nX2,2\n", encoding="utf-8")
    (tmp_path / "c.csv").write_text("Code,1\nX3,3\n", encoding="utf-8")

    result = load_scores_from_folder(
        str(tmp_path),
        specific_files=["b.csv", "c.csv"],
    )

    assert result["Code"].tolist() == ["X2", "X3"]


def test_feature_column_helpers_preserve_both_policies():
    scores_df = pd.DataFrame(
        {
            "Code": ["X1"],
            "1": [1.0],
            "1.1": [2.0],
            "topic_text": [3.0],
            "Year_num": [2020.0],
        }
    )

    assert get_all_feature_columns(scores_df) == ["1", "1.1", "topic_text", "Year_num"]
    assert get_numeric_code_feature_columns(scores_df) == ["1", "1.1"]
