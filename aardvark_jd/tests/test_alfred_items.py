import json

import pytest

from aardvark_jd import json_output
from aardvark_jd.alfred import items

ROOT_PATH = "/Users/dave/My Life"


def _entity(**overrides):
    record = {
        "id": "areas:A11.10",
        "row_key": "42",
        "type": "id",
        "domain": "areas",
        "code": "A11.10",
        "title": "Cardiologist",
        "description": "heart people",
        "emoji": "",
        "folder_path": f"{ROOT_PATH}/03_AREAS/A11_doctors/A11.10_cardiologist",
        "archived": False,
        "urls": {
            "finder": "hook://file/abc?p=x&n=y",
            "craft": "https://craft.do/doc",
            "todoist": "https://todoist.com/project",
            "drive": "https://drive.google.com/folder",
            "dropbox": "https://dropbox.com/share",
        },
    }
    record.update(overrides)
    return record


def _contract(entities=None, **overrides):
    envelope = {
        "aardvark_json": json_output.AARDVARK_JSON_VERSION,
        "system": {
            "name": "My Life",
            "root_path": ROOT_PATH,
            "generated_at": "2026-09-05T09:00:00Z",
            "version": "1.2.3",
        },
        "entities": [_entity()] if entities is None else entities,
    }
    envelope.update(overrides)
    return envelope


def test_one_item_per_entity_in_the_contracts_own_order():
    # ARRANGE
    first = _entity(id="areas:A11.10", code="A11.10")
    second = _entity(id="areas:A11.11", code="A11.11")

    # ACT
    payload = items.script_filter_payload(_contract([first, second]))

    # ASSERT
    # THE COMMAND ROWS TRAIL THE ENTITIES AND CARRY NO `uid`.
    assert [
        item["uid"] for item in payload["items"] if "uid" in item
    ] == ["areas:A11.10", "areas:A11.11"]


def test_title_uses_the_workflows_own_fallback_when_the_emoji_is_blank():
    payload = items.script_filter_payload(_contract([_entity(emoji="")]))
    assert payload["items"][0]["title"] == f"{items.FALLBACK_EMOJI} A11.10 Cardiologist"


def test_title_uses_the_stored_emoji_when_there_is_one():
    payload = items.script_filter_payload(_contract([_entity(emoji="🩺")]))
    assert payload["items"][0]["title"] == "🩺 A11.10 Cardiologist"


def test_subtitle_is_the_folder_path_relative_to_the_system_root():
    payload = items.script_filter_payload(_contract())
    assert payload["items"][0]["subtitle"] == "03_AREAS/A11_doctors/A11.10_cardiologist"


def test_match_carries_the_code_title_path_segments_and_description():
    payload = items.script_filter_payload(_contract())
    match = payload["items"][0]["match"]
    assert "A11.10" in match
    assert "Cardiologist" in match
    assert "A11_doctors" in match
    assert "heart people" in match


def test_arg_is_the_folder_path():
    payload = items.script_filter_payload(_contract())
    assert payload["items"][0]["arg"] == _entity()["folder_path"]


def test_item_variables_carry_the_whole_urls_object_as_a_json_string():
    payload = items.script_filter_payload(_contract())
    variables = payload["items"][0]["variables"]
    assert json.loads(variables["urls"]) == _entity()["urls"]
    assert variables["entity_id"] == "areas:A11.10"
    assert variables["entity_title"] == "🩺 A11.10 Cardiologist".replace("🩺", items.FALLBACK_EMOJI)


def test_every_item_skips_alfreds_knowledge():
    """*archive frees a Johnny Decimal number for reuse, so a recycled uid would inherit its predecessor's rank*"""
    payload = items.script_filter_payload(_contract())
    assert payload["items"][0]["skipknowledge"] is True


def test_no_modifier_block_carries_variables_because_the_payload_is_lean():
    # a mod's variables replace the item's wholesale with no merge, so a fat
    # shape repeats the discriminator in every mod for about 50% more bytes.
    payload = items.script_filter_payload(_contract())
    for mod in payload["items"][0]["mods"].values():
        assert "variables" not in mod
        assert "arg" not in mod


def test_the_three_bound_modifiers_are_described_and_shift_is_left_alone():
    payload = items.script_filter_payload(_contract())
    mods = payload["items"][0]["mods"]
    assert set(mods) == {"cmd", "alt", "ctrl"}


def test_the_script_filter_caches_with_a_loose_reload():
    payload = items.script_filter_payload(_contract())
    assert payload["cache"] == {"seconds": 3600, "loosereload": True}


