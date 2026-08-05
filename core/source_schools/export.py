"""Экспорт данных школы по источникам."""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from openpyxl.styles import Alignment

from .bibliography import build_bibliography_text
from .tables import build_evidence_dataframe, build_people_dataframe, build_sources_dataframe
from .tree import SourceSchoolTree, build_source_school_tree_edges_dataframe


@dataclass(frozen=True)
class SourceSchoolExportBundle:
    """Набор байтов для пользовательских скачиваний."""

    json_bytes: bytes
    xlsx_bytes: bytes
    representatives_csv_bytes: bytes
    sources_csv_bytes: bytes
    evidence_csv_bytes: bytes
    bibliography_txt_bytes: bytes
    tree_html_bytes: bytes
    tree_png_bytes: bytes
    zip_bytes: bytes


def _slug(document: Mapping[str, Any]) -> str:
    return str(document["школа"].get("идентификатор_школы", "source_school"))


def _csv_bytes(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False).encode("utf-8-sig")


def _write_sheet(writer: pd.ExcelWriter, name: str, dataframe: pd.DataFrame) -> None:
    dataframe.to_excel(writer, sheet_name=name, index=False)
    sheet = writer.book[name]
    sheet.freeze_panes = "A2"
    if sheet.max_row and sheet.max_column:
        sheet.auto_filter.ref = sheet.dimensions
    for column_cells in sheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 60)
        letter = column_cells[0].column_letter
        sheet.column_dimensions[letter].width = width
        for cell in column_cells:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def _xlsx_bytes(document: Mapping[str, Any], tree: SourceSchoolTree) -> bytes:
    school = document["школа"]
    structure = school.get("внутренняя_структура", {})
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _write_sheet(writer, "Общие сведения", pd.DataFrame([{"Показатель": "Каноническое название", "Значение": school.get("каноническое_название", "")}]))
        _write_sheet(writer, "Представители", build_people_dataframe(document))
        _write_sheet(writer, "Источники", build_sources_dataframe(document))
        _write_sheet(writer, "Подтверждения", build_evidence_dataframe(document))
        _write_sheet(writer, "Группы", pd.json_normalize(structure.get("исследовательские_группы", [])))
        _write_sheet(writer, "Направления", pd.json_normalize(structure.get("направления", [])))
        _write_sheet(writer, "Поколения", pd.json_normalize(structure.get("поколения", [])))
        _write_sheet(writer, "Рёбра дерева", build_source_school_tree_edges_dataframe(tree))
    return output.getvalue()


def build_source_school_export_bundle(*, document: Mapping[str, Any], source_path: Path, tree: SourceSchoolTree, tree_html: str, tree_png: bytes) -> SourceSchoolExportBundle:
    """Формирует полный набор файлов экспорта."""
    slug = _slug(document)
    json_bytes = source_path.read_bytes() if source_path.exists() else json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    xlsx_bytes = _xlsx_bytes(document, tree)
    representatives_csv_bytes = _csv_bytes(build_people_dataframe(document))
    sources_csv_bytes = _csv_bytes(build_sources_dataframe(document))
    evidence_csv_bytes = _csv_bytes(build_evidence_dataframe(document))
    bibliography_txt_bytes = build_bibliography_text(document).encode("utf-8")
    edge_csv_bytes = _csv_bytes(build_source_school_tree_edges_dataframe(tree))
    tree_html_bytes = tree_html.encode("utf-8")
    zip_output = io.BytesIO()
    with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{slug}.json", json_bytes)
        archive.writestr(f"{slug}.данные.xlsx", xlsx_bytes)
        archive.writestr(f"{slug}.представители.csv", representatives_csv_bytes)
        archive.writestr(f"{slug}.источники.csv", sources_csv_bytes)
        archive.writestr(f"{slug}.подтверждения.csv", evidence_csv_bytes)
        archive.writestr(f"{slug}.рёбра_дерева.csv", edge_csv_bytes)
        archive.writestr(f"{slug}.список_источников.txt", bibliography_txt_bytes)
        archive.writestr(f"{slug}.дерево.png", tree_png)
        archive.writestr(f"{slug}.интерактивное_дерево.html", tree_html_bytes)
    return SourceSchoolExportBundle(json_bytes, xlsx_bytes, representatives_csv_bytes, sources_csv_bytes, evidence_csv_bytes, bibliography_txt_bytes, tree_html_bytes, tree_png, zip_output.getvalue())


def build_filtered_people_csv(dataframe: pd.DataFrame) -> bytes:
    """Формирует CSV текущей отфильтрованной таблицы представителей."""
    return _csv_bytes(dataframe.copy())


def build_filtered_people_xlsx(dataframe: pd.DataFrame) -> bytes:
    """Формирует XLSX текущей отфильтрованной таблицы представителей."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _write_sheet(writer, "Представители", dataframe.copy())
    return output.getvalue()
