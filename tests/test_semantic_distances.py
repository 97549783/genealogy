"""Проверки описательных семантических расстояний."""

import numpy as np

from core.semantic.distances import (
    categorize_distances,
    compute_precomputed_silhouette,
    find_medoid,
    summarize_heterogeneity,
)


def test_medoid_and_summary() -> None:
    matrix = np.array([[0, 1, 2], [1, 0, 1], [2, 1, 0]], dtype=float)
    assert find_medoid(["A", "B", "C"], matrix) == ("B", 1.0)
    summary = summarize_heterogeneity([0, 1, 2])
    assert summary["core_radius"] == summary["median_distance"] == 1


def test_categories_are_russian_only_for_five_or_more_items() -> None:
    small = categorize_distances(["A", "B"], [0.1, 0.2])
    assert small["category"].isna().all()
    large = categorize_distances(list("ABCDE"), [0, 1, 2, 3, 4])
    assert large.iloc[0]["category"] == "Тематическое ядро"
    assert large.iloc[-1]["category"] == "Наиболее удалённые работы"


def test_precomputed_silhouette() -> None:
    matrix = np.array([
        [0, 0.1, 1, 1], [0.1, 0, 1, 1], [1, 1, 0, 0.1], [1, 1, 0.1, 0],
    ])
    score, samples = compute_precomputed_silhouette(matrix, [0, 0, 1, 1])
    assert np.isclose(score, 0.9)
    assert samples.shape == (4,)


def test_medoid_excludes_diagonal_and_supports_one_item() -> None:
    matrix = np.array([[9.0, 2.0], [2.0, 8.0]])
    assert find_medoid(["A", "B"], matrix) == ("A", 2.0)
    assert find_medoid(["A"], np.array([[7.0]])) == ("A", 0.0)


def test_silhouette_does_not_mutate_input() -> None:
    matrix = np.array([[5, .1, 1, 1], [.1, 4, 1, 1], [1, 1, 3, .1], [1, 1, .1, 2]], dtype=float)
    original = matrix.copy()
    compute_precomputed_silhouette(matrix, [0, 0, 1, 1])
    assert np.array_equal(matrix, original)