def test_a_version_mismatch_prepends_a_warning_row_and_keeps_the_entities():
    payload = items.script_filter_payload(_contract(), workflowVersion="0.9.0")
    assert "out of step" in payload["items"][0]["title"]
    assert "0.9.0" in payload["items"][0]["subtitle"]
    assert "1.2.3" in payload["items"][0]["subtitle"]
    assert payload["items"][1]["uid"] == "areas:A11.10"
    assert payload["items"][-1]["title"] == "set_emoji"


def test_a_matching_version_adds_no_warning_row():
    payload = items.script_filter_payload(_contract(), workflowVersion="1.2.3")
    assert not any("out of step" in item["title"] for item in payload["items"])
    assert payload["items"][0]["uid"] == "areas:A11.10"


def test_an_unrecognised_contract_version_is_one_actionable_error_row():
    payload = items.script_filter_payload(_contract(aardvark_json=99))
    assert len(payload["items"]) == 1
    row = payload["items"][0]
    assert row["arg"] == "aardvark install_alfred"
    assert row["variables"] == {"action": "copy"}
    assert row["valid"] is True


def test_an_error_contract_shows_the_clis_own_message_inertly():
    contract = {
        "aardvark_json": json_output.AARDVARK_JSON_VERSION,
        "error": {"kind": "no_system", "message": "no aardvark system found"},
    }
    payload = items.script_filter_payload(contract)
    assert len(payload["items"]) == 1
    assert payload["items"][0]["title"] == "no aardvark system found"
    assert payload["items"][0]["valid"] is False


def test_a_not_synced_error_offers_to_run_that_mirrors_sync():
    contract = {
        "aardvark_json": json_output.AARDVARK_JSON_VERSION,
        "error": {"kind": "not_synced", "message": "'Cardiologist' has not been synced to craft"},
    }
    payload = items.script_filter_payload(contract)
    assert payload["items"][0]["valid"] is True
    assert payload["items"][0]["arg"] == "sync:craft_sync"


def test_a_not_synced_row_says_it_in_the_workflows_own_words():
    """*the CLI's sentence is written for a terminal and names three commands this row runs for you*"""
    contract = {
        "aardvark_json": json_output.AARDVARK_JSON_VERSION,
        "error": {"kind": "not_synced", "message": "'Cardiologist' has not been synced to todoist"},
    }
    payload = items.script_filter_payload(contract)
    assert payload["items"][0]["title"].startswith("Not yet synced to")
    assert "Todoist" in payload["items"][0]["title"]
    assert payload["items"][0]["arg"] == "sync:todoist_sync"


def test_return_opens_craft_todoist_and_drive_in_the_clis_own_order():
    opened = items.mirror_urls_to_open(_entity()["urls"])
    assert [url for _label, url in opened] == [
        "https://craft.do/doc",
        "https://todoist.com/project",
        "https://drive.google.com/folder",
    ]


def test_return_never_opens_finder_or_dropbox():
    """*Finder has its own modifier and Dropbox is only in the sub-list, matching `aardvark open`*"""
    opened = items.mirror_urls_to_open(_entity()["urls"])
    assert "https://dropbox.com/share" not in [url for _label, url in opened]
    assert "hook://file/abc?p=x&n=y" not in [url for _label, url in opened]


def test_an_entity_synced_to_nothing_opens_nothing_rather_than_erroring():
    urls = {"finder": "hook://file/abc", "craft": None, "todoist": None, "drive": None, "dropbox": None}
    assert items.mirror_urls_to_open(urls) == []


def test_the_destinations_sub_list_always_shows_all_four_mirrors():
    urls = {"finder": None, "craft": None, "todoist": None, "drive": None, "dropbox": None}
    rows = items.destination_items(urls)
    assert len(rows) == 4


def test_a_synced_destination_row_opens_its_url():
    rows = items.destination_items(_entity()["urls"])
    assert rows[0]["arg"] == "https://craft.do/doc"
    assert rows[0]["valid"] is True


@pytest.mark.parametrize(
    "mirror, expectedCommand",
    [
        ("craft", "craft_sync"),
        ("todoist", "todoist_sync"),
        ("drive", "gdrive_sync"),
        # THERE IS NO `dropbox_sync` COMMAND - THE DROPBOX SHARE LINKS ARE
        # MINTED BY THE CRAFT SYNC RUN.
        ("dropbox", "craft_sync"),
    ],
)
def test_an_unsynced_destination_row_offers_that_mirrors_own_sync(mirror, expectedCommand):
    urls = dict.fromkeys(("finder", "craft", "todoist", "drive", "dropbox"))
    rows = {row["variables"]["mirror"]: row for row in items.destination_items(urls)}
    assert rows[mirror]["arg"] == f"sync:{expectedCommand}"
    assert rows[mirror]["valid"] is True
    assert "not synced" in rows[mirror]["title"].lower()


