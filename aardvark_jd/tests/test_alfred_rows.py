from aardvark_jd.alfred import rows

PARSED = {"title": "Aadvark notes", "description": "everything about them"}
SUGGESTIONS = [{"token": "Aadvark", "index": 0, "suggested": "aardvark"}]


# --------------------------------------------------------- the argument step

def test_the_back_row_is_a_row_not_a_key():
    """
    *Escape discards the run rather than stepping back, and a chord hint would compete with the parse*

    A row is visible without being read and costs nothing when unused.
    """
    row = rows.back_row("Choose a different category")

    assert row["title"] == "Choose a different category"
    assert row["valid"] is True
    assert row["variables"]["action"] == "back"


# ------------------------------------------------------ the confirmation screen

def test_create_as_typed_is_first_and_is_what_return_does():
    """*Return always means create, which is why accepting a correction re-renders instead*"""
    items = rows.confirmation_items(PARSED, [])

    assert len(items) == 1
    assert items[0]["title"] == "Create as typed"
    assert items[0]["subtitle"] == "title = «Aadvark notes»  description = «everything about them»"
    assert items[0]["valid"] is True
    assert items[0]["variables"]["action"] == "create"


def test_each_suspect_token_adds_one_row_beside_it():
    items = rows.confirmation_items(PARSED, SUGGESTIONS)

    assert [item["title"] for item in items] == [
        "Create as typed", "Use «Aardvark» instead of «Aadvark»",
    ]


def test_a_correction_row_re_renders_rather_than_committing():
    """*accepting one is not the commit - each is accepted independently*"""
    correction = rows.confirmation_items(PARSED, SUGGESTIONS)[1]

    assert correction["variables"]["action"] == "recheck"
    assert correction["variables"]["title"] == "Aardvark notes"
    assert correction["variables"]["description"] == "everything about them"


def test_a_correction_row_carries_the_original_capitalisation():
    """*the suggestion is a lowercase dictionary word; the title's case wins*"""
    items = rows.confirmation_items(
        {"title": "AADVARK notes", "description": ""},
        [{"token": "AADVARK", "index": 0, "suggested": "aardvark"}],
    )

    assert items[1]["variables"]["title"] == "AARDVARK notes"


def test_teaching_the_vocabulary_needs_its_own_modifier():
    """
    *a deliberate divergence from the CLI, which teaches a word on a decline*

    Under this shape declining is the default path, so the CLI's rule
    would teach a word on every reflexive Return.
    """
    correction = rows.confirmation_items(PARSED, SUGGESTIONS)[1]

    assert correction["mods"]["cmd"]["variables"]["action"] == "teach"
    assert correction["mods"]["cmd"]["variables"]["token"] == "Aadvark"
    assert "Aadvark" in correction["mods"]["cmd"]["subtitle"]


def test_a_second_suspect_token_gets_its_own_row():
    items = rows.confirmation_items(
        {"title": "Aadvark cardilogist", "description": ""},
        [
            {"token": "Aadvark", "index": 0, "suggested": "aardvark"},
            {"token": "cardilogist", "index": 1, "suggested": "cardiologist"},
        ],
    )

    assert len(items) == 3
    assert items[1]["variables"]["title"] == "Aardvark cardilogist"
    assert items[2]["variables"]["title"] == "Aadvark cardiologist"


# --------------------------------------------------------- the success surface

ENTITY = {
    "code": "A11.12", "title": "Podiatrist", "folder_path": "/root/A11.12_podiatrist",
    "urls": {
        "finder": "file:///root/A11.12_podiatrist", "craft": "https://craft/x",
        "todoist": None, "drive": None, "dropbox": None,
    },
}


def test_the_success_surface_leads_with_what_was_created():
    """*this is the whole recall story - the cached index has not caught up yet*"""
    items = rows.success_items(ENTITY)

    assert items[0]["title"] == "A11.12  Podiatrist"
    assert items[0]["variables"]["action"] == "reveal"
    assert items[0]["arg"] == "/root/A11.12_podiatrist"


def test_the_success_surface_offers_the_handoff():
    items = rows.success_items(ENTITY)

    handoff = [item for item in items if item["variables"].get("action") == "handoff"]
    assert len(handoff) == 1
    assert handoff[0]["arg"] == "/root/A11.12_podiatrist"


def test_the_success_surface_offers_every_mirror_synced_or_not():
    """*four rows always, so an unsynced mirror can say why nothing happened*"""
    items = rows.success_items(ENTITY)

    assert [item["title"] for item in items[2:]] == [
        "Open in 🗒️ Craft", "Not synced to ✅ Todoist",
        "Not synced to 📁 Drive", "Not synced to 🔗 Dropbox",
    ]


# ------------------------------------------------------- the argument step list

def test_an_empty_argument_step_shows_only_the_way_back():
    """*nothing has been typed, so there is nothing to confirm yet*"""
    items = rows.argument_items("", "Choose a different category")

    assert len(items) == 1
    assert items[0]["variables"]["action"] == "back"


def test_a_typed_argument_step_leads_with_the_parse():
    """
    *Return must mean "carry on", never "discard what I just typed"*

    The back row stays visible - it is an affordance that costs nothing
    when unused - but it stops being the default the moment there is
    something to lose.
    """
    items = rows.argument_items("Cardiologist, GP referrals", "Choose a different category")

    assert items[0]["subtitle"] == "title = «Cardiologist»  description = «GP referrals»"
    assert items[0]["variables"]["action"] == "confirm"
    assert items[0]["variables"]["title"] == "Cardiologist"
    assert items[0]["variables"]["description"] == "GP referrals"
    assert items[1]["variables"]["action"] == "back"


def test_the_argument_step_shows_no_code_and_no_folder_path():
    """*showing the JD code next to the title field invites typing the code into the title*"""
    items = rows.argument_items("Cardiologist", "Choose a different category")

    assert "A11" not in items[0]["subtitle"]
    assert "/" not in items[0]["subtitle"]


# ------------------------------------- a malformed contract is never a traceback

def test_a_missing_suggestions_array_is_the_same_as_an_empty_one():
    """*these cross a process boundary, so they validate rather than trust*"""
    items = rows.confirmation_items(PARSED, None)

    assert len(items) == 1
    assert items[0]["title"] == "Create as typed"


def test_a_malformed_suggestion_is_skipped_rather_than_raised():
    items = rows.confirmation_items(PARSED, [{"index": 0}, SUGGESTIONS[0]])

    assert [item["title"] for item in items] == [
        "Create as typed", "Use «Aardvark» instead of «Aadvark»",
    ]
