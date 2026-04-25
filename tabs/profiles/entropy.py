"""
Модуль для расчета энтропии Шеннона тематических профилей диссертаций.

Реализует классическую энтропию Шеннона и модифицированную версию
с учетом иерархического коэффициента Z.

Версия с улучшенной обработкой типов и диагностикой.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import math


# ==============================================================================
# РАСЧЕТ ЭНТРОПИИ ШЕННОНА
# ==============================================================================

def calculate_entropy_shannon(
    profile: pd.Series,
    min_threshold: float = 0.0
) -> float:
    """
    Рассчитывает классическую энтропию Шеннона для тематического профиля.

    Формула: H = -∑ p_i · log₂(p_i)
    где p_i = балл_i / сумма_баллов (нормализованное значение)

    Параметры:
        profile: Series с баллами по темам (индекс = коды тем, значения = баллы)
        min_threshold: Минимальный порог для учета темы

    Возвращает:
        Значение энтропии (float)
    """
    # Фильтруем по порогу
    filtered = profile[profile >= min_threshold]

    if filtered.empty or filtered.sum() == 0:
        return 0.0

    # Нормализуем (получаем вероятности)
    probabilities = filtered / filtered.sum()

    # Рассчитываем энтропию напрямую через Python math (избегаем numpy)
    entropy = 0.0
    for prob in probabilities:
        if prob > 0:
            entropy -= float(prob) * math.log2(float(prob))

    return float(entropy)


def calculate_entropy_hierarchical(
    profile: pd.Series,
    classifier_hierarchy: Dict[str, List[str]],
    min_threshold: float = 0.0
) -> float:
    """
    Рассчитывает модифицированную энтропию с иерархическим коэффициентом Z.

    Формула: H = -∑ Z_i · p_i · log₂(p_i)
    где Z_i учитывает положение темы в иерархии классификатора

    Параметры:
        profile: Series с баллами по темам
        classifier_hierarchy: Словарь {код: список родительских кодов}
        min_threshold: Минимальный порог для учета темы

    Возвращает:
        Значение энтропии (float)
    """
    # Фильтруем по порогу
    filtered = profile[profile >= min_threshold]

    if filtered.empty or filtered.sum() == 0:
        return 0.0

    # Нормализуем
    probabilities = filtered / filtered.sum()

    codes = probabilities.index.tolist()

    # Рассчитываем энтропию напрямую через Python math
    entropy = 0.0
    for code, prob in zip(codes, probabilities):
        if prob > 0:
            z = calculate_z_coefficient(code, classifier_hierarchy)
            entropy -= z * float(prob) * math.log2(float(prob))

    return float(entropy)


def calculate_z_coefficient(
    code: str,
    classifier_hierarchy: Dict[str, List[str]]
) -> float:
    """
    Рассчитывает иерархический коэффициент Z для кода классификатора.

    Z учитывает глубину кода в иерархии:
    - Более глубокие (специфичные) коды получают меньший коэффициент
    - Это увеличивает их вклад в общую энтропию

    Формула: Z_i = ∏ (1 / log₂(k_d))
    где k_d = количество дочерних узлов у предка d

    Параметры:
        code: Код темы в классификаторе
        classifier_hierarchy: Словарь {код: список родительских кодов}

    Возвращает:
        Коэффициент Z (float)
    """
    if code not in classifier_hierarchy:
        return 1.0

    parents = classifier_hierarchy.get(code, [])

    if not parents:
        return 1.0

    z = 1.0
    for parent in parents:
        # Количество дочерних узлов родителя
        siblings_count = count_children(parent, classifier_hierarchy)

        if siblings_count > 1:
            z *= 1.0 / math.log2(float(siblings_count))

    return float(z)


def count_children(parent_code: str, classifier_hierarchy: Dict[str, List[str]]) -> int:
    """
    Подсчитывает количество непосредственных дочерних узлов.

    Параметры:
        parent_code: Код родительского узла
        classifier_hierarchy: Словарь иерархии

    Возвращает:
        Количество дочерних узлов
    """
    count = 0
    for code, parents in classifier_hierarchy.items():
        if parents and parents[-1] == parent_code:
            count += 1

    return max(count, 2)  # Минимум 2 для избежания деления на 0


# ==============================================================================
# ПОСТРОЕНИЕ ИЕРАРХИИ ИЗ КОДОВ
# ==============================================================================

def build_hierarchy_from_codes(codes: List[str]) -> Dict[str, List[str]]:
    """
    Строит иерархию классификатора из списка кодов.

    Для каждого кода определяет список его предков на основе структуры кода.
    Например, для "1.1.2.3" предками будут ["1", "1.1", "1.1.2"]

    Параметры:
        codes: Список кодов классификатора

    Возвращает:
        Словарь {код: [список предков]}
    """
    hierarchy = {}

    for code in codes:
        parents = []
        parts = code.split(".")

        # Строим список предков
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            parents.append(parent)

        hierarchy[code] = parents

    return hierarchy


def get_code_depth(code: str) -> int:
    """
    Возвращает глубину кода в иерархии (количество уровней).

    Параметры:
        code: Код классификатора

    Возвращает:
        Глубина (количество точек + 1)
    """
    return code.count(".") + 1 if code else 0


# ==============================================================================
# ИНТЕРПРЕТАЦИЯ ЭНТРОПИИ
# ==============================================================================

def interpret_entropy(entropy: float, hierarchical: bool = False) -> str:
    """
    Возвращает текстовую интерпретацию значения энтропии.

    Параметры:
        entropy: Значение энтропии
        hierarchical: Была ли использована иерархическая формула

    Возвращает:
        Текстовое описание
    """
    if entropy < 1.0:
        return "🔹 Очень узкая специализация"
    elif entropy < 2.5:
        return "🔸 Узкая специализация"
    elif entropy < 4.0:
        return "🟡 Умеренная широта"
    elif entropy < 5.5:
        return "🟠 Широкий охват"
    else:
        return "🔴 Очень широкий охват"


# ==============================================================================
# ПОИСК ПО ЭНТРОПИИ
# ==============================================================================

def search_by_entropy(
    scores_df: pd.DataFrame,
    feature_columns: List[str],
    use_hierarchical: bool = False,
    min_threshold: float = 0.0,
    ascending: bool = True
) -> pd.DataFrame:
    """
    Выполняет поиск диссертаций по энтропии их тематических профилей.

    Параметры:
        scores_df: DataFrame с профилями (Code + колонки с баллами)
        feature_columns: Список колонок-признаков для анализа
        use_hierarchical: Использовать ли иерархическую формулу с Z
        min_threshold: Минимальный порог для учета темы
        ascending: Сортировка по возрастанию (True) или убыванию (False)

    Возвращает:
        DataFrame с результатами (Code, entropy, features_count)
    """
    results = []

    # Строим иерархию если нужна
    hierarchy = None
    if use_hierarchical:
        hierarchy = build_hierarchy_from_codes(feature_columns)

    for idx, row in scores_df.iterrows():
        code = str(row["Code"])

        # Извлекаем профиль (только нужные колонки)
        # Создаем Series с числовыми значениями
        profile_dict = {}
        for col in feature_columns:
            try:
                val = row[col]
                if pd.isna(val):
                    profile_dict[col] = 0.0
                else:
                    profile_dict[col] = float(val)
            except (ValueError, TypeError):
                profile_dict[col] = 0.0

        profile = pd.Series(profile_dict)

        # Рассчитываем энтропию
        try:
            if use_hierarchical and hierarchy:
                entropy = calculate_entropy_hierarchical(
                    profile,
                    hierarchy,
                    min_threshold
                )
            else:
                entropy = calculate_entropy_shannon(
                    profile,
                    min_threshold
                )
        except Exception as e:
            # Если произошла ошибка, записываем диагностику и пропускаем
            print(f"⚠️ Ошибка при расчете энтропии для {code}: {type(e).__name__}: {e}")
            entropy = 0.0

        # Подсчитываем количество значимых тем
        try:
            features_count = int(sum(1 for v in profile.values if v >= min_threshold))
        except Exception:
            features_count = 0

        results.append({
            "Code": code,
            "entropy": float(entropy),
            "features_count": features_count
        })

    # Создаем DataFrame
    results_df = pd.DataFrame(results)

    # Сортируем по энтропии
    if not results_df.empty:
        results_df = results_df.sort_values(by="entropy", ascending=ascending)

    return results_df
