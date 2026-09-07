from aardvark_jd.alfred import parse


# ------------------------------------------------- the title/description split

def test_the_entry_splits_on_the_first_comma():
    assert parse.title_and_description("Cardiologist, GP referrals and letters") == {
        "title": "Cardiologist",
        "description": "GP referrals and letters",
    }


def test_only_the_first_comma_splits():
    """
    *everything after the first comma is description, commas and all*

    A title containing a comma loses the fragment after the first one to
    the description. The confirmation screen catches that before
    anything is written, which is why the parse can stay this simple.
    """
    assert parse.title_and_description("Insurance, buildings, contents") == {
        "title": "Insurance",
        "description": "buildings, contents",
    }


def test_no_comma_means_no_description():
    assert parse.title_and_description("Cardiologist") == {
        "title": "Cardiologist",
        "description": "",
    }


def test_a_leading_comma_leaves_an_empty_title():
    """*shown as an empty title rather than repaired - the parse never guesses*"""
    assert parse.title_and_description(", GP referrals") == {
        "title": "",
        "description": "GP referrals",
    }


def test_a_trailing_comma_leaves_an_empty_description():
    assert parse.title_and_description("Cardiologist,") == {
        "title": "Cardiologist",
        "description": "",
    }


def test_whitespace_around_each_part_is_stripped():
    """*the separator needs no shift key, so a space after it is the common typing*"""
    assert parse.title_and_description("  Cardiologist ,   GP referrals  ") == {
        "title": "Cardiologist",
        "description": "GP referrals",
    }


def test_hyphens_in_a_title_survive_untouched():
    """*why comma beat the hyphen - real titles contain hyphens*"""
    assert parse.title_and_description("Insurance - buildings and contents") == {
        "title": "Insurance - buildings and contents",
        "description": "",
    }


def test_an_empty_entry_parses_to_two_empty_fields():
    assert parse.title_and_description("") == {"title": "", "description": ""}
    assert parse.title_and_description(None) == {"title": "", "description": ""}


def test_the_parse_is_a_new_dict_every_time():
    """*nothing downstream may mutate a shared parse*"""
    first = parse.title_and_description("Cardiologist, notes")
    first["title"] = "mutated"

    assert parse.title_and_description("Cardiologist, notes")["title"] == "Cardiologist"


# --------------------------------------------------------------- the parse view

def test_the_parse_renders_as_the_two_lines_the_step_shows():
    """*the argument step shows the parse and nothing else - no JD code, no path*"""
    parsed = parse.title_and_description("Cardiologist, GP referrals")

    assert parse.parse_subtitle(parsed) == "title = «Cardiologist»  description = «GP referrals»"


def test_an_absent_description_still_renders_its_field():
    """*an empty «» is what tells the user the comma was never typed*"""
    parsed = parse.title_and_description("Cardiologist")

    assert parse.parse_subtitle(parsed) == "title = «Cardiologist»  description = «»"


# ------------------------------------------------- slice 3: the template step

def test_template_names_are_the_sorted_zips_in_the_reserved_templates_folder(tmp_path):
    category = tmp_path / "P11.10_website📁"
    templates = category / "P11.04_templates📐"
    templates.mkdir(parents=True)
    (templates / "site-v2.zip").write_bytes(b"")
    (templates / "site-v1.zip").write_bytes(b"")
    (templates / "notes.txt").write_text("ignore me")

    assert parse.template_names(str(category)) == ["site-v1.zip", "site-v2.zip"]


def test_template_names_is_empty_for_a_category_with_no_templates_folder(tmp_path):
    category = tmp_path / "P12.10_marketing📁"
    category.mkdir()

    assert parse.template_names(str(category)) == []


def test_template_names_is_empty_for_a_blank_path():
    assert parse.template_names("") == []
