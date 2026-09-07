#!/usr/bin/env python
"""
One-off builder: wire slice 3's five mutating flows into the Alfred
workflow's info.plist, following .scratch/alfred-workflow/map.md and the
code-architect blueprint.

Not shipped and not imported by anything. Kept on-branch so slice 4 can
extend the same shape rather than re-deriving it. Idempotent: it refuses
to run twice by checking for the router object.

    python .scratch/alfred-workflow/build_slice3_plist.py

Then: make alfred-normalise
"""

import plistlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLIST = REPO_ROOT / "aardvark_jd" / "resources" / "alfred" / "info.plist"
PREFIX = "6F1B0A54-1C1E-4C3B-9C0A-2B7F1D0E"


def obj(n):
    return f"{PREFIX}5A{n:02d}"


def cond(n):
    return f"{PREFIX}C{n:02d}"


def script_filter(uid, scriptfile, title, subtext, *, listmode, running=""):
    """A Script Filter object. listmode=True is profile L (Alfred filters a
    fetched list, script runs once); listmode=False is profile T (the
    script re-runs per keystroke)."""
    return {
        "config": {
            "alfredfiltersresults": listmode,
            "alfredfiltersresultsmatchmode": 2 if listmode else 0,
            "argumenttrimmode": 0,
            "argumenttype": 1 if listmode else 2,
            "escaping": 0,
            "keyword": "",
            "queuedelaycustom": 3,
            "queuedelayimmediatelyinitially": True,
            "queuedelaymode": 0,
            "queuemode": 1,
            "runningsubtext": running,
            "script": "",
            "scriptargtype": 1,
            "scriptfile": scriptfile,
            "subtext": subtext,
            "title": title,
            "type": 8,
            "withspace": False,
        },
        "type": "alfred.workflow.input.scriptfilter",
        "uid": uid,
        "version": 3,
    }


def run_script(uid, scriptfile):
    return {
        "config": {
            "concurrently": False,
            "escaping": 0,
            "script": "",
            "scriptargtype": 1,
            "scriptfile": scriptfile,
            "type": 8,
        },
        "type": "alfred.workflow.action.script",
        "uid": uid,
        "version": 2,
    }


def conditional(uid, tests, inputstring="{var:action}"):
    """tests is a list of (condition_uid, matchstring)."""
    return {
        "config": {
            "conditions": [
                {
                    "inputstring": inputstring,
                    "matchcasesensitive": False,
                    "matchmode": 0,
                    "matchstring": match,
                    "outputlabel": match,
                    "uid": cuid,
                }
                for cuid, match in tests
            ],
            "elselabel": "else",
            "hideelse": False,
        },
        "type": "alfred.workflow.utility.conditional",
        "uid": uid,
        "version": 1,
    }


def edge(dest, sourceoutputuid=None):
    entry = {
        "destinationuid": dest,
        "modifiers": 0,
        "modifiersubtext": "",
        "vitoclose": False,
    }
    if sourceoutputuid is not None:
        # ALFRED ORDERS sourceoutputuid BEFORE vitoclose; MATCH ITS KEY ORDER
        # SO THE NORMALISED FILE IS BYTE-STABLE AGAINST AN ALFRED SAVE.
        entry = {
            "destinationuid": dest,
            "modifiers": 0,
            "modifiersubtext": "",
            "sourceoutputuid": sourceoutputuid,
            "vitoclose": False,
        }
    return entry


REVEAL = obj(3)
HANDOFF = obj(4)
NOTIFY = obj(7)
ADD_ID_REFERENCE = obj(9)
TEACH = obj(15)
POST_SUCCESS = obj(17)

EMOJI_SUBTEXT = "↩ for the offline pick, or type an emoji or a word to search"

OBJECTS = []
CONNECTIONS = {}


def add(object_dict, edges):
    OBJECTS.append(object_dict)
    if edges:
        CONNECTIONS[object_dict["uid"]] = edges


