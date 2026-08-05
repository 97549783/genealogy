"""Проверки экспорта школ по источникам."""
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from core.source_schools.export import build_filtered_people_csv, build_source_school_export_bundle
from core.source_schools.tree import build_source_school_overview_tree
from core.ui.tree_renderers import build_markmap_html

PATH = Path("data/source_schools/vygotsky_school_sources_demo.v1.json")


def test_выборка_csv_содержит_bom():
    data = build_filtered_people_csv(pd.DataFrame([{"Представитель": "Лев Семёнович Выготский"}]))
    assert data.startswith(b"\xef\xbb\xbf")


def test_zip_содержит_основные_файлы():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    tree = build_source_school_overview_tree(document)
    html, _ = build_markmap_html(tree.graph, tree.root_id)
    bundle = build_source_school_export_bundle(document=document, source_path=PATH, tree=tree, tree_html=html, tree_png=b"png")
    names = zipfile.ZipFile(io.BytesIO(bundle.zip_bytes)).namelist()
    slug = document["школа"]["идентификатор_школы"]
    assert f"{slug}.json" in names
    assert f"{slug}.интерактивное_дерево.html" in names
    assert f"{slug}.дерево.png" in names
