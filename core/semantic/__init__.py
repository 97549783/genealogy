"""Общая семантическая инфраструктура анализа диссертаций."""

from core.semantic.models import (
    PairwiseDistanceDiagnostics,
    QueryRankingConfig,
    SectionSelection,
    SemanticAnalysisLimits,
    VectorMetadata,
    build_section_selection,
)

__all__ = [
    "PairwiseDistanceDiagnostics", "QueryRankingConfig", "SectionSelection",
    "SemanticAnalysisLimits", "VectorMetadata", "build_section_selection",
]
