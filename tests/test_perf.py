from __future__ import annotations

import logging

import pytest

from core import perf


def test_perf_timer_no_logs_when_disabled(monkeypatch, caplog):
    monkeypatch.delenv("GENEALOGY_PERF_LOG", raising=False)
    caplog.set_level(logging.INFO)
    with perf.perf_timer("x"):
        pass
    assert "[perf]" not in caplog.text


def test_perf_timer_logs_when_enabled(monkeypatch, caplog):
    monkeypatch.setenv("GENEALOGY_PERF_LOG", "1")
    caplog.set_level(logging.INFO)
    with perf.perf_timer("test.label"):
        pass
    assert "test.label" in caplog.text


def test_perf_timer_does_not_swallow_exceptions(monkeypatch):
    monkeypatch.setenv("GENEALOGY_PERF_LOG", "1")
    with pytest.raises(RuntimeError):
        with perf.perf_timer("boom"):
            raise RuntimeError("x")
