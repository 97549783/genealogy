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
    conn = sqlite3.connect(db)
    conn.execute('ALTER TABLE diss_metadata ADD COLUMN "institution_prepared" TEXT')
    conn.execute('UPDATE diss_metadata SET "institution_prepared" = ? WHERE "Code" = "1"', ("МГУ имени М.В. Ломоносова",))
    conn.execute('UPDATE diss_metadata SET "institution_prepared" = ? WHERE "Code" = "2"', ("Московский государственный университет",))
    conn.commit()
    conn.close()
    importlib.reload(dissertations)
    like_only = dissertations.fetch_dissertation_text_candidates(["institution_prepared"], "МГУ", use_like_prefilter=True)
    assert set(like_only["Code"]) == {"1"}
    all_candidates = dissertations.fetch_dissertation_text_candidates(["institution_prepared"], "МГУ", use_like_prefilter=False)
    assert set(all_candidates["Code"]) == {"1", "2"}
