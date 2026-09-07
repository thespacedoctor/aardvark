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


def title_only_items(query, backLabel):
    """
    *the argument step for a command that takes a title and nothing else*

    `add_project`'s docopt line is `<category> <projectTitle>` - one
    positional, no description - so its step is a plain title field with
    no comma split. The back row behaves exactly as in `argument_items`:
    it leads while the field is empty and steps aside once there is
    something to lose.

    **Key Arguments:**

    - ``query`` -- the raw text of the title field
    - ``backLabel`` -- what the back row says, e.g. "Choose a different template"

    **Return:**

    - ``items`` -- the Alfred item dicts

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    step = rows.title_only_items(query, "Choose a different template")
    ```
    """
    back = back_row(backLabel)
    title = (query or "").strip()
    if not title:
        return [back]

    return [
        {
            "title": title,
            "subtitle": f"title = «{title}»",
            "arg": title,
            "valid": True,
            "variables": {"action": "confirm", "title": title, "description": ""},
        },
        back,
    ]


def _emoji_suffix(emoji):
    """*the ` emoji = «…»` a confirmation subtitle carries when an emoji was chosen, else empty*"""
    return f"  emoji = «{emoji}»" if emoji else ""


def _confirm_subtitle(title, description, emoji, titleOnly):
    """*the confirmation row's subtitle: the parse, plus the emoji when one was chosen*"""
    if titleOnly:
        return f"title = «{title}»" + _emoji_suffix(emoji)
    return parse.parse_subtitle(
        {"title": title, "description": description},
    ) + _emoji_suffix(emoji)


def confirmation_items(parsed, suggestions, emoji=None, titleOnly=False):
    """
    *the confirmation screen: what will be created, and every correction offered against it*

    The final Return of the argument step does not commit; this screen
    does. Accepting a correction **re-renders** the confirmation rather
    than committing, so Return always means create.

    **Key Arguments:**

    - ``parsed`` -- a `parse.title_and_description` result
    - ``suggestions`` -- the contract's `suggestions` array for that title, or `None`
    - ``emoji`` -- the emoji settled on the emoji step, for `add_area` and `add_category`. Default `None`, for the commands with no emoji step.
    - ``titleOnly`` -- drop the description field, for `add_project`, whose docopt line takes only a title. Default `False`.

    **Return:**

    - ``items`` -- the Alfred item dicts, "Create as typed" first

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    screen = rows.confirmation_items(parsed, result["suggestions"])
    ```
    """
    title = parsed.get("title", "")
    description = "" if titleOnly else parsed.get("description", "")
    subtitle = _confirm_subtitle(title, description, emoji, titleOnly)

    createVariables = {"action": "create", "title": title}
    if not titleOnly:
        createVariables["description"] = description
    if emoji:
        createVariables["emoji"] = emoji

    screen = [{
        "title": CREATE_ROW_TITLE,
        "subtitle": subtitle,
        "arg": title,
        "valid": True,
        "variables": createVariables,
    }]

    # THESE ARRIVE ACROSS A PROCESS BOUNDARY, SO THEY ARE VALIDATED RATHER
    # THAN TRUSTED: A MALFORMED ENTRY LOSES ITS ROW, NEVER THE WHOLE SCREEN.
    for suggestion in suggestions or []:
        if not suggestion.get("token") or not suggestion.get("suggested"):
            continue
        screen.append(_correction_row(title, description, suggestion, emoji, titleOnly))

    return screen


