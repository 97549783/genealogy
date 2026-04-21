import pandas as pd

from core.people import get_unique_supervisors


def test_get_unique_supervisors_drops_empty_values_and_sorts():
    df = pd.DataFrame(
        {
            "supervisors_1.name": ["Иванов И.И.", " ", None, "nan", "Петров П.П."],
            "supervisors_2.name": ["Сидоров С.С.", "None", "Иванов И.И.", "  ", "Петров П.П."],
        }
    )

    result = get_unique_supervisors(df)

    assert result == ["Иванов И.И.", "Петров П.П.", "Сидоров С.С."]
