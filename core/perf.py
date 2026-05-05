"""Общие инструменты диагностики производительности."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from collections.abc import Iterator

_LOG = logging.getLogger(__name__)
_ENV_FLAG = "GENEALOGY_PERF_LOG"


def _is_perf_enabled() -> bool:
    """Проверяет, включена ли диагностика производительности через переменную окружения."""
    return os.getenv(_ENV_FLAG, "").strip() == "1"


@contextmanager
def perf_timer(label: str, *, min_seconds: float = 0.0) -> Iterator[None]:
    """Измеряет время выполнения блока и пишет сообщение в лог при включённой диагностике."""
    if not _is_perf_enabled():
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        if elapsed >= min_seconds:
            _LOG.info("[perf] %s: %.3fs", label, elapsed)
