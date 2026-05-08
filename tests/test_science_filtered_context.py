import pandas as pd

from core.ui.science_filtering import build_science_filtered_lineage_context


def test_build_science_filtered_lineage_context_filters_and_rebuilds_supervisors():
    df = pd.DataFrame(
        [
            {
                "Code": "A",
                "candidate_name": "Автор A",
                "supervisors_1.name": "Тех Руководитель",
                "degree.science_field": "Технические науки",
            },
            {
                "Code": "B",
                "candidate_name": "Автор B",
                "supervisors_1.name": "Пед Руководитель",
                "degree.science_field": "Педагогические науки",
            },
        ]
    )

    context = build_science_filtered_lineage_context(
        df=df,
        selected_ids=["technical"],
        supervisor_columns=["supervisors_1.name"],
    )

    assert context.df["Code"].tolist() == ["A"]
    assert context.all_supervisor_names == ["Тех Руководитель"]
    assert context.science_field_ids == ["technical"]
    assert context.idx
