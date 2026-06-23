from pathlib import Path


def test_no_external_metrics_ui_imports():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("tabs/lineages/"):
            continue
        text = path.read_text(encoding="utf-8")
        needle = "tabs.lineages" + ".metrics_ui"
        if needle in text:
            offenders.append(rel)
    assert offenders == []
