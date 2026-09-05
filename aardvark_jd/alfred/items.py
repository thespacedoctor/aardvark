#!/usr/bin/env python
# encoding: utf-8
"""
*Render the JSON contract as the `av` Script Filter's Alfred items*

The Script Filter runs **once**, with an empty query: Alfred is set to
filter the results itself, so this module ships the whole index and Alfred
matches against each item's `match` string client-side from then on. That
is why there is no branching on what the user typed anywhere below.

Pure by design - dicts in, dicts out, no I/O and no `db` import. The
workflow's latency budget depends on the second part: a bare
`import aardvark_jd.db` costs 460 ms, where shelling out to `aardvark fd
--json` returns the whole tree in 240 ms.

Author
: David Young
"""

import json
from pathlib import Path

from aardvark_jd import doc_links, json_output

# THE WORKFLOW'S OWN FALLBACK. THE CONTRACT DELIBERATELY LEAVES `emoji`
# BLANK RATHER THAN SUBSTITUTING ONE, SO THAT EACH SURFACE CAN CHOOSE.
FALLBACK_EMOJI = "📁"

# THE `cache` BLOCK ALFRED READS. `loosereload` SHOWS THE STALE CACHE
# IMMEDIATELY AND REFRESHES IN THE BACKGROUND, SO A FOLDER FROM A MUTATING
# COMMAND APPEARS ONE INVOCATION LATE AT WORST - ACCEPTED, BECAUSE THE
# POST-CREATE SUCCESS SURFACE COVERS THE GAP AT THE MOMENT IT MATTERS.
CACHE = {"seconds": 3600, "loosereload": True}

INSTALL_COMMAND = "aardvark install_alfred"

# THE MUTATING COMMANDS THAT HAVE A ROW, AS `(command, subtitle, extra match
# words)`. THEY SHARE THE ONE LIST WITH THE ENTITIES BECAUSE "ALFRED FILTERS
# RESULTS" RUNS THE SCRIPT FILTER ONCE, WITH AN EMPTY QUERY - THERE IS NO
# SECOND PASS TO ADD THEM IN. `fd`, `open` AND `cd` EARN NO ROWS: THEY ARE
# WHAT AN ENTITY ROW'S RETURN AND MODIFIERS ALREADY DO.
# ORDER FOLLOWS THE SPEC'S COMMAND INVENTORY. THE SYNC AND MAINTENANCE
# COMMANDS (`craft_sync`, ..., `repair_emoji`) JOIN THIS LIST IN SLICE 4.
_COMMANDS = (
    ("add_area", "Add a new Johnny Decimal area", "new area domain create"),
    ("add_category", "Add a new Johnny Decimal category to an area", "new category create"),
    ("add_id", "Add a new Johnny Decimal ID to a category", "new id add create"),
    ("add_project", "Create a new project in a project category", "new project create"),
    ("archive", "Retire an entity and free its number", "archive retire remove delete"),
    ("set_emoji", "Change an entity's emoji", "set emoji icon change"),
)

# THE `add_area` REFERENCE PICK IS A DOMAIN LETTER, NOT AN ENTITY: THERE IS
# NOTHING IN THE INDEX TO CHOOSE FROM. THE THREE DOMAINS AND THE LETTER EACH
# TAKES, IN THE ORDER `add_area`'S OWN HELP LISTS THEM.
_DOMAIN_LETTERS = (
    ("A", "Areas", "responsibilities you carry, with no end date"),
    ("R", "Resources", "reference material and topics of interest"),
    ("P", "Projects", "efforts with a defined end"),
)

# THE THREE JOHNNY DECIMAL ENTITY TYPES, FOR THE "ANY ENTITY" REFERENCE PICK
# `archive` AND `set_emoji` USE. SYSTEM FOLDERS ARE NOT IN THE CONTRACT AND
# SO ARE NEVER OFFERED HERE.
_ENTITY_TYPES = ("area", "category", "id")

# THE MIRRORS RETURN OPENS, IN THE ORDER `aardvark open` OPENS THEM.
# FINDER HAS ITS OWN MODIFIER AND DROPBOX IS ONLY IN THE SUB-LIST.
_OPENABLE_MIRRORS = (
    ("craft", doc_links.CRAFT_LABEL),
    ("todoist", doc_links.TODOIST_LABEL),
    ("drive", doc_links.DRIVE_LABEL),
)

