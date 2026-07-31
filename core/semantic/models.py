"""Неизменяемые контракты общей семантической инфраструктуры."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Mapping, Sequence

from tabs.dissertation_characteristics.labels import SEARCHABLE_SECTION_KEYS

SemanticScope = Literal["direct", "all"]
SectionSelectionMode = Literal["all", "selected"]
SchoolQueryRankingMode = Literal["broad", "focused"]
SemanticRepresentation = Literal["classifier", "characteristics"]


@dataclass(frozen=True)
class SectionSelection:
    """Описывает выбранные разделы, их веса и порог покрытия."""

    mode: SectionSelectionMode
    section_keys: tuple[str, ...]
    weights: tuple[tuple[str, float], ...]
    min_coverage: float

    def __post_init__(self) -> None:
        if self.mode not in ("all", "selected"):
            raise ValueError("Неизвестный режим выбора разделов.")
        requested = set(SEARCHABLE_SECTION_KEYS if self.mode == "all" else self.section_keys)
        unknown = requested - set(SEARCHABLE_SECTION_KEYS)
        if unknown:
            raise ValueError("Выбраны неизвестные разделы характеристик.")
        ordered = tuple(key for key in SEARCHABLE_SECTION_KEYS if key in requested)
        if not ordered:
            raise ValueError("Необходимо выбрать хотя бы один раздел.")
        if not isfinite(float(self.min_coverage)) or not 0.0 <= float(self.min_coverage) <= 1.0:
            raise ValueError("Минимальное покрытие должно находиться в диапазоне от 0 до 1.")
        weight_map = dict(self.weights)
        if len(weight_map) != len(self.weights) or set(weight_map) != set(ordered):
            raise ValueError("Вес должен быть задан ровно один раз для каждого выбранного раздела.")
        if any(not isfinite(float(value)) or float(value) <= 0.0 for value in weight_map.values()):
            raise ValueError("Веса разделов должны быть конечными положительными числами.")
        object.__setattr__(self, "section_keys", ordered)
        object.__setattr__(self, "weights", tuple((key, float(weight_map[key])) for key in ordered))


@dataclass(frozen=True)
class VectorMetadata:
    """Содержит проверенные метаданные матрицы векторов."""

    model_name: str
    normalized: bool
    dimensions: int
    matrix_signature: tuple[str, float, int]


@dataclass(frozen=True)
class QueryRankingConfig:
    """Задаёт параметры ранжирования научных школ по запросу."""

    ranking_mode: SchoolQueryRankingMode
    relevance_threshold: float
    shrinkage_strength: float
    minimum_school_size: int
    minimum_covered_dissertations: int


@dataclass(frozen=True)
class PairwiseDistanceDiagnostics:
    """Описывает полноту построенной попарной матрицы."""

    item_count: int
    undefined_pair_count: int
    selected_section_count: int
    minimum_coverage: float


@dataclass(frozen=True)
class SemanticAnalysisLimits:
    """Задаёт ограничения пакетной семантической обработки."""

    batch_size: int
    school_batch_size: int
    maximum_pairwise_items: int


def build_section_selection(
    mode: SectionSelectionMode = "all",
    section_keys: Sequence[str] | None = None,
    weights: Mapping[str, float] | Sequence[tuple[str, float]] | None = None,
    min_coverage: float = 0.60,
) -> SectionSelection:
    """Создаёт выбор разделов в устойчивом каноническом порядке."""
    if mode not in ("all", "selected"):
        raise ValueError("Неизвестный режим выбора разделов.")
    requested = set(SEARCHABLE_SECTION_KEYS if mode == "all" else (section_keys or ()))
    unknown = requested - set(SEARCHABLE_SECTION_KEYS)
    if unknown:
        raise ValueError("Выбраны неизвестные разделы характеристик.")
    ordered = tuple(key for key in SEARCHABLE_SECTION_KEYS if key in requested)
    supplied = dict(weights or ())
    if set(supplied) - set(SEARCHABLE_SECTION_KEYS):
        raise ValueError("Для неизвестного раздела задан вес.")
    if supplied and set(supplied) != set(ordered):
        raise ValueError("Явные веса должны охватывать все и только выбранные разделы.")
    ordered_weights = tuple((key, float(supplied.get(key, 1.0))) for key in ordered)
    return SectionSelection(mode, ordered, ordered_weights, float(min_coverage))
