"""
utils/table_display.py — утилиты для отображения таблиц диссертаций в UI.

Модуль предоставляет переиспользуемые функции и константы, которые можно
применять на любых вкладках, где нужно показать список диссертаций
(деревья, поиск, анализ школ и т.д.).

Публичный API:
    COLUMN_ALIASES          — dict: исходное имя колонки → алиас без точек
                              (нужен при переходе на SQLite, где точки в именах
                              колонок недопустимы)
    COLUMN_LABELS           — dict: исходное/алиасное имя → русское название
    TREE_TABLE_COLUMNS      — list: упорядоченный список исходных колонок
                              для таблицы на вкладке «Построение деревьев»
    make_abstract_link(code, name) -> str
        Возвращает URL автореферата (или пустую строку) по коду диссертации.
    build_tree_display_df(subset) -> pd.DataFrame
        Формирует DataFrame для отображения в st.dataframe():
        добавляет колонку «Автореферат», применяет порядок и русские названия.
"""

from __future__ import annotations

import re
from urllib.parse import quote
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Алиасы колонок: точки → нижние подчёркивания
# Нужны для совместимости с SQLite, где точки в именах колонок запрещены.
# При переходе на SQLite достаточно переименовать колонки один раз при загрузке
# и везде использовать алиасы.
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    # степень и отрасль
    "degree.degree_level":  "degree_degree_level",
    "degree.science_field": "degree_science_field",
    # специальности
    "specialties_1.code":   "specialties_1_code",
    "specialties_1.name":   "specialties_1_name",
    "specialties_2.code":   "specialties_2_code",
    "specialties_2.name":   "specialties_2_name",
    # научные руководители
    "supervisors_1.name":   "supervisors_1_name",
    "supervisors_1.degree": "supervisors_1_degree",
    "supervisors_1.title":  "supervisors_1_rank",   # title → rank
    "supervisors_2.name":   "supervisors_2_name",
    "supervisors_2.degree": "supervisors_2_degree",
    "supervisors_2.title":  "supervisors_2_rank",   # title → rank
    # оппоненты
    "opponents_1.name":     "opponents_1_name",
    "opponents_1.degree":   "opponents_1_degree",
    "opponents_1.title":    "opponents_1_rank",
    "opponents_2.name":     "opponents_2_name",
    "opponents_2.degree":   "opponents_2_degree",
    "opponents_2.title":    "opponents_2_rank",
    "opponents_3.name":     "opponents_3_name",
    "opponents_3.degree":   "opponents_3_degree",
    "opponents_3.title":    "opponents_3_rank",
}

# Обратный словарь: алиас → исходное имя (удобно для поиска колонки по любому варианту)
_ALIAS_TO_ORIGINAL: dict[str, str] = {v: k for k, v in COLUMN_ALIASES.items()}


def _resolve(col: str) -> str:
    """Возвращает исходное имя колонки, принимая как исходное, так и алиасное."""
    return _ALIAS_TO_ORIGINAL.get(col, col)


# ---------------------------------------------------------------------------
# Русские названия колонок
# Ключи — исходные имена с точками (canonical form).
# Функции display принимают любой из вариантов через _resolve.
# ---------------------------------------------------------------------------

