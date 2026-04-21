"""Compatibility shim for legacy imports."""

from tabs.school_analysis.analysis import (
    collect_school_subset,
    compute_overview,
    compute_metrics,
    compute_yearly_stats,
    compute_city_stats,
    compute_institutional_stats,
    compute_top_opponents,
    compute_thematic_profile,
    compute_continuity,
)
from tabs.school_analysis.exports import build_excel_report
