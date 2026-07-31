"""Метки и политики разделов характеристик диссертаций."""

from __future__ import annotations

DISPLAY_SECTION_KEYS = [
    "research_relevance", "research_problem", "research_object", "research_subject",
    "research_goal", "research_hypothesis", "research_tasks", "research_methods",
    "scientific_novelty", "theoretical_significance", "practical_significance",
    "defensible_propositions", "approbation", "publications", "structure",
]

SEARCHABLE_SECTION_KEYS = [
    "research_relevance", "research_problem", "research_object", "research_subject",
    "research_goal", "research_hypothesis", "research_tasks", "research_methods",
    "scientific_novelty", "theoretical_significance", "practical_significance",
    "defensible_propositions", "approbation",
]

SECTION_PRESETS = {
    "all": tuple(SEARCHABLE_SECTION_KEYS),
    "research_design": (
        "research_object", "research_subject", "research_goal",
        "research_hypothesis", "research_tasks",
    ),
    "methods": ("research_methods",),
    "contribution": (
        "scientific_novelty", "theoretical_significance",
        "practical_significance", "defensible_propositions",
    ),
}

SECTION_PRESET_LABELS_RU = {
    "all": "Все разделы",
    "research_design": "Замысел исследования",
    "methods": "Методы исследования",
    "contribution": "Научный вклад",
}

SECTION_LABELS_RU = {
    "research_relevance": "Актуальность исследования",
    "research_problem": "Проблема исследования",
    "research_object": "Объект исследования",
    "research_subject": "Предмет исследования",
    "research_goal": "Цель исследования",
    "research_hypothesis": "Гипотеза исследования",
    "research_tasks": "Задачи исследования",
    "research_methods": "Методы исследования",
    "scientific_novelty": "Научная новизна",
    "theoretical_significance": "Теоретическая значимость",
    "practical_significance": "Практическая значимость",
    "defensible_propositions": "Положения, выносимые на защиту",
    "approbation": "Апробация и внедрение результатов",
    "publications": "Публикации автора по теме диссертации",
    "structure": "Структура работы",
}