# EVERY DESTINATION IN THE ⌃ SUB-LIST, WITH THE COMMAND THAT MINTS ITS
# LINKS. THERE IS NO `dropbox_sync` COMMAND - THE DROPBOX SHARE LINKS ARE
# MINTED BY THE CRAFT SYNC RUN.
_DESTINATIONS = (
    ("craft", doc_links.CRAFT_LABEL, "craft_sync"),
    ("todoist", doc_links.TODOIST_LABEL, "todoist_sync"),
    ("drive", doc_links.DRIVE_LABEL, "gdrive_sync"),
    ("dropbox", doc_links.DROPBOX_LABEL, "craft_sync"),
)

# WHICH SYNC A `not_synced` ERROR ROW SHOULD OFFER, BY THE MIRROR NAMED IN
# THE CLI'S OWN MESSAGE. CRAFT IS THE DEFAULT BECAUSE ITS CARRIER RUNS ALL
# THREE MIRRORS IN THE MANDATED ORDER.
_SYNC_FOR_MIRROR = {"craft": "craft_sync", "todoist": "todoist_sync", "drive": "gdrive_sync",
                    "google drive": "gdrive_sync", "dropbox": "craft_sync"}

# HOW EACH MIRROR IS NAMED BACK TO THE USER IN AN ERROR ROW.
_MIRROR_LABELS = {
    "craft": doc_links.CRAFT_LABEL,
    "todoist": doc_links.TODOIST_LABEL,
    "drive": doc_links.DRIVE_LABEL,
    "google drive": doc_links.DRIVE_LABEL,
    "dropbox": doc_links.DROPBOX_LABEL,
}


def _entity_title(entity):
    """
    *the display title of one entity row*

    **Key Arguments:**

    - ``entity`` -- one entity record from the contract

    **Return:**

    - ``title`` -- the `<emoji> <code> <title>` line
    """
    return f"{entity['emoji'] or FALLBACK_EMOJI} {entity['code']} {entity['title']}"


def _relative_path(folderPath, rootPath):
    """
    *a folder path shown relative to the system root, for the row's subtitle*

    **Key Arguments:**

    - ``folderPath`` -- the entity's absolute folder path
    - ``rootPath`` -- the system's root path, which may be `None`

    **Return:**

    - ``relativePath`` -- the path below the root, or the absolute path when it sits outside it
    """
    if not rootPath:
        return folderPath
    # A STRING PREFIX IS NOT ENOUGH: `/My Life (Old)/...` STARTS WITH
    # `/My Life` WITHOUT BEING INSIDE IT, AND WOULD OTHERWISE RENDER AS A
    # `../` PATH. `is_relative_to` COMPARES WHOLE PATH SEGMENTS.
    folder = Path(folderPath)
    if not folder.is_relative_to(rootPath):
        return folderPath
    return str(folder.relative_to(rootPath))


def _match_string(entity, rootPath):
    """
    *everything Alfred matches a query against for one entity*

    `match` **replaces** matching on the title rather than adding to it, so
    it has to carry the title too. Folding the description in costs about 7
    per cent of the payload and is deliberate - description search is
    wanted.

    **Key Arguments:**

    - ``entity`` -- one entity record from the contract
    - ``rootPath`` -- the system's root path

    **Return:**

    - ``match`` -- the space-joined match string
    """
    pathSegments = Path(_relative_path(entity["folder_path"], rootPath)).parts
    parts = [entity["code"], entity["title"], *pathSegments, entity["description"]]
    return " ".join(part for part in parts if part)


