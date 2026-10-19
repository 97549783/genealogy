"""Full raw v2 data survive exports; filtered exports remain selected views."""
import copy
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from core.source_schools.export import build_filtered_people_csv, build_filtered_people_xlsx, build_source_school_export_bundle
from core.source_schools.tables import build_classification_dataframes, build_people_dataframe
from core.source_schools.tree import build_source_school_overview_tree
from source_school_fixtures import synthetic_document


def bundle(d):
    return build_source_school_export_bundle(document=d,source_path=Path('does-not-exist.json'),
        tree=build_source_school_overview_tree(d),tree_html='<html><body>Дерево</body></html>',tree_png=b'png')


def test_filtered_csv_has_utf8_bom_and_only_the_requested_rows():
    df=build_people_dataframe(synthetic_document()).iloc[:1]
    data=build_filtered_people_csv(df)
    assert data.startswith(b'\xef\xbb\xbf')
    assert pd.read_csv(io.BytesIO(data))['id'].tolist()==['person_alpha']


def test_filtered_xlsx_has_only_requested_rows():
    df=build_people_dataframe(synthetic_document()).iloc[:1]
    data=build_filtered_people_xlsx(df)
    assert pd.read_excel(io.BytesIO(data))['id'].tolist()==['person_alpha']


def test_full_zip_contains_all_core_artifacts_and_exact_current_json():
    d=synthetic_document();d['метаданные']['примечание']='Текущее изменение в памяти.';before=copy.deepcopy(d)
    b=bundle(d);archive=zipfile.ZipFile(io.BytesIO(b.zip_bytes));slug=d['школа']['идентификатор_школы']
    expected=['json','данные.xlsx','представители.csv','кандидаты.csv','источники.csv','подтверждения.csv',
              'классификационные_назначения.csv','основания_классификации.csv','сведения.csv','связи.csv','объекты.csv',
              'рёбра_дерева.csv','список_источников.txt','интерактивное_дерево.html','дерево.png']
    assert {f'{slug}.{suffix}' for suffix in expected}.issubset(archive.namelist())
    assert json.loads(archive.read(f'{slug}.json'))==d==before
    assert json.loads(b.json_bytes)==d
    assert archive.read(f'{slug}.дерево.png')==b'png'


def test_all_assignment_decisions_and_source_locators_survive_csv_and_xlsx():
    d=synthetic_document();assignments,bases=build_classification_dataframes(d)
    assert len(assignments)==len(d['классификационные_назначения'])
    assert len(bases)==len(assignments)
    assert set(assignments['Решение'])=={'принято','гипотеза'}
    assert set(bases['ID источника'])=={'source_alpha'} and all(bases['Локатор'])
    b=bundle(d);workbook=pd.ExcelFile(io.BytesIO(b.xlsx_bytes))
    assert {'Представители','Кандидаты','Источники','Подтверждения','Классификации','Основания классификаций','Сведения','Связи','Состав','Рёбра дерева'}.issubset(workbook.sheet_names)
    exported=pd.read_excel(workbook,sheet_name='Классификации')
    assert set(exported['ID назначения'])==set(assignments['ID назначения'])
    assert 'гипотеза' in set(exported['Решение'])
    assert len(pd.read_excel(workbook,sheet_name='Представители'))==4
    assert len(pd.read_excel(workbook,sheet_name='Кандидаты'))==1
    assert set(pd.read_csv(io.BytesIO(b.assignments_csv_bytes))['ID назначения'])==set(assignments['ID назначения'])
    assert set(pd.read_csv(io.BytesIO(b.assignment_bases_csv_bytes))['ID основания'])=={'evidence_alpha'}


def test_assignment_export_resolves_transitive_source_support():
    d=synthetic_document();a=d['классификационные_назначения'][0]
    a['основания']=[];a['опирается_на']=[d['сведения'][1]['id']]
    d['сведения'][1]['основания']=['evidence_beta']
    _,bases=build_classification_dataframes(d)
    rows=bases[bases['ID назначения']==a['id']]
    assert rows['ID основания'].tolist()==['evidence_beta']
    assert rows['ID источника'].tolist()==['source_beta']


def test_empty_classification_exports_keep_structured_headers():
    d=synthetic_document();d['классификационные_назначения']=[]
    a,b=build_classification_dataframes(d)
    assert a.empty and b.empty
    assert {'ID назначения','Решение','Характер'}.issubset(a.columns)
    assert {'ID основания','ID источника','Локатор'}.issubset(b.columns)
    result=bundle(d)
    assert pd.read_csv(io.BytesIO(result.assignments_csv_bytes)).empty
    assert pd.read_csv(io.BytesIO(result.assignment_bases_csv_bytes)).empty
