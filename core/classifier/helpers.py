from __future__ import annotations

from typing import Optional

from .data import CLASSIFIER_BY_CODE, ClassifierItem

def classifier_depth(code: str) -> int:
    return code.count(".") if code else 0


def classifier_format(option: Optional[ClassifierItem]) -> str:
    if option is None:
        return "— выберите пункт —"
    code, title, disabled = option
    indent = "\u2003" * classifier_depth(code)
    label = f"{code} {title}"
    if disabled:
        label += " (нельзя выбрать)"
    return f"{indent}{label}"


def classifier_label(code: str) -> str:
    item = CLASSIFIER_BY_CODE.get(code)
    if not item:
        return code
    _, title, _ = item
    return f"{code} · {title}"


def classifier_label_from_labels(code: str, labels: dict[str, str]) -> str:
    title = labels.get(code)
    if title:
        return f"{code} · {title}"
    return code


def classifier_item_label(item: ClassifierItem) -> str:
    code, title, _ = item
    return f"{code} · {title}"