def entity_item(entity, rootPath):
    """
    *render one entity record as one Alfred item*

    **Key Arguments:**

    - ``entity`` -- one entity record from the contract
    - ``rootPath`` -- the system's root path, used to shorten the subtitle

    **Return:**

    - ``item`` -- the Alfred item dict

    **Usage:**

    ```python
    from aardvark_jd.alfred import items
    item = items.entity_item(record, "/Users/dave/My Life")
    ```
    """
    title = _entity_title(entity)
    return {
        "uid": entity["id"],
        "title": title,
        "subtitle": _relative_path(entity["folder_path"], rootPath),
        "match": _match_string(entity, rootPath),
        "arg": entity["folder_path"],
        # THE LEAN SHAPE: ONE `urls` OBJECT PER ITEM, AND NO `mods` CARRYING
        # DUPLICATE URLS. A MOD'S `variables` REPLACE THE ITEM'S WHOLESALE
        # WITH NO MERGE, SO THE FAT SHAPE REPEATS EVERY SHARED KEY IN EVERY
        # MOD FOR ABOUT 50 PER CENT MORE BYTES. ALFRED HOLDS THE WHOLE INDEX
        # IN MEMORY, SO A MODIFIER RESOLVING A URL FROM HERE IS A CACHE READ.
        "variables": {
            "urls": json.dumps(entity["urls"]),
            "entity_id": entity["id"],
            "entity_title": title,
        },
        # PERMANENT, NOT A PLACEHOLDER. ALFRED'S LEARNING IS KEYED ON THE
        # `uid` STRING AND `archive` FREES A JOHNNY DECIMAL NUMBER FOR
        # REUSE, SO A RECYCLED `A11.10` WOULD INHERIT ITS PREDECESSOR'S
        # RANK AND SURFACE IT CONFIDENTLY.
        "skipknowledge": True,
        "mods": {
            "cmd": {"subtitle": "Reveal the folder in Finder"},
            "alt": {"subtitle": "Open a terminal tab at the folder"},
            "ctrl": {"subtitle": "Craft, Todoist, Google Drive, Dropbox…"},
        },
    }


def _row(title, subtitle="", arg="", valid=False, variables=None):
    """
    *one plain Alfred row, for the surfaces that are not entity lists*

    **Key Arguments:**

    - ``title`` -- the row's title
    - ``subtitle`` -- the row's subtitle. Default `""`.
    - ``arg`` -- what Return hands the connected action. Default `""`.
    - ``valid`` -- whether Return actions the row at all. Default `False`.
    - ``variables`` -- the row's item variables. Default `None`.

    **Return:**

    - ``row`` -- the Alfred item dict
    """
    row = {"title": title, "subtitle": subtitle, "arg": arg, "valid": valid}
    if variables is not None:
        row["variables"] = variables
    return row


def _install_row(title, subtitle):
    """
    *an error row whose Return copies the install command to the clipboard*

    Copying rather than pre-typing into a terminal, which would resurrect
    the AppleScript the handoff decision removed. `install_alfred` is
    `ADVANCED` and so absent from `-h`, which is acceptable **only**
    because these rows hand over the exact string.

    **Key Arguments:**

    - ``title`` -- the diagnosis
    - ``subtitle`` -- what Return will do

    **Return:**

    - ``row`` -- the Alfred item dict
    """
    return _row(
        title, subtitle, arg=INSTALL_COMMAND, valid=True, variables={"action": "copy"},
    )


def error_row(error):
    """
    *render the contract's own error object as a single row*

    **Key Arguments:**

    - ``error`` -- the contract's `error` object, carrying `kind` and `message`

    **Return:**

    - ``row`` -- the Alfred item dict
    """
    message = error.get("message") or "aardvark reported an error"
    if error.get("kind") != "not_synced":
        return _row(message)

    # THE ONE ERROR KIND WITH AN OBVIOUS FIX: RUN THE SYNC THE ENTITY IS
    # WAITING ON. THE MIRROR IS NAMED IN THE CLI'S OWN MESSAGE, BUT THE ROW
    # SAYS IT IN THE WORKFLOW'S OWN WORDS - THE CLI'S SENTENCE IS WRITTEN
    # FOR A TERMINAL AND TELLS THE READER TO RUN THREE COMMANDS THIS ROW IS
    # ABOUT TO RUN FOR THEM.
    lowered = message.lower()
    mirrorName, syncCommand = next(
        (
            (mirror, command)
            for mirror, command in _SYNC_FOR_MIRROR.items()
            if mirror in lowered
        ),
        ("craft", "craft_sync"),
    )
    return _row(
        f"Not yet synced to {_MIRROR_LABELS.get(mirrorName, mirrorName)}",
        f"Press ↩ to run `aardvark {syncCommand}`",
        arg=f"sync:{syncCommand}",
        valid=True,
    )


