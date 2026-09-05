#!/usr/bin/env python
# encoding: utf-8
"""
*The rows the mutating flow's own screens are built from*

Three surfaces live here, none of which is an entity list:

- the **back row** the argument step carries, because Alfred's Escape
  discards the run rather than stepping back
- the **confirmation screen**, where "Create as typed" is the first and
  default row and each suspect token sits beside it as its own row
- the **success surface**, built from the record the mutating result
  already returns

Detection itself stays in `spell_check`; what belongs here is only the
code that turns a suggestion into a row.

Author
: David Young
"""

from aardvark_jd import spell_check
from aardvark_jd.alfred import items, parse

CREATE_ROW_TITLE = "Create as typed"

# TEACHING THE LEARNED VOCABULARY NEEDS ITS OWN EXPLICIT MODIFIER, WHICH IS A
# DELIBERATE DIVERGENCE FROM THE CLI. THE TERMINAL TEACHES A WORD WHEN THE
# USER DECLINES A SUGGESTION; HERE DECLINING IS THE DEFAULT PATH, SO THAT RULE
# WOULD TEACH A WORD ON EVERY REFLEXIVE RETURN.
TEACH_MODIFIER = "cmd"


def back_row(title):
    """
    *the first row of a step that can be stepped back from*

    A row, not a key. Alfred's Escape discards the run rather than
    stepping back, and a chord hint in the subtitle would compete with
    the parse the same subtitle is showing. A row is visible without
    being read and costs nothing when unused.

    **Key Arguments:**

    - ``title`` -- what going back does, e.g. "Choose a different category"

    **Return:**

    - ``row`` -- the Alfred item dict

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    row = rows.back_row("Choose a different category")
    ```
    """
    return {
        "title": title,
        "subtitle": "",
        "arg": "",
        "valid": True,
        "variables": {"action": "back"},
    }


def argument_items(query, backLabel):
    """
    *the argument step: the parse of what has been typed, and the way back*

    The step shows the parse and nothing else - no Johnny Decimal code,
    which invites typing the code into the title, and no folder path.

    The back row leads only while the field is empty. Once anything has
    been typed the parse leads, because Return has to mean "carry on"
    and never "discard what I just typed"; the back row stays visible
    below it, which is the whole reason it is a row and not a chord.

    **Key Arguments:**

    - ``query`` -- the raw text of the argument field
    - ``backLabel`` -- what the back row says, e.g. "Choose a different category"

    **Return:**

    - ``items`` -- the Alfred item dicts

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    step = rows.argument_items(query, "Choose a different category")
    ```
    """
    back = back_row(backLabel)
    parsed = parse.title_and_description(query)
    if not parsed["title"] and not parsed["description"]:
        return [back]

    return [
        {
            "title": parsed["title"] or "(no title yet)",
            "subtitle": parse.parse_subtitle(parsed),
            "arg": parsed["title"],
            "valid": True,
            "variables": {
                "action": "confirm",
                "title": parsed["title"],
                "description": parsed["description"],
            },
        },
        back,
    ]


def confirmation_items(parsed, suggestions):
    """
    *the confirmation screen: what will be created, and every correction offered against it*

    The final Return of the argument step does not commit; this screen
    does. Accepting a correction **re-renders** the confirmation rather
    than committing, so Return always means create.

    **Key Arguments:**

    - ``parsed`` -- a `parse.title_and_description` result
    - ``suggestions`` -- the contract's `suggestions` array for that title, or `None`

    **Return:**

    - ``items`` -- the Alfred item dicts, "Create as typed" first

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    screen = rows.confirmation_items(parsed, result["suggestions"])
    ```
    """
    title = parsed.get("title", "")
    description = parsed.get("description", "")
    subtitle = parse.parse_subtitle(parsed)

    screen = [{
        "title": CREATE_ROW_TITLE,
        "subtitle": subtitle,
        "arg": title,
        "valid": True,
        "variables": {"action": "create", "title": title, "description": description},
    }]

    # THESE ARRIVE ACROSS A PROCESS BOUNDARY, SO THEY ARE VALIDATED RATHER
    # THAN TRUSTED: A MALFORMED ENTRY LOSES ITS ROW, NEVER THE WHOLE SCREEN.
    for suggestion in suggestions or []:
        if not suggestion.get("token") or not suggestion.get("suggested"):
            continue
        screen.append(_correction_row(title, description, suggestion))

    return screen


def _correction_row(title, description, suggestion):
    """
    *one suspect token, as a row that can be accepted on its own*

    Each is accepted independently and re-renders the screen, so a title
    carrying two typos is two Returns and one create, never a choice
    between them.

    **Key Arguments:**

    - ``title`` -- the title as it currently stands
    - ``description`` -- the description, carried through untouched
    - ``suggestion`` -- one `{token, index, suggested}` dict

    **Return:**

    - ``row`` -- the Alfred item dict
    """
    token = suggestion["token"]
    corrected = spell_check.substituted_title(title, token, suggestion["suggested"])
    # THE WORD AS IT WOULD LAND IN THE TITLE, NOT THE BARE DICTIONARY ENTRY:
    # WHAT THE ROW SHOWS AND WHAT ACCEPTING IT WRITES HAVE TO BE THE SAME.
    replacement = spell_check.cased_suggestion(token, suggestion["suggested"])

    return {
        "title": f"Use «{replacement}» instead of «{token}»",
        "subtitle": parse.parse_subtitle(
            {"title": corrected, "description": description},
        ),
        "arg": corrected,
        "valid": True,
        "variables": {
            "action": "recheck", "title": corrected, "description": description,
        },
        "mods": {
            TEACH_MODIFIER: {
                "subtitle": f"Teach aardvark that «{token}» is a word",
                "arg": token,
                "valid": True,
                "variables": {"action": "teach", "token": token},
            },
        },
    }


def success_items(entity):
    """
    *what to do with the thing that was just created*

    Required after every mutating flow, and not decoration: it is the
    whole of the recall story. The Script Filter's cached index is one
    invocation behind at this point, and this surface reaches the new
    entity without waiting for it.

    **Key Arguments:**

    - ``entity`` -- the `entity` record from the mutating result

    **Return:**

    - ``items`` -- reveal, handoff, then the four mirrors

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    surface = rows.success_items(result["entity"])
    ```
    """
    folderPath = entity.get("folder_path", "")
    label = f"{entity.get('code', '')}  {entity.get('title', '')}".strip()

    return [
        {
            "title": label,
            "subtitle": "Reveal in Finder",
            "arg": folderPath,
            "valid": True,
            "variables": {"action": "reveal"},
        },
        {
            "title": "Open a terminal tab here",
            "subtitle": folderPath,
            "arg": folderPath,
            "valid": True,
            "variables": {"action": "handoff"},
        },
        *items.destination_items(entity.get("urls") or {}, entity.get("title", "")),
    ]
