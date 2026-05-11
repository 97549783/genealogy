# Источник данных приложения

Единственный рабочий источник данных сайта — файл SQLite `genealogy.db` в корне репозитория.

Runtime-код приложения получает данные через слой `core/db/`. Вкладки и аналитические модули должны работать с `pandas.DataFrame` и не должны напрямую читать исходные файлы данных.

## Путь к базе данных

По умолчанию используется файл:

```text
genealogy.db
```

Для локального запуска или деплоя путь можно переопределить переменной окружения:

```bash
SQLITE_DB_PATH=/путь/к/genealogy.db
```

Пример запуска:

```bash
SQLITE_DB_PATH=/путь/к/genealogy.db streamlit run streamlit_app.py
```

Если файл базы не найден, приложение должно показывать явную ошибку. Нельзя случайно создавать пустую SQLite-базу вместо отсутствующей рабочей базы.

## Обязательные таблицы

Минимальный набор таблиц, без которого runtime-аналитика не считается рабочей:

- `diss_metadata`;
- `diss_scores_5_8`;
- `diss_scores_2_3`;
- `articles_metadata`;
- `articles_scores_inf_edu`.

В текущей публичной базе дополнительно есть расширенные таблицы вкладки «Анализ статей (демо)»:

- `article_authors`;
- `article_keywords`.

Загрузчики `load_article_authors()` и `load_article_keywords()` допускают мягкое отсутствие этих двух таблиц и возвращают пустые датафреймы с ожидаемыми столбцами. Это нужно для совместимости со старыми копиями базы. В актуальной `genealogy.db` эти таблицы должны присутствовать, потому что они используются для расширенных метрик по авторам школы, аффилиациям, городам и ключевым словам.

### `diss_metadata`

Метаданные диссертаций.

Обязательные поля:

- `Code` — ключ диссертации;
- `candidate_name` — имя автора диссертации.

Остальные поля используются вкладками поиска, анализа научных школ и отображения карточек диссертаций, если присутствуют в таблице.

### `diss_scores_5_8` и `diss_scores_2_3`

Тематические профили диссертаций для педагогического и ИТ-профилей.

Обязательное поле в каждой таблице:

- `Code` — ключ диссертации, связывающий профиль с `diss_metadata`.

Остальные поля — числовые признаки соответствующего тематического классификатора. Служебные или метаданные поля не должны использоваться как тематические признаки.

## Выбор тематического профиля в UI

Во всех сценариях, где используются тематические признаки диссертаций, пользователь выбирает один источник профилей:

- `pedagogy_5_8` — `diss_scores_5_8`, классификатор 5.8.x / 13.00.xx;
- `it_2_3` — `diss_scores_2_3`, классификатор 2.3.x / 05.13.xx.

Смешивание этих профилей в одном тематическом расчёте запрещено: одинаковые коды узлов могут иметь разный смысл в разных классификаторах.

### `articles_metadata`

Метаданные статей.

Обязательные поля:

- `Article_id`;
- `Authors`;
- `Title`;
- `Journal`;
- `Volume`;
- `Issue`;
- `Year`.

Вкладка «Анализ статей (демо)» также использует дополнительные поля, если они есть в таблице:

- `ISSN`;
- `Abstract`;
- `Keywords`;
- `DOI`;
- `Pages`;
- `Funding`.

`Article_id` является ключом статьи и связывает `articles_metadata` с таблицами `articles_scores_inf_edu`, `article_authors` и `article_keywords`.

### `articles_scores_inf_edu`

Тематические профили статей журнала по информатике и образованию.

Обязательное поле:

- `Article_id` — ключ статьи, связывающий профиль с `articles_metadata`.

Остальные поля — числовые признаки тематического классификатора статей. Код приложения обрабатывает их динамически как все столбцы, кроме ключа `Article_id` и служебных полей.

### `article_authors`

Нормализованные сведения об авторах статей. Таблица отделяет автора статьи от агрегированной строки `Authors` в `articles_metadata` и позволяет вкладке «Анализ статей (демо)» считать найденных авторов школы, показывать аффилиации и города.

Ожидаемые поля:

- `id` — технический идентификатор строки;
- `Article_id` — ключ статьи;
- `ISSN` — ISSN журнала или выпуска;
- `Author_order` — порядок автора в статье;
- `Name` — имя автора;
- `Affiliation` — аффилиация автора;
- `Country` — страна;
- `City` — город;
- `Details` — дополнительные сведения об авторе.

### `article_keywords`

