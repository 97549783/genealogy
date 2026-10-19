"""Stable bibliography order and native v2 multi-access source passports."""
from core.source_schools.bibliography import build_bibliography_text, build_numbered_bibliography, format_bibliographic_reference
from source_school_fixtures import load_vygotsky, synthetic_document


def test_sources_are_numbered_in_json_registry_order():
    d=load_vygotsky();rows=build_numbered_bibliography(d)
    assert [r['№'] for r in rows]==list(range(1,len(d['источники'])+1))
    assert [r['id'] for r in rows]==[s['id'] for s in d['источники']]


def test_doi_access_url_and_access_date_are_not_duplicated():
    s={'библиографическое_описание':'Описание','doi':'10.1/test',
       'доступы':[{'назначение':'полный_текст','url':'https://example.org','дата_обращения':'2026-08-04'}]}
    text=format_bibliographic_reference(s)
    assert 'DOI: 10.1/test' in text and 'https://example.org' in text and '04.08.2026' in text
    s['библиографическое_описание']='Описание DOI: 10.1/test URL: https://example.org'
    assert format_bibliographic_reference(s).count('10.1/test')==1
    assert format_bibliographic_reference(s).count('https://example.org')==1


def test_multiple_accesses_retain_their_distinct_purposes():
    s={'библиографическое_описание':'История исследования','доступы':[
       {'назначение':'полный_текст','url':'https://example.org/full'},
       {'назначение':'эпилог','url':'https://example.org/epilogue'}]}
    text=format_bibliographic_reference(s)
    assert 'полный текст' in text and 'эпилог' in text
    assert all(a['url'] in text for a in s['доступы'])


def test_known_unpublished_local_copy_does_not_receive_a_fake_link():
    d=synthetic_document();rows=build_numbered_bibliography(d)
    assert all(not r['url'] and not r['доступы'] for r in rows)
    assert 'URL' not in build_bibliography_text(d)


def test_text_bibliography_contains_all_numbers():
    d=load_vygotsky();text=build_bibliography_text(d)
    assert len(text.splitlines())==len(d['источники'])
    for n in range(1,len(d['источники'])+1):assert f'{n}.' in text
