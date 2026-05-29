from __future__ import annotations

import importlib


def test_feedback_file_path_can_be_configured(monkeypatch, tmp_path):
    target = tmp_path / "feedback.csv"
    monkeypatch.setenv("FEEDBACK_FILE_PATH", str(target))

    import core.app.feedback as feedback

    feedback = importlib.reload(feedback)

    assert feedback.FEEDBACK_FILE == target


def test_append_and_load_feedback(monkeypatch, tmp_path):
    target = tmp_path / "feedback.csv"
    monkeypatch.setenv("FEEDBACK_FILE_PATH", str(target))

    import core.app.feedback as feedback

    feedback = importlib.reload(feedback)

    feedback.append_feedback(" Alice ", " alice@example.org ", "Line 1\r\nLine 2")

    df = feedback.load_feedback()

    assert list(df.columns) == feedback.FEEDBACK_COLUMNS
    assert len(df) == 1
    assert df.loc[0, "name"] == "Alice"
    assert df.loc[0, "email"] == "alice@example.org"
    assert df.loc[0, "message"] == "Line 1\nLine 2"
    assert target.exists()
