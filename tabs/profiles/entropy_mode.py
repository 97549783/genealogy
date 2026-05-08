"""
Модуль Streamlit-вкладки поиска по мере общности/специфичности.

Реализует поиск диссертаций на основе энтропии Шеннона с возможностью:
- Выбора одного или нескольких научных руководителей
- Выбора уровня (прямые диссертанты / все поколения)
- Выбора узлов классификатора для анализа
- Применения иерархического коэффициента Z
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Set

import pandas as pd
import streamlit as st
from core.db import get_all_feature_columns, load_dissertation_scores as load_dissertation_scores_core
from core.people import get_unique_supervisors as get_unique_supervisors_core
from core.ui.table_display import (
    make_abstract_download_url_numeric,
    make_abstract_read_url,
)

from .entropy import interpret_entropy, search_by_entropy

# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================

DEFAULT_MIN_THRESHOLD = 3.0
MAX_RESULTS_DISPLAY = 100


def _prepare_entropy_export_df(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Готовит таблицы для отображения и скачивания:
    - для UI: колонки ссылок «Автореферат» и «PDF-файл», без колонки кода;
    - для экспорта: русские названия колонок и ссылка «Автореферат» вместо кода.
    """
    base = results.copy()
    code_col = "Code" if "Code" in base.columns else None
    name_col = "candidate.name" if "candidate.name" in base.columns else None

    if code_col:
        base["Автореферат"] = base[code_col].apply(
            lambda code: make_abstract_read_url(str(code))
        )
        if name_col:
            base["PDF-файл"] = base.apply(
                lambda row: make_abstract_download_url_numeric(
                    str(row.get(code_col, "")),
                    str(row.get(name_col, "")),
                ),
                axis=1,
            )
        else:
            base["PDF-файл"] = ""
    else:
        base["Автореферат"] = ""
        base["PDF-файл"] = ""

    rename_map = {
        "entropy": "Энтропия",
        "features_count": "Количество тем",
        "candidate.name": "Автор",
        "title": "Название",
        "year": "Год",
        "degree.degree_level": "Степень",
        "institution_prepared": "Организация",
    }

    export_df = base.rename(columns=rename_map).drop(columns=["Code"], errors="ignore")

    ui_cols = [
        "Автореферат",
        "PDF-файл",
        "Энтропия",
        "Количество тем",
        "Интерпретация",
        "Автор",
        "Название",
        "Год",
        "Степень",
        "Организация",
    ]
    return base, export_df[[c for c in ui_cols if c in export_df.columns]]

# ==============================================================================
# ИНСТРУКЦИЯ
# ==============================================================================

INSTRUCTION_ENTROPY = """
## 📊 Поиск по мере общности/специфичности

Этот инструмент позволяет находить диссертации по степени **узости** или **широты** 
исследования на основе анализа тематических профилей.

---

### 🎯 Область анализа

#### Выбор научной школы
Выберите одного или нескольких научных руководителей для анализа их школ:
- Можно выбрать **несколько руководителей** для совместного анализа
- **Только прямые диссертанты** — анализ работ непосредственных учеников
- **Все поколения диссертантов** — анализ всего дерева научного руководства

#### Выбор узлов классификатора
Можно анализировать:
- **Весь классификатор** — все темы (медленнее, но полная картина)
- **Конкретные узлы** — выбранные разделы классификатора (быстрее, фокусировка на теме)

---

### 🔧 Параметры поиска

#### 1. Тип формулы энтропии

- **Классическая формула Шеннона**: H = -∑ p_i · log(p_i)
  - Все темы классификатора рассматриваются как равноправные
  - Подходит для общей оценки разнообразия тем

- **С иерархическим коэффициентом Z**: H = -∑ Z_i · p_i · log(p_i)
  - Учитывает структуру классификатора
  - Придает больший вес темам на глубоких уровнях иерархии
  - **Рекомендуется** для более точной оценки специфичности

#### 2. Отсечение малых значений

Темы с баллами ниже порога исключаются из анализа.
- **По умолчанию**: 3 балла
- **Рекомендация**: используйте 2-4 балла

---

### 📈 Интерпретация результатов

| Диапазон энтропии | Интерпретация |
|-------------------|---------------|
| < 1.0 | Очень узкая специализация |
| 1.0 – 2.5 | Узкая специализация |
| 2.5 – 4.0 | Умеренная широта |
| 4.0 – 5.5 | Широкий охват |
| > 5.5 | Очень широкий охват (междисциплинарность) |

---

### 💡 Примеры использования

**Сравнить специализацию работ разных школ:**
- Выбрать несколько руководителей
- "Все поколения диссертантов"
- Весь классификатор
- Посмотреть распределение энтропии

**Найти узкоспециализированные работы в конкретной области:**
- Выбрать руководителя(ей)
- Выбрать нужные узлы классификатора
- "С коэффициентом Z"
- "От узких к широким"
"""

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def show_instruction_dialog() -> None:
    """Показывает диалог с инструкцией."""
    @st.dialog("📖 Инструкция", width="large")
    def _show():
        st.markdown(INSTRUCTION_ENTROPY)

    _show()


