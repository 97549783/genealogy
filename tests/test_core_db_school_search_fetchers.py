import importlib
import sqlite3

from core.db import dissertations


def test_school_search_fetchers(tmp_path, monkeypatch):
    db = tmp_path / "g.db"
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE diss_metadata ("Code" TEXT, "year" TEXT, "city" TEXT, "candidate_name" TEXT, "opponents_1.name" TEXT)')
    conn.executemany('INSERT INTO diss_metadata VALUES (?,?,?,?,?)', [
        ("1", "2020", "Москва", "Иванов И.И.", "Петров П.П."),
        ("2", "2021", "москва", "Сидоров С.С.", "ПЕТРОВ П.П."),
        ("", "2021", "Казань", " ", None),
    ])
    conn.commit()
    conn.close()
    monkeypatch.setenv("SQLITE_DB_PATH", str(db))
    import core.db.connection as connection
    importlib.reload(connection)
    importlib.reload(dissertations)

    assert dissertations.fetch_dissertation_codes_by_year_range(2020, 2021) == {"1", "2"}
    assert dissertations.fetch_dissertation_codes_by_year(2021) == {"2"}
    cands = dissertations.fetch_dissertation_text_candidates(["city"], "МОСКВА")
    assert set(cands.columns) == {"Code", "column", "value"}
    assert set(cands["Code"]) == {"1", "2"}
    names = dissertations.fetch_candidate_name_options()
    assert names == ["Иванов И.И.", "Сидоров С.С."]
    try:
        dissertations.fetch_dissertation_codes_by_year_range(2022, 2021)
        assert False
    except ValueError:
        assert True
    try:
        dissertations.fetch_dissertation_text_candidates(["unknown_column"], "x")
        assert False
    except ValueError:
        assert True
    no_prefilter = dissertations.fetch_dissertation_text_candidates(["opponents_1.name"], "zzz", use_like_prefilter=False)
    assert set(no_prefilter["Code"]) == {"1", "2"}
