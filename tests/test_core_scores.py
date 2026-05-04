import pandas as pd

from core.db.scores import get_all_feature_columns, get_numeric_code_feature_columns


def test_feature_column_helpers_exclude_metadata_columns():
    scores_df = pd.DataFrame(
        {
            "Code": ["X1"],
            "title": ["Тема"],
            "year": ["2024"],
            "1": [1.0],
            "1.1": [2.0],
            "topic_text": [3.0],
            "Year_num": [2020.0],
        }
    )

    assert get_all_feature_columns(scores_df) == ["1", "1.1", "topic_text", "Year_num"]
    assert get_numeric_code_feature_columns(scores_df) == ["1", "1.1"]