def test_building_items_never_mutates_the_contract_it_was_handed():
    contract = _contract()
    before = json.dumps(contract, sort_keys=True)
    items.script_filter_payload(contract, workflowVersion="0.0.1")
    assert json.dumps(contract, sort_keys=True) == before


def test_a_sibling_of_the_root_sharing_its_prefix_keeps_its_absolute_path():
    """*`/My Life (Old)` starts with `/My Life` without being inside it*"""
    sibling = f"{ROOT_PATH} (Old)/03_AREAS/A11.10_cardiologist"
    payload = items.script_filter_payload(_contract([_entity(folder_path=sibling)]))
    assert payload["items"][0]["subtitle"] == sibling


def test_a_folder_outside_the_root_entirely_keeps_its_absolute_path():
    payload = items.script_filter_payload(_contract([_entity(folder_path="/somewhere/else")]))
    assert payload["items"][0]["subtitle"] == "/somewhere/else"


# ------------------------------------------------------------- command rows

def test_the_command_rows_share_the_one_list_with_the_entities():
    """
    *"Alfred Filters Results" runs the Script Filter once, with an empty query*

    There is no second pass to add rows in, so a command row and an
    entity row have to be emitted together or not at all.
    """
    payload = items.script_filter_payload({
        "aardvark_json": 1,
        "system": {"root_path": "/root", "version": "0.3.1"},
        "entities": [],
    })

    assert [row["title"] for row in payload["items"]] == [
        "add_area", "add_category", "add_id", "add_project", "archive", "set_emoji",
    ]


def test_a_command_row_says_it_starts_a_flow_rather_than_opening_anything():
    payload = items.script_filter_payload({
        "aardvark_json": 1, "system": {"root_path": "/root"}, "entities": [],
    })
    row = payload["items"][0]

    assert row["valid"] is True
    assert row["variables"]["action"] == "command"
    assert row["variables"]["command"] == "add_area"


def test_a_command_row_matches_on_more_than_its_own_name():
    """*`av new` and `av id` both have to find it, since neither is its name*"""
    payload = items.script_filter_payload({
        "aardvark_json": 1, "system": {"root_path": "/root"}, "entities": [],
    })

    assert "new" in payload["items"][0]["match"]


def test_the_entities_come_before_the_command_rows():
    payload = items.script_filter_payload({
        "aardvark_json": 1,
        "system": {"root_path": "/root"},
        "entities": [{
            "id": "areas:A11.10", "code": "A11.10", "type": "id", "domain": "areas",
            "title": "Cardiologist", "description": "", "emoji": None,
            "folder_path": "/root/A11.10_cardiologist", "archived": False,
            "row_key": 1, "urls": {},
        }],
    })

    assert payload["items"][0]["title"] not in {
        "add_area", "add_category", "add_id", "add_project", "archive", "set_emoji",
    }
    assert payload["items"][-1]["title"] == "set_emoji"


# --------------------------------------------------------- the reference pick

def _mixedContract():
    return {
        "aardvark_json": json_output.AARDVARK_JSON_VERSION,
        "system": {"root_path": "/root", "version": "1.2.3"},
        "entities": [
            _entity(id="areas:A10-19", code="A10-19", type="area", title="Health"),
            _entity(id="areas:A11", code="A11", type="category", title="Doctors"),
            _entity(id="areas:A11.10", code="A11.10", type="id", title="Cardiologist"),
        ],
    }


def test_the_reference_pick_lists_only_the_valid_parents():
    """*`add_id` hangs an ID off a category, so an area or another ID is not a choice*"""
    payload = items.reference_payload(_mixedContract(), "category")

    assert [item["arg"] for item in payload["items"]] == ["A11"]


def test_the_reference_pick_hands_on_the_code_the_command_takes():
    payload = items.reference_payload(_mixedContract(), "category")

    assert payload["items"][0]["arg"] == "A11"
    assert payload["items"][0]["variables"]["category"] == "A11"


def test_the_reference_pick_says_so_when_there_is_nothing_to_pick():
    """*a script filter cannot raise, so an empty parent list is a row too*"""
    contract = _mixedContract()
    contract["entities"] = [_entity(type="area")]

    payload = items.reference_payload(contract, "category")

    assert len(payload["items"]) == 1
    assert payload["items"][0]["valid"] is False
    assert "category" in payload["items"][0]["title"]


