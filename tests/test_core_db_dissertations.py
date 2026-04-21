from __future__ import annotations

import pandas as pd

from core.db.dissertations import AUTHOR_COLUMN, SUPERVISOR_COLUMNS, load_data


def test_load_data_reads_csv_and_preserves_expected_columns(monkeypatch, tmp_path):
    (tmp_path / "part_1.csv").write_text(
        "candidate_name,supervisors_1.name,Code\n"
        "Автор 1,Руководитель 1,100\n",
        encoding="utf-8",
    )
    (tmp_path / "part_2.csv").write_text(
        "candidate_name,supervisors_2.name,Code\n"
        "Автор 2,Руководитель 2,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("core.db.dissertations.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("core.db.dissertations.CSV_GLOB", "*.csv")
    load_data.clear()

    result = load_data()

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    assert AUTHOR_COLUMN == "candidate_name"
    assert SUPERVISOR_COLUMNS == ["supervisors_1.name", "supervisors_2.name"]
    assert set(result["Code"].astype(str).tolist()) == {"100", "200"}

    load_data.clear()
