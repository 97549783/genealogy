from __future__ import annotations

from pathlib import Path


LEGACY_PATHS = [
    "school_search.py",
    "school_trees.py",
    "utils/__init__.py",
    "utils/names.py",
    "utils/tree_renderers.py",
    "entropy_specificity.py",
    "articles_classifier.json",
]


def test_legacy_modules_are_removed() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    missing = [path for path in LEGACY_PATHS if (repo_root / path).exists()]
    assert missing == []


def test_utils_package_directory_removed_or_empty() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    utils_dir = repo_root / "utils"
    if not utils_dir.exists():
        return
    assert list(utils_dir.iterdir()) == []