def _contract_guard(contract):
    """
    *the one row to show instead of a step, when the contract itself is unusable*

    **Key Arguments:**

    - ``contract`` -- the parsed `aardvark fd --json` envelope

    **Return:**

    - ``payload`` -- a Script Filter response dict to return as-is, or `None` when the contract is fine
    """
    if contract.get("aardvark_json") != json_output.AARDVARK_JSON_VERSION:
        return {
            "items": [_install_row(
                "This workflow is out of step with the installed aardvark",
                f"Press ↩ to copy `{INSTALL_COMMAND}`, then run it in a terminal",
            )],
        }
    if contract.get("error"):
        return {"items": [error_row(contract["error"])]}
    return None


def reference_payload(contract, entityType, domain=None):
    """
    *the mutating flow's first step: the entities a command can target*

    A filtered view of the same `fd --json` envelope the main list is
    built from, so the pick costs one shell-out and no new contract.

    **Key Arguments:**

    - ``contract`` -- the parsed `aardvark fd --json` envelope
    - ``entityType`` -- the entity type to list (`area`, `category`, `id`), or `None` for any of the three (`archive`, `set_emoji`)
    - ``domain`` -- restrict to one domain, e.g. `projects` for `add_project`. Default `None`.

    **Return:**

    - ``payload`` -- the Script Filter response dict

    **Usage:**

    ```python
    from aardvark_jd.alfred import items
    payload = items.reference_payload(json.load(sys.stdin), "category")
    ```
    """
    guard = _contract_guard(contract)
    if guard is not None:
        return guard

    allowedTypes = {entityType} if entityType else set(_ENTITY_TYPES)
    # WITH NO SINGLE TYPE, THE PICK NAMES A `<ref>` (WHAT `archive` AND
    # `set_emoji` TAKE); WITH ONE, IT NAMES THAT COMMAND'S OWN POSITIONAL.
    variableKey = entityType or "ref"
    noun = entityType or "entity"

    rootPath = (contract.get("system") or {}).get("root_path")
    rows = []
    for entity in contract.get("entities") or []:
        if entity.get("type") not in allowedTypes:
            continue
        if domain is not None and entity.get("domain") != domain:
            continue
        code = entity.get("code", "")
        # BUILT FROM THE ENTITY ROW'S *PIECES*, NOT BY MERGING OVER THE WHOLE
        # ROW. A MERGE LEAVES `mods`, `uid` AND `skipknowledge` BEHIND, WHICH
        # WOULD OFFER "REVEAL THE FOLDER IN FINDER" ON A ROW WHOSE ONLY JOB
        # IS TO NAME A REFERENCE.
        rows.append({
            "title": _entity_title(entity),
            "subtitle": _relative_path(entity["folder_path"], rootPath),
            "match": _match_string(entity, rootPath),
            "arg": code,
            "valid": True,
            # `root_path` TRAVELS WITH THE PICK BECAUSE THE LATER STEPS NEED
            # IT AND MUST NOT FETCH THE WHOLE INDEX AGAIN TO GET IT.
            # `folder_path` DOES THE SAME FOR `add_project`, WHOSE TEMPLATE
            # STEP FINDS THE CATEGORY'S TEMPLATES FOLDER FROM IT; THE OTHER
            # COMMANDS IGNORE IT.
            "variables": {
                "action": "reference", variableKey: code,
                "root_path": rootPath or "", "folder_path": entity.get("folder_path", ""),
            },
        })

    if not rows:
        # A SCRIPT FILTER CANNOT RAISE, SO AN EMPTY LIST IS A ROW.
        return {"items": [_row(
            f"No {noun} to pick yet",
            f"Create {'a ' + noun if noun != 'entity' else 'one'} first",
        )]}

    return {"items": rows}


def domain_letter_payload(contract):
    """
    *`add_area`'s reference step: pick Areas, Resources or Projects*

    Unlike every other reference pick this lists nothing from the index -
    the three domains are fixed. It still takes the contract, only to read
    `system.root_path` for the steps that follow and to surface the same
    error row on a broken contract.

    **Key Arguments:**

    - ``contract`` -- the parsed `aardvark fd --json` envelope

    **Return:**

    - ``payload`` -- the Script Filter response dict

    **Usage:**

    ```python
    from aardvark_jd.alfred import items
    payload = items.domain_letter_payload(json.load(sys.stdin))
    ```
    """
    guard = _contract_guard(contract)
    if guard is not None:
        return guard

    rootPath = (contract.get("system") or {}).get("root_path")
    return {"items": [
        _row(
            f"{name}", subtitle, arg=letter, valid=True,
            variables={"action": "reference", "domainLetter": letter, "root_path": rootPath or ""},
        )
        for letter, name, subtitle in _DOMAIN_LETTERS
    ]}


