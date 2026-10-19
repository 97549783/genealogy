"""Small native v2.1 fixtures: no legacy projection or source-data migration."""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name('fixtures') / 'source_school_v2.template.json'
VYGOTSKY_PATH = Path(__file__).resolve().parents[1] / 'data/source_schools/schools/vygotsky_cultural_historical_school.json'


def load_vygotsky():
    return json.loads(VYGOTSKY_PATH.read_text(encoding='utf-8'))


def synthetic_document(*, primary=False, facet_count=3):
    doc = json.loads(TEMPLATE.read_text(encoding='utf-8'))
    doc['метаданные'].update(статус='на_проверке', примечание='Синтетический пример для проверки контракта.')
    doc['школа'].update(идентификатор_школы='synthetic_school', каноническое_название='Синтетическая школа',
                        вид_объекта='региональное сообщество', границы_описания='Тестовый корпус независимых источников.',
                        дисциплины=['философия'])
    doc['отображение'].update(центр={'тип':'школа','id':'synthetic_school'}, поля_карточки=['contribution'])
    for suffix in ['alpha', 'beta']:
        doc['источники'].append({'id':'source_'+suffix, 'библиографическое_описание':'Автор '+suffix+'. История исследования. 2020.',
             'название':'История исследования '+suffix, 'авторы':['Автор '+suffix], 'редакторы':[], 'год':2020,
             'жанр':'монография','языки':['ru'],'доступы':[], 'связанные_издания':[], 'проверка':{'статус':'сверено'},
             'файлы':[{'id':'file_'+suffix,'путь_ресурса':None,'число_страниц_pdf':10,'sha256':None,'полнота':'полный_текст'}]})
        doc['основания'].append({'id':'evidence_'+suffix, 'источник':'source_'+suffix,'файл':'file_'+suffix,
             'локатор':{'страницы_pdf':[1], 'печатные_страницы':['1']},'область_ссылки':'конкретное_место',
             'фрагмент':None,'тип_свидетельства':'прямое_сообщение','явность':'явное','проверка':{'статус':'сверено'}})
    for pid, name in [('person_alpha','Альфа Исследователь'),('person_beta','Бета Исследователь'),
                      ('person_gamma','Гамма Исследователь'),('person_delta','Дельта Исследователь'),('person_candidate','Кандидат Исследователь')]:
        doc['объекты']['персоны'].append({'id':pid,'имя':name,'варианты_имени':[],
             'идентификация':{'статус':'установлена','основания':['evidence_alpha']},'внешние_идентификаторы':[]})
        doc['состав'].append({'id':'membership_'+pid,'персона':pid,'отношение_к_школе':'представитель',
             'решение':'кандидат' if pid=='person_candidate' else 'включено','характер':'редакторская_интерпретация',
             'интервалы':[],'основания':['evidence_alpha'],'проверка':{'статус':'сверено'}})
        doc['сведения'].append({'id':'info_'+pid,'субъект':pid,'поле':'contribution',
             'значение':{'вид':'текст','значение':'Самостоятельное исследование '+name+'.'},'роль_значения':'основное',
             'характер':'источниковое_сообщение','решение':'принято','порядок':1,
             'основания':['evidence_alpha'],'проверка':{'статус':'сверено'}})
    facets = [('historical_group','Исторические группы',[('group_alpha','Группа Альфа'),('group_beta','Группа Бета'),('concept_context','Исследования понятий')]),
              ('period','Периоды',[('stage_0','Ранний период')]),
              ('research_direction','Направления',[('research_0','Исследовательское направление')]),
              ('language_context','Языковой контекст',[('ru_context','Русскоязычный контекст')]),
              ('place_context','Географический контекст',[('place_alpha','Регион Альфа')])]
    for i,(fid,label,values) in enumerate(facets[:facet_count],1):
        doc['классификации']['гибкие_измерения'].append({'id':fid,'название':label,'описание':'Явно заданное гибкое измерение.',
             'значения':[{'id':vid,'название':name,'объект':None,'основания':[],'порядок':j} for j,(vid,name) in enumerate(values,1)],
             'порядок':i,'показывать_по_умолчанию':True})
    rows = [('person_alpha','historical_group','group_alpha','источниковое_отнесение','принято'),
            ('person_beta','historical_group','group_beta','классификационная_интерпретация','принято'),
            ('person_gamma','historical_group','concept_context','классификационная_интерпретация','гипотеза'),
            ('person_alpha','period','stage_0','источниковое_отнесение','принято'),
            ('person_beta','period','stage_0','классификационная_интерпретация','принято'),
            ('person_delta','research_direction','research_0','источниковое_отнесение','принято'),
            ('person_beta','research_direction','research_0','классификационная_интерпретация','гипотеза'),
            ('person_alpha','language_context','ru_context','классификационная_интерпретация','принято'),
            ('person_beta','place_context','place_alpha','классификационная_интерпретация','принято')]
    available = {f['id'] for f in doc['классификации']['гибкие_измерения']}
    for i,(pid,fid,vid,nature,decision) in enumerate(rows,1):
        if fid in available:
            doc['классификационные_назначения'].append({'id':'assignment_'+str(i),'персона':pid,'измерение':fid,'значение':vid,
                 'характер':nature,'решение':decision,'интервалы':[],'основания':['evidence_alpha'],'проверка':{'статус':'сверено'}})
    if primary:
        doc['классификации']['основное_деление'] = {'id':'primary_category','название':'Основное деление',
             'правила_отнесения':['Одна категория на человека.'],'период_описания':None,'область_применения':['представитель'],
             'исключённые_персоны':[],'категории':[{'id':'category_alpha','код':'A1','название':'Категория Альфа','критерий':'Первый критерий','порядок':1},
                                              {'id':'category_beta','код':'A2','название':'Категория Бета','критерий':'Второй критерий','порядок':2}]}
        for pid, vid in [('person_alpha','category_alpha'),('person_beta','category_beta')]:
            doc['классификационные_назначения'].append({'id':'primary_'+pid,'персона':pid,'измерение':'primary_category','значение':vid,
                 'характер':'классификационная_интерпретация','решение':'принято','интервалы':[],'основания':['evidence_alpha'],'проверка':{'статус':'сверено'}})
    return doc
