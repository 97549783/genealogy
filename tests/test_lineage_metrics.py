import networkx as nx
import pandas as pd

from core.lineage.metrics import compute_lineage_metrics


def _mv(metrics, key):
    return next(v.value for v in (*metrics.extended_values, *metrics.technical_values) if v.key == key)


def test_simple_tree_metrics():
    graph = nx.DiGraph([("root", "A"), ("root", "B"), ("A", "C"), ("C", "D")])
    subset = pd.DataFrame({"candidate_name": ["A", "B", "C", "D"], "year": [2000, 2001, 2003, 2006]})
    metrics = compute_lineage_metrics(graph, "root", subset)
    assert metrics.direct_students == 2
    assert metrics.continuing_students == 1
    assert metrics.continuing_rate_percent == 50.0
    assert metrics.descendants == 4
    assert metrics.descendant_generations == 3
    assert metrics.levels_including_root == 4
    assert [(g.generation, g.members) for g in metrics.generation_counts] == [(0, 1), (1, 2), (2, 1), (3, 1)]
    assert metrics.max_width == 2
    assert metrics.max_width_generation == 1
    assert [p.year for p in metrics.proliferation_points] == list(range(2000, 2007))


def test_dag_shared_descendant_is_not_double_counted():
    graph = nx.DiGraph([("root", "A"), ("root", "B"), ("A", "C"), ("B", "C")])
    metrics = compute_lineage_metrics(graph, "root", pd.DataFrame())
    assert metrics.descendants == 3
    assert dict((g.generation, g.members) for g in metrics.generation_counts)[2] == 1
    assert metrics.edges == 4
    assert _mv(metrics, "multi_parent_nodes") == 1
    assert _mv(metrics, "edge_surplus") == 1


def test_cycle_returns_warning_and_keeps_basic_metrics():
    graph = nx.DiGraph([("root", "A"), ("A", "B"), ("B", "A")])
    metrics = compute_lineage_metrics(graph, "root", pd.DataFrame())
    assert metrics.is_dag is False
    assert metrics.descendant_generations is None
    assert metrics.direct_students == 1
    assert metrics.warnings


def test_empty_and_missing_root():
    assert compute_lineage_metrics(nx.DiGraph(), "root", pd.DataFrame()).warnings
    graph = nx.DiGraph([("A", "B")])
    assert compute_lineage_metrics(graph, "root", pd.DataFrame()).warnings


def test_extended_metrics():
    graph = nx.DiGraph([("root", "A"), ("root", "B"), ("A", "C"), ("A", "D"), ("C", "E")])
    metrics = compute_lineage_metrics(graph, "root", pd.DataFrame())
    assert _mv(metrics, "terminal_descendants") == 3
    assert _mv(metrics, "internal_descendants") == 2
    assert _mv(metrics, "max_local_branching") == 2
    assert _mv(metrics, "max_local_branching_nodes") == "A, root"
    assert _mv(metrics, "mean_descendant_generation") == 1.8
    assert _mv(metrics, "largest_branch_share_percent") == 80.0
    assert _mv(metrics, "edge_surplus") == 0


def test_duplicate_rows_name_variants_missing_years_and_g_score():
    graph = nx.DiGraph([("root", "Иванов Иван Иванович"), ("Иванов Иван Иванович", "Петров П.П.")])
    subset = pd.DataFrame([
        {"candidate_name": "Иванов Иван Иванович", "year": "2005", "degree.degree_level": "доктор наук"},
        {"candidate_name": "Иванов И. И.", "year": "2007", "degree.degree_level": "доктор наук"},
        {"candidate_name": "Петров П.П.", "year": "нет", "degree.degree_level": "кандидат наук"},
    ])
    metrics = compute_lineage_metrics(graph, "root", subset)
    assert metrics.dated_descendants == 1
    assert metrics.undated_descendants == 1
    assert metrics.g_score is None
    assert metrics.g_score_status == "source_required"
    assert _mv(metrics, "doctor_descendants") == 1
    assert _mv(metrics, "candidate_descendants") == 1