def load_scores_from_db(profile_source_id: str = "pedagogy_5_8") -> pd.DataFrame:
    """Совместимая обёртка над загрузчиком профилей из SQLite."""
    return load_dissertation_scores_core(profile_source_id=profile_source_id)


def get_feature_columns(scores: pd.DataFrame) -> List[str]:
    """Совместимая обёртка над общим выбором признаковых колонок."""
    return get_all_feature_columns(scores)


def get_all_nodes_of_branch(
    node_code: str,
    all_codes: List[str]
) -> List[str]:
    """
    Возвращает все узлы, относящиеся к ветке (сам узел + все потомки).

    """
    result = []
    for code in all_codes:
        # Узел сам или его потомок (начинается с node_code.)
        if code == node_code or code.startswith(f"{node_code}."):
            result.append(code)
    return result


def get_unique_supervisors(df: pd.DataFrame, supervisor_columns: List[str]) -> List[str]:
    """Совместимая обёртка над общим извлечением научных руководителей."""
    return get_unique_supervisors_core(df=df, supervisor_columns=supervisor_columns)


# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ РЕНДЕРИНГА ВКЛАДКИ
# ==============================================================================

def render_entropy_specificity_tab(
    df: pd.DataFrame,
    idx: Dict[str, Set[int]],
    lineage_func,
    rows_for_func,
    classifier_labels: Optional[Dict[str, str]] = None,
    thematic_classifier: Optional[List[tuple]] = None,
    supervisor_columns: Optional[List[str]] = None,
    profile_source_id: str = "pedagogy_5_8",
    profile_source_label: str = "Педагогические науки — 5.8.x / 13.00.xx",
) -> None:
    """
    Отрисовывает вкладку поиска по мере общности/специфичности.

    """
    if classifier_labels is None:
        classifier_labels = {}

    if supervisor_columns is None:
        supervisor_columns = ["supervisors_1.name", "supervisors_2.name"]

    entropy_results_key = f"entropy_results_{profile_source_id}"
    entropy_params_key = f"entropy_params_{profile_source_id}"

    # --- Кнопка инструкции ---
    if st.button("📖 Инструкция", key="instruction_entropy"):
        show_instruction_dialog()

    st.subheader("📊 Поиск по мере общности/специфичности")
    st.caption(f"Активный профиль: {profile_source_label}")

    st.markdown("""
    Найдите диссертации по степени **узости** или **широты** исследования в рамках 
    выбранных научных школ. Низкая энтропия = узкая тема, высокая энтропия = широкий охват.
    """)

    # =========================================================================
    # ЗАГРУЗКА ДАННЫХ ПРОФИЛЕЙ
    # =========================================================================