def test_the_reference_pick_forwards_a_contract_error_untouched():
    contract = {
        "aardvark_json": json_output.AARDVARK_JSON_VERSION,
        "error": {"kind": "no_system", "message": "no aardvark system found"},
    }

    payload = items.reference_payload(contract, "category")

    assert payload["items"][0]["title"] == "no aardvark system found"
    assert payload["items"][0]["valid"] is False


def test_the_reference_pick_carries_the_root_path_forward():
    """
    *the later steps need it and must not shell out again to get it*

    The confirmation screen filters its suggestions through the learned
    vocabulary, which lives under the system root. Fetching the whole
    index a second time to learn one path would cost 240 ms per step.
    """
    payload = items.reference_payload(_mixedContract(), "category")

    assert payload["items"][0]["variables"]["root_path"] == "/root"


def test_a_reference_row_carries_no_leftovers_from_the_entity_list():
    """
    *a category pick is not an entity row, and must not inherit its keys*

    `mods` would offer "Reveal the folder in Finder" over a row whose
    only job is to name a parent; `uid` and `skipknowledge` belong to
    Alfred's learning on a different surface entirely.
    """
    row = items.reference_payload(_mixedContract(), "category")["items"][0]

    assert "mods" not in row
    assert "uid" not in row
    assert "skipknowledge" not in row


def test_a_reference_row_still_shows_and_matches_what_the_entity_row_does():
    row = items.reference_payload(_mixedContract(), "category")["items"][0]

    assert "A11" in row["title"] and "Doctors" in row["title"]
    assert "Doctors" in row["match"]


# ------------------------------------------- slice 3: more reference-pick shapes


def test_the_reference_pick_can_scope_to_one_domain():
    """*`add_project` hangs a project off a `projects` category, never an `areas` one*"""
    contract = _mixedContract()
    contract["entities"] = [
        _entity(id="areas:A11", code="A11", type="category", domain="areas", title="Doctors"),
        _entity(id="projects:P11", code="P11", type="category", domain="projects", title="Website"),
    ]

    payload = items.reference_payload(contract, "category", domain="projects")

    assert [item["arg"] for item in payload["items"]] == ["P11"]


def test_the_reference_pick_can_take_any_entity_type():
    """*`archive` and `set_emoji` target an area, a category or an ID alike*"""
    payload = items.reference_payload(_mixedContract(), None)

    assert [item["arg"] for item in payload["items"]] == ["A10-19", "A11", "A11.10"]


def test_the_any_entity_reference_pick_carries_a_ref_variable():
    payload = items.reference_payload(_mixedContract(), None)

    assert payload["items"][0]["variables"]["ref"] == "A10-19"
    assert payload["items"][0]["variables"]["root_path"] == "/root"


def test_a_reference_row_carries_the_entity_title_forward():
    """
    *`archive` and `set_emoji` name the entity on their confirmation screen*

    Without it their confirm screen reads "Archive A11.10" with no title,
    on the one screen where naming the thing being destroyed matters most,
    and `set_emoji`'s emoji step loses its `pick_emoji` seed.
    """
    rows = items.reference_payload(_mixedContract(), None)["items"]
    row = next(r for r in rows if r["arg"] == "A11.10")

    assert row["variables"]["entity_title"] == row["title"]
    assert "A11.10" in row["variables"]["entity_title"]
    assert "Cardiologist" in row["variables"]["entity_title"]


# --------------------------------------------- the domain-letter reference pick


def test_the_domain_letter_pick_offers_areas_resources_and_projects():
    payload = items.domain_letter_payload(_contract(entities=[]))

    assert [item["arg"] for item in payload["items"]] == ["A", "R", "P"]
    assert "Areas" in payload["items"][0]["title"]


def test_the_domain_letter_pick_carries_the_letter_and_the_root_path():
    payload = items.domain_letter_payload(_contract(entities=[]))
    row = payload["items"][0]

    assert row["variables"]["domainLetter"] == "A"
    assert row["variables"]["root_path"] == ROOT_PATH
    assert row["variables"]["action"] == "reference"
    assert row["valid"] is True


def test_the_domain_letter_pick_forwards_a_contract_error():
    contract = {
        "aardvark_json": json_output.AARDVARK_JSON_VERSION,
        "error": {"kind": "no_system", "message": "no aardvark system found"},
    }

    payload = items.domain_letter_payload(contract)

    assert payload["items"][0]["title"] == "no aardvark system found"
    assert payload["items"][0]["valid"] is False


def test_the_domain_letter_pick_carries_no_entity_leftovers():
    row = items.domain_letter_payload(_contract(entities=[]))["items"][0]

    assert "mods" not in row and "uid" not in row and "skipknowledge" not in row