def _correction_row(title, description, suggestion, emoji=None, titleOnly=False):
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

    recheckVariables = {"action": "recheck", "title": corrected}
    if not titleOnly:
        recheckVariables["description"] = description
    if emoji:
        # THE EMOJI STEP RAN BEFORE THIS SCREEN, SO A CORRECTION THAT
        # RE-RENDERS IT MUST NOT DROP THE EMOJI ALREADY SETTLED ON.
        recheckVariables["emoji"] = emoji

    return {
        "title": f"Use «{replacement}» instead of «{token}»",
        "subtitle": _confirm_subtitle(corrected, description, emoji, titleOnly),
        "arg": corrected,
        "valid": True,
        "variables": recheckVariables,
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


def _emoji_row(emoji, subtitle):
    """*one row of the emoji step: pick this emoji*"""
    return {
        "title": emoji,
        "subtitle": subtitle,
        "arg": emoji,
        "valid": True,
        "variables": {"action": "emoji", "emoji": emoji},
    }


def emoji_items(query, defaultEmoji, searchResults=None):
    """
    *the emoji step: the offline pick as the default, and a free-text search over the emoji index*

    Only `add_area`, `add_category` and `set_emoji` reach this step - IDs
    are never emoji-suffixed. `emoji_picker.pick_emoji` returns the bare
    `📁` fallback for most area- and category-style titles, so the manual
    path carries the real load and is kept prominent: type anything and
    the first row uses it verbatim (an emoji pasted straight in, or a word
    to search), with the index matches below it.

    **Key Arguments:**

    - ``query`` -- the raw text of the emoji field
    - ``defaultEmoji`` -- `emoji_picker.pick_emoji`'s offline result
    - ``searchResults`` -- `(emoji, keyword)` pairs from `emoji_picker.search_emoji`, for a non-empty query. Default `None`.

    **Return:**

    - ``items`` -- the Alfred item dicts

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    step = rows.emoji_items(query, "📁", emoji_picker.search_emoji(query))
    ```
    """
    query = (query or "").strip()
    if not query:
        return [_emoji_row(
            defaultEmoji, "the offline pick - ↩ to use it, or type an emoji or a word to search",
        )]

    step = [_emoji_row(query, "use exactly what you typed")]
    for emoji, keyword in searchResults or []:
        step.append(_emoji_row(emoji, f"match for «{keyword}»"))
    return step


def _action_confirm_row(title, subtitle, variables):
    """
    *the single row a confirmation screen with no title entry is: one Return commits*

    `archive` and `set_emoji` take a reference and, at most, one more
    value - there is nothing to parse, so their confirmation is one row
    rather than the `confirmation_items` title/description shape.

    **Key Arguments:**

    - ``title`` -- what the row says will happen
    - ``subtitle`` -- the consequence, spelled out
    - ``variables`` -- carried onto the run; `action` is forced to `create`

    **Return:**

    - ``items`` -- a one-item list
    """
    return [{
        "title": title,
        "subtitle": subtitle,
        "arg": variables.get("ref", ""),
        "valid": True,
        "variables": {**variables, "action": "create"},
    }]


def archive_confirm_items(ref, label):
    """
    *`archive`'s confirmation screen: commit on Return, or step back to the pick*

    Archiving frees a Johnny Decimal number irreversibly, so unlike the
    other one-row confirmations this one carries a back row: a mis-picked
    target has to be recoverable without discarding the run, and Alfred's
    Escape discards it.

    **Key Arguments:**

    - ``ref`` -- the Johnny Decimal reference being archived
    - ``label`` -- the entity's `<code>  <title>` line, for the row

    **Return:**

    - ``items`` -- the commit row, then the way back
    """
    return _action_confirm_row(
        f"Archive {label}",
        "moves the folder to the nearest archive and frees its number - this is one-way",
        {"ref": ref},
    ) + [back_row("Choose something else to archive")]


def set_emoji_confirm_items(ref, label, emoji):
    """
    *`set_emoji`'s confirmation screen: one row carrying the ref and the new emoji*

    **Key Arguments:**

    - ``ref`` -- the reference whose emoji is changing
    - ``label`` -- the entity's `<code>  <title>` line
    - ``emoji`` -- the emoji settled on the emoji step

    **Return:**

    - ``items`` -- a one-item list
    """
    return _action_confirm_row(
        f"Set {label} to {emoji}",
        "renames the folder to carry the new emoji and repoints the index",
        {"ref": ref, "emoji": emoji},
    )


def template_items(templateNames):
    """
    *`add_project`'s template step: the blank scaffold first, then each `04_templates` zip*

    A plain list step before the title field. The blank scaffold is
    always the first row; the category's own template zips follow in the
    order the directory listing gave them.

    **Key Arguments:**

    - ``templateNames`` -- the `*.zip` basenames in the category's `04_templates` folder

    **Return:**

    - ``items`` -- the Alfred item dicts, blank first

    **Usage:**

    ```python
    from aardvark_jd.alfred import rows
    step = rows.template_items(parse.template_names(templatesPath))
    ```
    """
    step = [{
        "title": "Blank project",
        "subtitle": "README.md, input/, output/",
        "arg": "blank",
        "valid": True,
        "variables": {"action": "template", "templateName": "blank"},
    }]
    for name in templateNames:
        step.append({
            "title": name,
            "subtitle": "unzip this template into the new project folder",
            "arg": name,
            "valid": True,
            "variables": {"action": "template", "templateName": name},
        })
    return step
