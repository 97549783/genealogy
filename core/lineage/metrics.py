from __future__ import annotations

import math
from itertools import islice
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from statistics import median
from typing import Literal

import networkx as nx
import pandas as pd

from core.db import AUTHOR_COLUMN
from core.lineage.names import norm


@dataclass(frozen=True)
class GenerationCount:
    generation: int
    members: int


@dataclass(frozen=True)
class ProliferationPoint:
    year: int
    new_descendants: int
    cumulative_descendants: int


@dataclass(frozen=True)
class MetricValue:
    key: str
    value: int | float | str | None
    unit: str
    status: Literal["available", "not_applicable", "source_required", "insufficient_data"]
    note: str = ""


@dataclass(frozen=True)
class LineageMetrics:
    root: str
    nodes_including_root: int
    edges: int
    direct_students: int
    continuing_students: int
    continuing_rate_percent: float | None
    descendants: int
    descendant_generations: int | None
    levels_including_root: int | None
    max_width: int | None
    max_width_generation: int | None
    generation_counts: tuple[GenerationCount, ...]
    proliferation_points: tuple[ProliferationPoint, ...]
    dated_descendants: int
    undated_descendants: int
    first_observed_year: int | None
    last_observed_year: int | None
    mean_new_descendants_per_year: float | None
    indirect_descendants_per_direct_student: float | None
    second_generation_descendants_per_direct_student: float | None
    extended_values: tuple[MetricValue, ...]
    technical_values: tuple[MetricValue, ...]
    is_dag: bool
    warnings: tuple[str, ...]


def _empty(root: str, warning: str) -> LineageMetrics:
    return LineageMetrics(root, 0, 0, 0, 0, None, 0, None, None, None, None, tuple(), tuple(), 0, 0, None, None, None, None, None, tuple(), tuple(), True, (warning,))


def _safe_year(value) -> int | None:
    try:
        year = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return year if 1000 <= year <= 3000 else None


def _reachable_graph(graph: nx.DiGraph, root: str) -> nx.DiGraph:
    nodes = {root, *nx.descendants(graph, root)} if root in graph else set()
    return graph.subgraph(nodes).copy()


def _shortest_generations(graph: nx.DiGraph, root: str) -> dict[str, int]:
    return {str(node): int(dist) for node, dist in nx.single_source_shortest_path_length(graph, root).items()}


def _years_by_node(subset: pd.DataFrame, descendants: set[str], author_column: str, year_column: str, warnings: list[str]) -> dict[str, int]:
    if subset.empty or author_column not in subset.columns or year_column not in subset.columns:
        return {}
    exact: dict[str, list[int]] = defaultdict(list)
    normalized: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for _, row in subset.iterrows():
        author = str(row.get(author_column, "")).strip()
        if not author:
            continue
        year = _safe_year(row.get(year_column))
        if year is None:
            continue
        exact[author].append(year)
        normalized[norm(author)].append((author, year))
    if any(len({name for name, _ in matches}) > 1 for matches in normalized.values()):
        warnings.append("Несколько вариантов написания имени совпали после нормализации; для динамики выбран самый ранний валидный год.")
    result: dict[str, int] = {}
    for node in sorted(descendants):
        stripped = str(node).strip()
        if stripped in exact:
            result[node] = min(exact[stripped])
            continue
        matches = normalized.get(norm(stripped), [])
        if matches:
            result[node] = min(year for _, year in matches)
    return result


def _degree_counts(subset: pd.DataFrame, descendants: set[str], author_column: str, degree_column: str, warnings: list[str]) -> tuple[int, int, int]:
    if subset.empty or author_column not in subset.columns or degree_column not in subset.columns:
        return 0, 0, len(descendants)
    names_by_norm: dict[str, set[str]] = defaultdict(set)
    by_norm: dict[str, str] = {}
    for _, row in subset.iterrows():
        author = str(row.get(author_column, "")).strip()
        if not author:
            continue
        key = norm(author)
        raw = str(row.get(degree_column, "")).strip().lower()
        names_by_norm[key].add(author)
        if key not in by_norm:
            by_norm[key] = raw
    ambiguous = any(len(names) > 1 for names in names_by_norm.values())
    if ambiguous:
        warnings.append("Несколько вариантов написания имени совпали после нормализации; для состава по степеням использована первая найденная запись.")
    doctors = candidates = unknown = 0
    for node in descendants:
        raw = by_norm.get(norm(str(node)), "")
        if raw.startswith("док"):
            doctors += 1
        elif raw.startswith("кан"):
            candidates += 1
        else:
            unknown += 1
    return doctors, candidates, unknown


