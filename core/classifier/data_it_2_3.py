from __future__ import annotations

import json
from pathlib import Path

from .data_pedagogy_5_8 import ClassifierItem

CLASSIFIER_JSON_PATH = Path(__file__).with_name("it_2_3_classifier.json")


def _load_classifier_items_from_json(path: Path = CLASSIFIER_JSON_PATH) -> list[ClassifierItem]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported it_2_3 classifier schema_version")

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("it_2_3 classifier JSON must contain non-empty items list")

    codes: list[str] = []
    labels: list[tuple[str, str]] = []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid classifier item at index {i}: expected object")

        code = str(item.get("code", "")).strip()
        title = str(item.get("title", "")).strip()

        if not code:
            raise ValueError(f"Invalid classifier item at index {i}: empty code")
        if not title:
            raise ValueError(f"Invalid classifier item at index {i}: empty title")

        codes.append(code)
        labels.append((code, title))

    if len(codes) != len(set(codes)):
        duplicates = sorted({code for code in codes if codes.count(code) > 1})
        raise ValueError(f"Duplicate classifier codes in it_2_3 JSON: {duplicates}")

    code_set = set(codes)
    for code in codes:
        if "." in code:
            parent = code.rsplit(".", 1)[0]
            if parent not in code_set:
                raise ValueError(f"Classifier code {code} has missing parent {parent}")

    def is_parent(code: str) -> bool:
        prefix = f"{code}."
        return any(other.startswith(prefix) for other in codes)

    return [(code, title, is_parent(code)) for code, title in labels]


IT_2_3_CLASSIFIER: list[ClassifierItem] = _load_classifier_items_from_json()