COLUMN_LABELS: dict[str, str] = {
    # вычисляемая колонка
    "abstract":                "Автореферат",
    # основные поля
    "candidate_name":          "Автор диссертации",
    "title":                   "Название диссертации",
    "year":                    "Год защиты",
    "degree.degree_level":     "Учёная степень",
    "degree.science_field":    "Отрасль науки",
    "specialties_1.code":      "Шифр специальности",
    "specialties_1.name":      "Специальность",
    "specialties_2.code":      "Шифр специальности 2",
    "specialties_2.name":      "Специальность 2",
    # руководители
    "supervisors_1.name":      "Научный руководитель",
    "supervisors_1.degree":    "Степень руководителя",
    "supervisors_1.title":     "Звание руководителя",
    "supervisors_2.name":      "Науч. руководитель 2",
    "supervisors_2.degree":    "Степень руководителя 2",
    "supervisors_2.title":     "Звание руководителя 2",
    # место защиты / организации
    "institution_prepared":    "Организация выполнения",
    "defense_location":        "Место защиты",
    "city":                    "Город защиты",
    "defense_council":         "Диссертационный совет",
    "leading_organization":    "Ведущая организация",
    # оппоненты
    "opponents_1.name":        "Оппонент 1",
    "opponents_1.degree":      "Степень оппонента 1",
    "opponents_1.title":       "Звание оппонента 1",
    "opponents_2.name":        "Оппонент 2",
    "opponents_2.degree":      "Степень оппонента 2",
    "opponents_2.title":       "Звание оппонента 2",
    "opponents_3.name":        "Оппонент 3",
    "opponents_3.degree":      "Степень оппонента 3",
    "opponents_3.title":       "Звание оппонента 3",
}

# Добавляем алиасные варианты в COLUMN_LABELS, чтобы поиск работал по обоим именам
for _orig, _alias in COLUMN_ALIASES.items():
    if _orig in COLUMN_LABELS:
        COLUMN_LABELS[_alias] = COLUMN_LABELS[_orig]


# ---------------------------------------------------------------------------
# Порядок колонок для таблицы «Построение деревьев»
# Используются исходные имена (с точками); build_tree_display_df найдёт
# фактически присутствующие в DataFrame.
# ---------------------------------------------------------------------------

TREE_TABLE_COLUMNS: list[str] = [
    # вычисляемая — добавляется в build_tree_display_df
    "abstract",
    # автор и название
    "candidate_name",
    "title",
    "year",
    "degree.degree_level",
    "degree.science_field",
    # специальности
    "specialties_1.code",
    "specialties_1.name",
    "specialties_2.code",
    "specialties_2.name",
    # руководители
    "supervisors_1.name",
    "supervisors_1.degree",
    "supervisors_1.title",
    "supervisors_2.name",
    "supervisors_2.degree",
    "supervisors_2.title",
    # организации и место
    "institution_prepared",
    "defense_location",
    "city",
    "defense_council",
    "leading_organization",
    # оппоненты
    "opponents_1.name",
    "opponents_1.degree",
    "opponents_1.title",
    "opponents_2.name",
    "opponents_2.degree",
    "opponents_2.title",
    "opponents_3.name",
    "opponents_3.degree",
    "opponents_3.title",
]


# ---------------------------------------------------------------------------
# Логика формирования ссылки на автореферат
# ---------------------------------------------------------------------------

# Шаблоны URL
_URL_DOWNLOAD = (
    "https://rusneb.ru/local/tools/exalead/getFiles.php"
    "?book_id={code}&name={encoded_name}&doc_type=pdf"
)
_URL_READ = "https://viewer.rusneb.ru/ru/{code}?page=1"

# Паттерн «только цифры и нижние подчёркивания»
_RE_NUMERIC = re.compile(r'^[0-9_]+$')