def _branch_generation_counts(graph: nx.DiGraph, root: str, generations: dict[str, int]) -> dict[str, dict[str, int]]:
    children = sorted(str(c) for c in graph.successors(root))
    counts = {child: {"all_with_direct_student": 0, "indirect": 0, "second_generation": 0} for child in children}
    owner: dict[str, str] = {}
    for child in children:
        queue = deque([child])
        seen = {child}
        while queue:
            node = str(queue.popleft())
            if node not in owner:
                owner[node] = child
            for nxt in sorted(str(c) for c in graph.successors(node)):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
    for node, child in owner.items():
        if node == root:
            continue
        counts[child]["all_with_direct_student"] += 1
        generation = generations.get(node)
        if generation is not None and generation >= 2:
            counts[child]["indirect"] += 1
        if generation == 2:
            counts[child]["second_generation"] += 1
    return counts


def _unit_for_extended_metric(key: str) -> str:
    if key.endswith("percent") or key.endswith("share_percent"):
        return "%"
    if key == "branch_balance":
        return "индекс 0-1"
    if key in {"mean_branching_factor", "median_branching_factor"}:
        return "учеников"
    if key in {"median_indirect_descendants_per_direct_student", "median_second_generation_descendants_per_direct_student"}:
        return "потомков"
    if key == "activity_span_years":
        return "лет"
    return ""