# --------------------------------------------------------- the command router
# 5A08's "action == command" output currently points straight at
# add_id_reference (5A09). Repoint it here, then fan out by {var:command}.
add(
    conditional(
        obj(18),
        [
            (cond(7), "add_area"),
            (cond(8), "add_category"),
            (cond(9), "add_id"),
            (cond(10), "add_project"),
            (cond(11), "archive"),
            (cond(12), "set_emoji"),
        ],
        inputstring="{var:command}",
    ),
    [
        edge(obj(19), cond(7)),
        edge(obj(27), cond(8)),
        edge(ADD_ID_REFERENCE, cond(9)),
        edge(obj(35), cond(10)),
        edge(obj(43), cond(11)),
        edge(obj(48), cond(12)),
        edge(NOTIFY),
    ],
)

# --------------------------------------------------------- add_area (5A19-5A26)
add(script_filter(obj(19), "scripts/add_area_reference.sh", "Choose a domain",
                  "Areas, Resources or Projects — which domain is the new area in?",
                  listmode=True, running="Reading the index…"),
    [edge(obj(20))])
add(script_filter(obj(20), "scripts/add_area_arguments.sh", "Title and description",
                  "title, description — split on the first comma", listmode=False),
    [edge(obj(21))])
add(conditional(obj(21), [(cond(13), "back")]),
    [edge(obj(19), cond(13)), edge(obj(22))])
add(script_filter(obj(22), "scripts/add_area_emoji.sh", "Emoji", EMOJI_SUBTEXT, listmode=False),
    [edge(obj(23))])
add(script_filter(obj(23), "scripts/add_area_confirm.sh", "Confirm", "", listmode=False),
    [edge(obj(24))])
add(conditional(obj(24), [(cond(14), "recheck"), (cond(15), "teach")]),
    [edge(obj(23), cond(14)), edge(TEACH, cond(15)), edge(obj(25))])
add(run_script(obj(25), "scripts/add_area_create.sh"), [edge(obj(26))])
add(script_filter(obj(26), "scripts/add_area_success.sh", "Created", "", listmode=False),
    [edge(POST_SUCCESS)])

# ----------------------------------------------------- add_category (5A27-5A34)
add(script_filter(obj(27), "scripts/add_category_reference.sh", "Choose an area",
                  "Which area does the new category belong to?",
                  listmode=True, running="Reading the index…"),
    [edge(obj(28))])
add(script_filter(obj(28), "scripts/add_category_arguments.sh", "Title and description",
                  "title, description — split on the first comma", listmode=False),
    [edge(obj(29))])
add(conditional(obj(29), [(cond(16), "back")]),
    [edge(obj(27), cond(16)), edge(obj(30))])
add(script_filter(obj(30), "scripts/add_category_emoji.sh", "Emoji", EMOJI_SUBTEXT, listmode=False),
    [edge(obj(31))])
add(script_filter(obj(31), "scripts/add_category_confirm.sh", "Confirm", "", listmode=False),
    [edge(obj(32))])
add(conditional(obj(32), [(cond(17), "recheck"), (cond(18), "teach")]),
    [edge(obj(31), cond(17)), edge(TEACH, cond(18)), edge(obj(33))])
add(run_script(obj(33), "scripts/add_category_create.sh"), [edge(obj(34))])
add(script_filter(obj(34), "scripts/add_category_success.sh", "Created", "", listmode=False),
    [edge(POST_SUCCESS)])

# ------------------------------------------------------ add_project (5A35-5A42)
add(script_filter(obj(35), "scripts/add_project_reference.sh", "Choose a project category",
                  "Only categories in the projects domain",
                  listmode=True, running="Reading the index…"),
    [edge(obj(36))])
add(script_filter(obj(36), "scripts/add_project_template.sh", "Choose a template",
                  "The blank scaffold, or a zip from the category's 04_templates folder",
                  listmode=True),
    [edge(obj(37))])
add(script_filter(obj(37), "scripts/add_project_arguments.sh", "Project title",
                  "add_project takes a title and nothing else", listmode=False),
    [edge(obj(38))])
add(conditional(obj(38), [(cond(19), "back")]),
    [edge(obj(36), cond(19)), edge(obj(39))])
