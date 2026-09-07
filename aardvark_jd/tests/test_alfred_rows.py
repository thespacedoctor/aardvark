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


# ----------------------------------------- slice 3: the emoji step

def test_the_empty_emoji_step_offers_the_offline_pick_as_the_default():
    items = rows.emoji_items("", "📁")

    assert len(items) == 1
    assert items[0]["arg"] == "📁"
    assert items[0]["variables"] == {"action": "emoji", "emoji": "📁"}
    assert items[0]["valid"] is True


def test_a_typed_emoji_step_takes_what_was_typed_verbatim_first():
    items = rows.emoji_items("🚲", "📁")

    assert items[0]["arg"] == "🚲"
    assert items[0]["variables"]["emoji"] == "🚲"


def test_a_typed_emoji_step_appends_the_index_search_matches():
    items = rows.emoji_items("bike", "📁", searchResults=[("🚲", "bicycle"), ("🏍️", "motorcycle")])

    assert [item["arg"] for item in items] == ["bike", "🚲", "🏍️"]
    assert "bicycle" in items[1]["subtitle"]


# ----------------------------------------- slice 3: emoji on the confirmation

def test_the_confirmation_carries_the_chosen_emoji_into_the_create_variables():
    items = rows.confirmation_items(PARSED, [], emoji="🩺")

    assert items[0]["variables"]["emoji"] == "🩺"
    assert "🩺" in items[0]["subtitle"]


def test_a_correction_row_keeps_the_chosen_emoji_when_it_re_renders():
    correction = rows.confirmation_items(PARSED, SUGGESTIONS, emoji="🩺")[1]

    assert correction["variables"]["emoji"] == "🩺"


def test_the_confirmation_without_an_emoji_is_unchanged():
    assert rows.confirmation_items(PARSED, []) == rows.confirmation_items(PARSED, [], emoji=None)


# ----------------------------------------- slice 3: archive and set_emoji confirms

def test_archive_confirmation_commits_on_return_and_offers_a_way_back():
    items = rows.archive_confirm_items("A11.10", "A11.10  Cardiologist")

    assert items[0]["variables"]["action"] == "create"
    assert items[0]["variables"]["ref"] == "A11.10"
    assert "one-way" in items[0]["subtitle"] or "frees" in items[0]["subtitle"]
    # ARCHIVE FREES A JOHNNY DECIMAL NUMBER IRREVERSIBLY, SO A MIS-PICKED
    # TARGET MUST BE RECOVERABLE WITHOUT DISCARDING THE RUN.
    assert items[-1]["variables"]["action"] == "back"


def test_set_emoji_confirmation_carries_the_ref_and_the_new_emoji():
    items = rows.set_emoji_confirm_items("A10-19", "A10-19  Health", "🩺")

    assert len(items) == 1
    assert items[0]["variables"]["action"] == "create"
    assert items[0]["variables"]["ref"] == "A10-19"
    assert items[0]["variables"]["emoji"] == "🩺"
    assert "🩺" in items[0]["title"] or "🩺" in items[0]["subtitle"]


# ----------------------------------------- slice 3: the template pick

def test_the_template_pick_leads_with_the_blank_scaffold():
    items = rows.template_items(["site-v1.zip", "site-v2.zip"])

    assert items[0]["arg"] == "blank"
    assert [item["arg"] for item in items] == ["blank", "site-v1.zip", "site-v2.zip"]
    assert items[1]["variables"]["templateName"] == "site-v1.zip"


def test_the_template_pick_is_just_blank_when_there_are_no_zips():
    items = rows.template_items([])

    assert [item["arg"] for item in items] == ["blank"]


# ----------------------------------------- slice 3: the title-only step (add_project)

def test_the_empty_title_only_step_shows_only_the_way_back():
    items = rows.title_only_items("", "Choose a different template")

    assert len(items) == 1
    assert items[0]["variables"]["action"] == "back"


def test_a_typed_title_only_step_never_splits_on_a_comma():
    items = rows.title_only_items("Relaunch, the big one", "back")

    assert items[0]["variables"]["title"] == "Relaunch, the big one"
    assert items[0]["variables"]["description"] == ""
    assert items[0]["subtitle"] == "title = «Relaunch, the big one»"
    assert items[1]["variables"]["action"] == "back"


def test_the_title_only_confirmation_has_no_description_field():
    items = rows.confirmation_items({"title": "Relaunch"}, [], titleOnly=True)

    assert items[0]["subtitle"] == "title = «Relaunch»"
    assert "description" not in items[0]["variables"]


def test_a_title_only_correction_row_carries_no_description():
    row = rows.confirmation_items(
        {"title": "Aadvark"}, [{"token": "Aadvark", "index": 0, "suggested": "aardvark"}],
        titleOnly=True,
    )[1]

    assert row["variables"]["title"] == "Aardvark"
    assert "description" not in row["variables"]
