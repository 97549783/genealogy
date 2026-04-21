from pathlib import Path

import pandas as pd

from core.db.scores import (
    get_all_feature_columns,
    get_numeric_code_feature_columns,
    load_scores_from_folder,
)


def test_load_scores_from_folder_normalizes_codes_and_numeric_values(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text(
        "Code,1,topic_text\n"
        "  A1  ,1.5,5\n"
        ",2,bad\n"
        "A2,foo,7\n",
        encoding="utf-8",
    )
    (tmp_path / "b.csv").write_text(
        "Code,1,topic_text\n"
        "A1,9,9\n"
        "A3,3,bar\n",
        encoding="utf-8",
    )

    result = load_scores_from_folder(str(tmp_path))

    assert result["Code"].tolist() == ["A1", "A2", "A3"]
    assert result.loc[result["Code"] == "A1", "1"].iloc[0] == 1.5
    assert result.loc[result["Code"] == "A2", "1"].iloc[0] == 0.0
    assert result.loc[result["Code"] == "A3", "topic_text"].iloc[0] == 0.0


def test_load_scores_from_folder_respects_specific_files(tmp_path: Path) -> None:
    (tmp_path / "first.csv").write_text("Code,1\nX,1\n", encoding="utf-8")
    (tmp_path / "second.csv").write_text("Code,1\nY,2\n", encoding="utf-8")
    (tmp_path / "third.csv").write_text("Code,1\nZ,3\n", encoding="utf-8")

    result = load_scores_from_folder(
        str(tmp_path),
        specific_files=["second.csv", "third.csv"],
    )

    assert set(result["Code"].tolist()) == {"Y", "Z"}


def test_feature_column_helpers_preserve_both_policies() -> None:
    frame = pd.DataFrame(
        columns=["Code", "1", "1.1", "topic_text", "Year_num"]
    )

    assert get_all_feature_columns(frame) == ["1", "1.1", "topic_text", "Year_num"]
    assert get_numeric_code_feature_columns(frame) == ["1", "1.1"]