def compute_lineage_metrics(graph: nx.DiGraph, root: str, subset: pd.DataFrame, *, author_column: str = AUTHOR_COLUMN, year_column: str = "year", degree_column: str = "degree.degree_level", include_extended: bool = True) -> LineageMetrics:
    if root not in graph:
        if graph.number_of_nodes() == 0:
            return _empty(root, "Граф пуст; метрики недоступны.")
        return _empty(root, "Корень отсутствует в графе; метрики недоступны.")
    warnings: list[str] = []
    rg = _reachable_graph(graph, root)
    descendants = {str(n) for n in rg.nodes if str(n) != str(root)}
    children = set(str(c) for c in rg.successors(root))
    direct = len(children)
    continuing = sum(1 for c in children if rg.out_degree(c) > 0)
    rate = continuing / direct * 100 if direct else None
    is_dag = nx.is_directed_acyclic_graph(rg)
    generations: dict[str, int] = {}
    generation_counts: tuple[GenerationCount, ...] = tuple()
    descendant_generations = levels = max_width = max_width_generation = None
    indirect_per_direct = second_generation_per_direct = None
    if is_dag:
        generations = _shortest_generations(rg, root)
        by_gen = Counter(generations.values())
        generation_counts = tuple(GenerationCount(k, by_gen[k]) for k in sorted(by_gen))
        descendant_generations = max(generations.values()) if generations else 0
        levels = descendant_generations + 1
        widths = [(k, v) for k, v in sorted(by_gen.items()) if k >= 1]
        if widths:
            max_width_generation, max_width = max(widths, key=lambda kv: (kv[1], -kv[0]))
        second_generation_count = sum(1 for gen in generations.values() if gen == 2)
        indirect_count = sum(1 for gen in generations.values() if gen >= 2)
        indirect_per_direct = indirect_count / direct if direct else None
        second_generation_per_direct = second_generation_count / direct if direct else None
    else:
        warnings.append("В достижимой части графа найден цикл; метрики поколений, ширины и динамики не рассчитываются.")
        for cycle in islice(nx.simple_cycles(rg), 3):
            warnings.append("Цикл: " + " → ".join(map(str, cycle)))
    years_by_node = {} if not is_dag else _years_by_node(subset, descendants, author_column, year_column, warnings)
    dated = len(years_by_node)
    undated = len(descendants) - dated
    points: tuple[ProliferationPoint, ...] = tuple()
    first = last = None
    mean_per_year = None
    if years_by_node:
        counts = Counter(years_by_node.values())
        first, last = min(counts), max(counts)
        cumulative = 0
        items = []
        for year in range(first, last + 1):
            new = counts.get(year, 0)
            cumulative += new
            items.append(ProliferationPoint(year, new, cumulative))
        points = tuple(items)
        mean_per_year = dated / (last - first + 1)
    ext: list[MetricValue] = []
    branch_counts = _branch_generation_counts(rg, root, generations) if is_dag else {}
    branch_sizes = {child: values["all_with_direct_student"] for child, values in branch_counts.items()}
    if include_extended:
        out_degrees = [int(rg.out_degree(n)) for n in rg.nodes]
        nonzero = [d for d in out_degrees if d > 0]
        terminal = sum(1 for n in descendants if rg.out_degree(n) == 0)
        internal = sum(1 for n in descendants if rg.out_degree(n) > 0)
        max_branch = max(nonzero) if nonzero else 0
        max_branch_nodes = ", ".join(sorted(str(n) for n in rg.nodes if rg.out_degree(n) == max_branch and max_branch > 0)) or None
        total_branch = sum(branch_sizes.values())
        branch_values = sorted(branch_sizes.values(), reverse=True)
        if len([v for v in branch_values if v > 0]) > 1 and total_branch:
            probs = [v / total_branch for v in branch_values if v > 0]
            balance = -sum(p * math.log(p) for p in probs) / math.log(len(probs))
        else:
            balance = None
        h = 0
        for k in range(1, len(branch_values) + 1):
            if sum(1 for v in branch_values if v >= k) >= k:
                h = k
        dated_counts = Counter(years_by_node.values())
        peak_year = min((y for y, c in dated_counts.items() if c == max(dated_counts.values())), default=None) if dated_counts else None
        peak_count = max(dated_counts.values()) if dated_counts else None
        gaps = [p.new_descendants for p in points]
        max_gap = cur = 0
        for value in gaps:
            cur = cur + 1 if value == 0 else 0
            max_gap = max(max_gap, cur)
        recent = sum(1 for y in years_by_node.values() if last is not None and y >= last - 4)
        doctors, candidates, unknown = _degree_counts(subset, descendants, author_column, degree_column, warnings)
        indirect_branch_values = [v["indirect"] for v in branch_counts.values()]
        second_generation_branch_values = [v["second_generation"] for v in branch_counts.values()]
        values = {
            "terminal_descendants": terminal, "terminal_share_percent": terminal / len(descendants) * 100 if descendants else None,
            "internal_descendants": internal, "internal_share_percent": internal / len(descendants) * 100 if descendants else None,
            "mean_branching_factor": sum(nonzero) / len(nonzero) if nonzero else None, "median_branching_factor": median(nonzero) if nonzero else None,
            "max_local_branching": max_branch, "max_local_branching_nodes": max_branch_nodes,
            "mean_descendant_generation": sum(generations.get(n, 0) for n in descendants) / len(descendants) if is_dag and descendants else None,
            "normalized_depth": descendant_generations / math.log2(len(descendants) + 1) if is_dag and descendants and descendant_generations is not None else None,
            "branch_balance": balance, "largest_branch_share_percent": max(branch_values) / total_branch * 100 if total_branch else None,
            "median_indirect_descendants_per_direct_student": median(indirect_branch_values) if indirect_branch_values else None,
            "median_second_generation_descendants_per_direct_student": median(second_generation_branch_values) if second_generation_branch_values else None,
            "structural_h_index": h, "linearity_index_percent": sum(1 for d in out_degrees if d == 1) / len(nonzero) * 100 if nonzero else None,
            "activity_span_years": last - first + 1 if first is not None and last is not None else None, "peak_growth_year": peak_year, "peak_growth_count": peak_count,
            "max_inactive_gap_years": max_gap if points else None, "recent_activity_5_years": recent if points else None,
            "doctor_descendants": doctors, "candidate_descendants": candidates, "unknown_degree_descendants": unknown,
            "doctor_share_percent": doctors / len(descendants) * 100 if descendants else None, "candidate_share_percent": candidates / len(descendants) * 100 if descendants else None, "unknown_degree_share_percent": unknown / len(descendants) * 100 if descendants else None,
        }
        ext = [MetricValue(k, v, _unit_for_extended_metric(k), "available" if v is not None else "insufficient_data") for k, v in values.items()]
    multi = sum(1 for n in descendants if rg.in_degree(n) > 1)
    tech_values = (
        MetricValue("multi_parent_nodes", multi, "", "available"),
        MetricValue("multi_parent_share_percent", multi / len(descendants) * 100 if descendants else None, "%", "available" if descendants else "not_applicable"),
        MetricValue("edge_surplus", rg.number_of_edges() - (rg.number_of_nodes() - 1) if rg.number_of_nodes() else 0, "", "available"),
        MetricValue("undated_descendants", undated, "", "available"),
        MetricValue("undated_share_percent", undated / len(descendants) * 100 if descendants else None, "%", "available" if descendants else "not_applicable"),
    )
    return LineageMetrics(str(root), rg.number_of_nodes(), rg.number_of_edges(), direct, continuing, rate, len(descendants), descendant_generations, levels, max_width, max_width_generation, generation_counts, points, dated, undated, first, last, mean_per_year, indirect_per_direct, second_generation_per_direct, tuple(ext), tech_values, is_dag, tuple(dict.fromkeys(warnings)))