add(script_filter(obj(39), "scripts/add_project_confirm.sh", "Confirm", "", listmode=False),
    [edge(obj(40))])
add(conditional(obj(40), [(cond(20), "recheck"), (cond(21), "teach")]),
    [edge(obj(39), cond(20)), edge(TEACH, cond(21)), edge(obj(41))])
add(run_script(obj(41), "scripts/add_project_create.sh"), [edge(obj(42))])
add(script_filter(obj(42), "scripts/add_project_success.sh", "Created", "", listmode=False),
    [edge(POST_SUCCESS)])

# ---------------------------------------------------------- archive (5A43-5A47)
add(script_filter(obj(43), "scripts/archive_reference.sh", "Choose what to archive",
                  "Any area, category or ID",
                  listmode=True, running="Reading the index…"),
    [edge(obj(44))])
add(script_filter(obj(44), "scripts/archive_confirm.sh", "Confirm", "", listmode=False),
    [edge(obj(45))])
# ARCHIVE FREES A JOHNNY DECIMAL NUMBER IRREVERSIBLY, SO ITS CONFIRM SCREEN
# CARRIES A BACK ROW WHERE THE OTHER ONE-ROW CONFIRMS DO NOT.
add(conditional(obj(45), [(cond(22), "back")]),
    [edge(obj(43), cond(22)), edge(obj(46))])
add(run_script(obj(46), "scripts/archive_create.sh"), [edge(obj(47))])
add(script_filter(obj(47), "scripts/archive_success.sh", "Archived", "", listmode=False),
    [edge(POST_SUCCESS)])

# -------------------------------------------------------- set_emoji (5A48-5A52)
add(script_filter(obj(48), "scripts/set_emoji_reference.sh", "Choose what to re-emoji",
                  "Any area, category or ID",
                  listmode=True, running="Reading the index…"),
    [edge(obj(49))])
add(script_filter(obj(49), "scripts/set_emoji_emoji.sh", "Emoji", EMOJI_SUBTEXT, listmode=False),
    [edge(obj(50))])
add(script_filter(obj(50), "scripts/set_emoji_confirm.sh", "Confirm", "", listmode=False),
    [edge(obj(51))])
add(run_script(obj(51), "scripts/set_emoji_create.sh"), [edge(obj(52))])
add(script_filter(obj(52), "scripts/set_emoji_success.sh", "Renamed", "", listmode=False),
    [edge(POST_SUCCESS)])


def grid_positions():
    """A plain left-to-right grid. Dave re-lays-out the canvas in Alfred's
    editor before this ships; these are only so every object has a uidata
    entry and the graph is not stacked at the origin."""
    bands = {
        18: (540, 700),
    }
    flows = [
        range(19, 27), range(27, 35), range(35, 43), range(43, 48), range(48, 53),
    ]
    for row, flow in enumerate(flows):
        y = 700 + (row + 1) * 160
        for col, n in enumerate(flow):
            bands[n] = (780 + col * 220, y)
    return {obj(n): {"xpos": float(x), "ypos": float(y)} for n, (x, y) in bands.items()}


def main():
    data = plistlib.loads(PLIST.read_bytes())

    if any(entry["uid"] == obj(18) for entry in data["objects"]):
        print("router 5A18 already present - nothing to do")
        return 0

    # REPOINT 5A08's command output FROM add_id_reference TO THE ROUTER.
    rewired = False
    for entry in data["connections"][obj(8)]:
        if entry.get("sourceoutputuid") == cond(1) and entry["destinationuid"] == ADD_ID_REFERENCE:
            entry["destinationuid"] = obj(18)
            rewired = True
    if not rewired:
        print("could not find the 5A08 -> 5A09 command edge to repoint", file=sys.stderr)
        return 1

    data["objects"].extend(OBJECTS)
    data["connections"].update(CONNECTIONS)
    data["uidata"].update(grid_positions())

    data["objects"].sort(key=lambda entry: entry.get("uid", ""))
    PLIST.write_bytes(plistlib.dumps(data))
    print(f"added {len(OBJECTS)} objects, {len(CONNECTIONS)} connection sources, "
          f"rewired the 5A08 command edge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
