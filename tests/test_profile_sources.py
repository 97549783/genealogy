from core.domain.profile_sources import (
    get_default_profile_source_id,
    get_profile_source,
    get_profile_source_options,
    get_profile_summary_groups,
)


def test_profile_sources_registered():
    assert get_default_profile_source_id() == "pedagogy_5_8"

    pedagogy = get_profile_source("pedagogy_5_8")
    assert pedagogy.label == "Педагогические науки — 5.8.x / 13.00.xx"
    assert pedagogy.score_table == "diss_scores_5_8"
    assert pedagogy.new_vak_codes == ("5.8",)
    assert pedagogy.old_vak_codes == ("13.00",)

    it = get_profile_source("it_2_3")
    assert it.label == "Информационные технологии — 2.3.x / 05.13.xx"
    assert it.score_table == "diss_scores_2_3"
    assert it.new_vak_codes == ("2.3",)
    assert it.old_vak_codes == ("05.13",)


def test_unknown_profile_source_falls_back_to_default():
    assert get_profile_source("unknown").id == "pedagogy_5_8"


def test_profile_source_options_order():
    assert [source.id for source in get_profile_source_options()] == ["pedagogy_5_8", "it_2_3"]


def test_profile_summary_groups():
    assert get_profile_summary_groups("pedagogy_5_8")
    assert get_profile_summary_groups("it_2_3")
