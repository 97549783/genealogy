# Источник данных приложения

Единственный рабочий источник данных сайта — файл SQLite `genealogy.db` в корне репозитория.

## Переопределение пути

Можно задать переменную окружения:

```bash
SQLITE_DB_PATH=/путь/к/genealogy.db
```

По умолчанию используется `genealogy.db`.

## Обязательные таблицы

- `diss_metadata`
- `diss_scores_5_8`
- `articles_metadata`
- `articles_scores_inf_edu`

## Проверка структуры базы

Пример проверки через Python:

```python
import sqlite3
conn = sqlite3.connect('genealogy.db')
print(conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
conn.close()
```

## Важно

CSV-папки `db_lineages/`, `basic_scores/`, `articles_scores/` больше не используются runtime-кодом сайта.
