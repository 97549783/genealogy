"""Совместимый модуль-обёртка для старых импортов."""

from tabs.school_comparison.comparison import (
    DistanceMetric,
    ComparisonScope,
    DISTANCE_METRIC_LABELS,
    SCOPE_LABELS,
    load_scores_from_folder,
    get_feature_columns,
    get_nodes_at_level,
    get_selectable_nodes,
    filter_columns_by_nodes,
    get_code_depth,
    compute_silhouette_analysis,
    create_silhouette_plot,
    create_comparison_summary,
    create_node_scores_table,
    interpret_silhouette_score,
    gather_school_dataset,
)
