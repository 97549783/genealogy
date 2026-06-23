from core.lineage import get_metric_definitions


def test_metric_definitions_have_clean_visible_text_and_verified_sources():
    definitions = get_metric_definitions(include_extended=True, include_technical=True)
    sources = {source.short_citation: source for definition in definitions for source in definition.sources}
    for definition in definitions:
        visible_text = " ".join([
            definition.title,
            " ".join(definition.aliases),
            definition.group,
            definition.short_description,
            definition.formula_markdown,
            definition.interpretation,
            " ".join(definition.caveats),
        ]).lower()
        assert "не является" not in visible_text
        assert "не входит" not in visible_text
        assert "глава" not in visible_text
    assert sources["Russell, Sugimoto 2009"].full_citation
    assert sources["Rossi, Freire, Mena-Chalco 2017"].doi_or_url == "10.1016/j.joi.2017.04.001"
    assert sources["Rossi et al. 2018"].doi_or_url == "10.1016/j.joi.2018.08.004"
    assert sources["Dores, Benevenuto, Laender 2016"].doi_or_url == "10.1145/2910896.2910916"
    assert sources["Liénard et al. 2018"].doi_or_url == "10.1038/s41467-018-07034-y"
    assert all(source.full_citation is not None for source in sources.values() if source.status == "verified")


def test_metric_definition_exports_are_available():
    import core.lineage as lineage

    assert lineage.MetricDefinition
    assert lineage.MetricSource
    assert lineage.get_metric_definition("g_score").title == "Генеалогический индекс"