Нормализованные ключевые слова статей. Таблица используется для расчёта уникальных ключевых слов и частот по статьям выбранной научной школы.

Ожидаемые поля:

- `id` — технический идентификатор строки;
- `Article_id` — ключ статьи;
- `ISSN` — ISSN журнала или выпуска;
- `Keyword_order` — порядок ключевого слова в статье;
- `Keyword` — ключевое слово.

Если `article_keywords` отсутствует или пуста, вкладка может построить резервный набор ключевых слов из строкового поля `Keywords` таблицы `articles_metadata`, если это поле присутствует.

## Фильтрация по отраслям наук

Формальные сценарии анализа могут ограничивать состав диссертаций по `degree.science_field`.

Фильтр работает не по точному равенству, а по нормализованным фрагментам:

- `pedagogy` → `педагог`
- `psychology` → `психолог`
- `philosophy` → `философ`
- `technical` → `техник` / `технич`
- `phys_math` → `математ`

Если отрасли не выбраны, используются все диссертации.

## Фактическая структура `genealogy.db`

Этот раздел фиксирует снимок структуры рабочей SQLite-базы, чтобы сведения о таблицах и типах столбцов не терялись при изменениях кода.

В текущей базе есть семь таблиц:

- `article_authors` — нормализованные авторы статей;
- `article_keywords` — нормализованные ключевые слова статей;
- `articles_metadata` — метаданные статей;
- `articles_scores_inf_edu` — тематические профили статей;
- `diss_metadata` — метаданные диссертаций;
- `diss_scores_2_3` — тематические профили диссертаций для ИТ-классификатора `2.3.x / 05.13.xx`;
- `diss_scores_5_8` — тематические профили диссертаций для педагогического классификатора `5.8.x / 13.00.xx`.

Runtime-код поддерживает обе таблицы диссертационных тематических профилей: `diss_scores_5_8` и `diss_scores_2_3`. Выбор таблицы выполняется через registry источников профилей в `core/domain/profile_sources.py`. Канонический ИТ-классификатор хранится в `core/classifier/it_2_3_classifier.json`; Python-код загружает его и вычисляет признак selectable/disabled по наличию дочерних узлов.

### `article_authors`

```text
id            INTEGER
Article_id    TEXT
ISSN          TEXT
Author_order  INTEGER
Name          TEXT
Affiliation   TEXT
Country       TEXT
City          TEXT
Details       TEXT
```

### `article_keywords`

```text
id             INTEGER
Article_id     TEXT
ISSN           TEXT
Keyword_order  INTEGER
Keyword        TEXT
```

### `articles_metadata`

Базовые обязательные поля:

```text
Article_id  TEXT
Authors     TEXT
Title       TEXT
Year        INTEGER
Journal     TEXT
Volume      INTEGER
Issue       INTEGER
```

Дополнительные поля, которые используются вкладкой статей при наличии:

```text
ISSN      TEXT
Abstract  TEXT
Keywords  TEXT
DOI       TEXT
Pages     TEXT
Funding   TEXT
```

### `articles_scores_inf_edu`

Ключевой столбец:

```text
Article_id  TEXT
```

Остальные столбцы — целочисленные или числовые тематические признаки классификатора. Имена признаков являются кодами узлов классификатора, например:

```text
1.1.1.1          INTEGER
1.1.1.2.1        INTEGER
1.1.2.1.7        INTEGER
1.2.3.4          INTEGER
2.1.1.1          INTEGER
2.4.2.5          INTEGER
3.1.1.1          INTEGER
3.5.3.5          INTEGER
```

Полный список признаков этой таблицы нужно получать из самой базы через `PRAGMA table_info("articles_scores_inf_edu")`, потому что код приложения обрабатывает их динамически как все столбцы, кроме ключа `Article_id`.

### `diss_metadata`

```text
Code                    TEXT
defense_council         TEXT
leading_organization    TEXT
specialties_1.code      TEXT
specialties_1.name      TEXT
specialties_2.code      TEXT
specialties_2.name      TEXT
supervisors_1.name      TEXT
supervisors_1.degree    TEXT
supervisors_1.title     TEXT
supervisors_1.other     TEXT
supervisors_2.name      TEXT
supervisors_2.degree    TEXT
supervisors_2.title     TEXT
supervisors_2.other     TEXT
defense_location        TEXT
year                    TEXT
opponents_1.name        TEXT
opponents_1.degree      TEXT
opponents_1.title       TEXT
opponents_1.other       TEXT
opponents_2.name        TEXT
opponents_2.degree      TEXT
opponents_2.title       TEXT
opponents_2.other       TEXT
opponents_3.name        TEXT
opponents_3.degree      TEXT
opponents_3.title       TEXT
opponents_3.other       TEXT
candidate_name          TEXT
degree.degree_level     TEXT
degree.science_field    TEXT
institution_prepared    TEXT
title                   TEXT
city                    TEXT
supervisors             TEXT
opponents               TEXT
specialties             TEXT
```

