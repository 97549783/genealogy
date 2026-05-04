"""Подключение к SQLite-базе проекта."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = "genealogy.db"


def _resolve_db_path() -> Path:
    """Возвращает путь к SQLite-базе из переменной окружения."""
    return Path(os.environ.get("SQLITE_DB_PATH", DB_PATH)).expanduser()


def get_sqlite_connection() -> sqlite3.Connection:
    """Создаёт подключение к SQLite-базе проекта."""
    db_path = _resolve_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite-база не найдена: {db_path.resolve()}")
    return sqlite3.connect(db_path)