def make_abstract_link(code: str, name: str) -> str:
    """
    Возвращает URL автореферата диссертации в зависимости от формата кода.

    Правила:
    - Если code состоит только из цифр и нижних подчёркиваний
      (например, «000199_000009_003279301») — ссылка на скачивание PDF
      с именем «Автореферат. <ФИО автора>.pdf».
      Пробелы в ФИО кодируются через urllib.parse.quote, чтобы URL
      оставался рабочим и браузер корректно подставлял имя файла.
    - Если code содержит подстроку «NLR»
      (например, «000200_000018_RU_NLR_bibl_574554») — ссылка для
      онлайн-просмотра через viewer.rusneb.ru.
    - В остальных случаях (code пустой, неизвестный формат и т.д.)
      возвращается пустая строка.

    Args:
        code: Код диссертации из колонки «Code» датафрейма.
        name: ФИО автора (диссертанта) — используется как имя файла PDF.

    Returns:
        Строка-URL или пустая строка «».

    Examples:
        >>> make_abstract_link("000199_000009_003279301", "Иванов Иван Иванович")
        'https://rusneb.ru/local/tools/exalead/getFiles.php?book_id=000199_000009_003279301&name=%D0%90%D0%B2%D1%82%D0%BE%D1%80%D0%B5%D1%84%D0%B5%D1%80%D0%B0%D1%82.%20%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2%20%D0%98%D0%B2%D0%B0%D0%BD%20%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2%D0%B8%D1%87&doc_type=pdf'
        >>> make_abstract_link("000200_000018_RU_NLR_bibl_574554", "Петров Пётр")
        'https://viewer.rusneb.ru/ru/000200_000018_RU_NLR_bibl_574554?page=1'
        >>> make_abstract_link("", "Кто-то")
        ''
    """
    code = str(code).strip()
    if not code:
        return ""

    if _RE_NUMERIC.match(code):
        # PDF: имя файла «Автореферат. <ФИО>.pdf»
        # quote кодирует пробелы и кириллицу, оставляя URL рабочим
        file_name = f"Автореферат. {str(name).strip()}"
        encoded_name = quote(file_name, safe="")
        return _URL_DOWNLOAD.format(code=code, encoded_name=encoded_name)

    if "NLR" in code:
        return _URL_READ.format(code=code)

    return ""


# ---------------------------------------------------------------------------
# Формирование отображаемого DataFrame для таблицы деревьев
# ---------------------------------------------------------------------------

def build_tree_display_df(subset: pd.DataFrame) -> pd.DataFrame:
    """
    Формирует DataFrame для отображения в st.dataframe() на вкладке
    «Построение деревьев».

    Что делает:
    1. Вычисляет колонку «abstract» (URL автореферата) через make_abstract_link.
    2. Отбирает и упорядочивает колонки согласно TREE_TABLE_COLUMNS
       (пропускает отсутствующие в subset).
    3. Переименовывает колонки в русские названия из COLUMN_LABELS.
       Пустые строки в колонке «abstract» остаются пустыми — Streamlit
       не покажет ссылку для записей без автореферата.

    Args:
        subset: DataFrame с исходными колонками (из функции lineage в graph.py).

    Returns:
        Новый DataFrame, готовый для передачи в st.dataframe().
        Индекс сброшен (0..N-1).

    Note:
        Для колонки «Автореферат» используй st.column_config.LinkColumn
        при вызове st.dataframe(), чтобы ссылки стали кликабельными:

            st.dataframe(
                display_df,
                column_config={
                    "Автореферат": st.column_config.LinkColumn(
                        label="Автореферат",
                        display_text="Скачать|Читать",  # regex для отображения
                    )
                },
                use_container_width=True,
            )
    """
    if subset.empty:
        # Возвращаем пустой DataFrame с правильными русскими заголовками
        final_cols = [
            COLUMN_LABELS.get(c, c)
            for c in TREE_TABLE_COLUMNS
            if c in COLUMN_LABELS
        ]
        return pd.DataFrame(columns=final_cols)

    df = subset.copy().reset_index(drop=True)

    # Шаг 1: вычисляем колонку «abstract»
    code_col = "Code" if "Code" in df.columns else None
    name_col = "candidate_name" if "candidate_name" in df.columns else None

    if code_col and name_col:
        df["abstract"] = df.apply(
            lambda row: make_abstract_link(
                row.get(code_col, ""),
                row.get(name_col, ""),
            ),
            axis=1,
        )
    else:
        df["abstract"] = ""

    # Шаг 2: определяем доступные колонки в нужном порядке
    # Колонка «abstract» уже в df; остальные берём по исходному имени.
    ordered_cols: list[str] = []
    for col in TREE_TABLE_COLUMNS:
        if col == "abstract":
            if "abstract" in df.columns:
                ordered_cols.append("abstract")
        elif col in df.columns:
            ordered_cols.append(col)
        # Если колонки нет в subset — просто пропускаем

    df = df[ordered_cols]

    # Шаг 3: переименовываем в русские названия
    rename_map = {col: COLUMN_LABELS.get(col, col) for col in ordered_cols}
    df = df.rename(columns=rename_map)

    return df