def command_items():
    """
    *the rows that start a mutating flow, for the one list they share with the entities*

    A command row opens nothing. Its Return hands the flow's first step
    the command name, and the conditional on the way out tells a command
    row from an entity row by its `action` variable.

    **Return:**

    - ``rows`` -- one Alfred item dict per mutating command with a surface

    **Usage:**

    ```python
    from aardvark_jd.alfred import items
    rows = items.command_items()
    ```
    """
    return [
        _row(
            command, subtitle, arg=command, valid=True,
            variables={"action": "command", "command": command},
        ) | {"match": f"{command} {command.replace('_', ' ')} {matchWords}"}
        for command, subtitle, matchWords in _COMMANDS
    ]


def script_filter_payload(contract, workflowVersion=None):
    """
    *render a whole `fd --json` envelope as the Script Filter's response*

    **Key Arguments:**

    - ``contract`` -- the parsed `aardvark fd --json` envelope
    - ``workflowVersion`` -- the installed workflow's version, for the drift check. Default `None`.

    **Return:**

    - ``payload`` -- the Script Filter response dict, carrying `items` and `cache`

    **Usage:**

    ```python
    from aardvark_jd.alfred import items
    payload = items.script_filter_payload(json.load(sys.stdin), workflowVersion="1.2.3")
    ```
    """
    guard = _contract_guard(contract)
    if guard is not None:
        return guard

    system = contract.get("system") or {}
    rootPath = system.get("root_path")
    # THE ENTITIES LEAD. THEY ARE WHAT GETS TYPED TWENTY TIMES A DAY, AND
    # WITH AN EMPTY QUERY ALFRED SHOWS THIS ORDER VERBATIM; ONCE ANYTHING IS
    # TYPED ALFRED'S OWN MATCHING DECIDES, SO `av add` STILL FINDS `add_id`.
    rows = [
        entity_item(entity, rootPath) for entity in contract.get("entities") or []
    ] + command_items()

    # A WARNING, NEVER A BLOCKER: THE WORKFLOW STILL WORKS, IT IS JUST
    # OLDER OR NEWER THAN THE CLI IT IS DRIVING.
    packageVersion = system.get("version")
    if workflowVersion and packageVersion and workflowVersion != packageVersion:
        rows.insert(0, _row(
            "This workflow is out of step with the installed aardvark",
            f"workflow {workflowVersion}, aardvark {packageVersion} - re-run `{INSTALL_COMMAND}`",
        ))

    return {"items": rows, "cache": dict(CACHE)}


def mirror_urls_to_open(urls):
    """
    *the mirrors Return opens, in the order `aardvark open` opens them*

    **Key Arguments:**

    - ``urls`` -- one entity record's `urls` object

    **Return:**

    - ``openable`` -- an ordered list of `(label, url)` pairs, empty when the entity is synced to nothing

    **Usage:**

    ```python
    from aardvark_jd.alfred import items
    for label, url in items.mirror_urls_to_open(urls):
        ...
    ```
    """
    return [(label, urls.get(mirror)) for mirror, label in _OPENABLE_MIRRORS if urls.get(mirror)]


def destination_items(urls, entityTitle=""):
    """
    *the ⌃ sub-list: all four mirrors, synced or not*

    Always four rows. Showing an unsynced mirror and offering to sync it is
    the whole reason this is a sub-list rather than four modifier chords -
    an unbound chord cannot say why nothing happened.

    **Key Arguments:**

    - ``urls`` -- one entity record's `urls` object
    - ``entityTitle`` -- the entity's display title, shown in each subtitle. Default `""`.

    **Return:**

    - ``rows`` -- four Alfred item dicts, in the order Craft, Todoist, Google Drive, Dropbox
    """
    rows = []
    for mirror, label, syncCommand in _DESTINATIONS:
        url = urls.get(mirror)
        if url:
            rows.append(_row(
                f"Open in {label}", entityTitle or url, arg=url, valid=True,
                variables={"mirror": mirror},
            ))
        else:
            rows.append(_row(
                f"Not synced to {label}", f"Press ↩ to run `aardvark {syncCommand}`",
                arg=f"sync:{syncCommand}", valid=True, variables={"mirror": mirror},
            ))
    return rows