### `diss_scores_2_3`

Ключевой столбец:

```text
Code  TEXT
```

Остальные столбцы — целочисленные тематические признаки классификатора (`INTEGER`). Имена признаков являются кодами узлов классификатора с префиксами `1.*`, `2.*`, `3.*`. Таблица хранит тематические профили диссертаций для группы специальностей по информационным технологиям: новая номенклатура ВАК `2.3.x`, старая номенклатура `05.13.xx`. Например:

```text
1.1.1.1  INTEGER
1.2.4.3  INTEGER
1.3.6.3  INTEGER
2.1.1.1  INTEGER
2.4.4.4  INTEGER
2.6.4.4  INTEGER
3.1.1.1  INTEGER
3.3.6.4  INTEGER
```

Полный список признаков этой таблицы нужно получать из самой базы через `PRAGMA table_info("diss_scores_2_3")`.

### `diss_scores_5_8`

Ключевой столбец:

```text
Code  TEXT
```

Остальные столбцы — целочисленные тематические признаки педагогического классификатора (`INTEGER`). Имена признаков являются кодами узлов классификатора. Эта таблица включает как промежуточные узлы, так и более глубокие дочерние признаки, например:

```text
1.1                  INTEGER
1.1.1                INTEGER
1.1.1.2.1            INTEGER
1.1.2.2.1.1.3.4      INTEGER
1.2.2.4              INTEGER
2.1                  INTEGER
2.2.3.4              INTEGER
3.1                  INTEGER
3.3.6.6              INTEGER
```

Полный список признаков этой таблицы нужно получать из самой базы через `PRAGMA table_info("diss_scores_5_8")`. Runtime-код уже делает это динамически при построении списка тематических признаков.

## Проверка структуры базы

Пример проверки через Python:

```python
import sqlite3

conn = sqlite3.connect("genealogy.db")
tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
print(tables)
conn.close()
```

Минимальная проверка обязательных таблиц:

```python
import sqlite3

required = {
    "diss_metadata",
    "diss_scores_5_8",
    "diss_scores_2_3",
    "articles_metadata",
    "articles_scores_inf_edu",
}

conn = sqlite3.connect("genealogy.db")
actual = {
    row[0]
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
}
conn.close()

missing = required - actual
if missing:
    raise RuntimeError(f"Не найдены обязательные таблицы: {sorted(missing)}")
```

Проверка актуальной публичной базы с расширенными таблицами вкладки статей:

```python
import sqlite3

expected_current = {
    "diss_metadata",
    "diss_scores_5_8",
    "diss_scores_2_3",
    "articles_metadata",
    "articles_scores_inf_edu",
    "article_authors",
    "article_keywords",
}

conn = sqlite3.connect("genealogy.db")
actual = {
    row[0]
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
}
conn.close()

missing = expected_current - actual
if missing:
    raise RuntimeError(f"В актуальной базе не найдены таблицы: {sorted(missing)}")
```

Проверка фактической схемы всех таблиц:

```python
import sqlite3

conn = sqlite3.connect("genealogy.db")
tables = [
    row[0]
    for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
]

for table in tables:
    print(f"\n[{table}]")
    for _, name, type_, *_ in conn.execute(f'PRAGMA table_info("{table}")'):
        print(f"  {name}  {type_}")

conn.close()
```

## CSV и экспорт

Ранее в репозитории использовались CSV-папки `db_lineages/`, `basic_scores/`, `articles_scores/`. Они удалены из runtime-структуры проекта и больше не являются источником данных приложения.

Пользовательский экспорт результатов в CSV или XLSX остаётся штатной функцией интерфейса. Экспорт — это формат выгрузки результатов, а не источник данных приложения.

## Правило для новых вкладок и аналитики

Новый код должен получать данные через функции из `core/db/` и не должен напрямую обращаться к файлам исходных данных. Если нужна новая таблица или новый набор тематических профилей, сначала следует добавить загрузчик в `core/db/`, а затем использовать его во вкладке.
