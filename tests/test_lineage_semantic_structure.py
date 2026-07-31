"""Проверки поколений, ветвей и пересекающегося членства школ."""

import pandas as pd

from core.lineage.graph import build_index
from core.lineage.membership import (
    get_all_school_memberships_by_code, get_school_branch_codes,
    get_school_generation_codes,
)


def _context(signature):
    return (signature, (), ("supervisors_1.name", "supervisors_2.name"))


def test_generations_branches_and_overlap_are_preserved() -> None:
    df = pd.DataFrame([
        {"Code": "1", "candidate_name": "А", "supervisors_1.name": "Корень", "supervisors_2.name": ""},
        {"Code": "2", "candidate_name": "Б", "supervisors_1.name": "Корень", "supervisors_2.name": ""},
        {"Code": "3", "candidate_name": "В", "supervisors_1.name": "А", "supervisors_2.name": "Б"},
    ])
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    signature = ("структура", 1.0, 1)
    key = _context(signature)
    generations = get_school_generation_codes(df, idx, "Корень", signature, context_key=key)
    branches = get_school_branch_codes(df, idx, "Корень", signature, context_key=key)
    inverse = get_all_school_memberships_by_code(df, idx, "all", signature, context_key=key)
    assert generations == {1: {"1", "2"}, 2: {"3"}}
    assert branches["А"] == {"1", "3"}
    assert branches["Б"] == {"2", "3"}
    assert "Корень" in inverse["3"]


def test_cycle_does_not_recurse_forever() -> None:
    df = pd.DataFrame([
        {"Code": "1", "candidate_name": "А", "supervisors_1.name": "Корень"},
        {"Code": "2", "candidate_name": "Корень", "supervisors_1.name": "А"},
    ])
    idx = build_index(df, ["supervisors_1.name"])
    signature = ("цикл", 1.0, 1)
    assert get_school_generation_codes(df, idx, "Корень", signature, context_key=_context(signature)) == {1: {"1"}, 2: {"2"}}
