#!/usr/bin/env python
# encoding: utf-8
"""
*Parse the Alfred argument step's single free-text field*

The mutating flow takes both of a new entity's text fields in one
keystroke-cheap step: `title, description`, split on the **first comma
only**. Comma beat `::`, `/`, `—`, ` - ` and `>` against real titles -
it needs no shift key and, unlike the hyphen, does not collide with the
hyphens that appear in real titles ("Insurance - buildings and
contents").

The parse never guesses and never repairs. A title containing a comma
loses the fragment after the first one to the description, and a leading
comma leaves the title empty; both are shown as parsed and caught on the
confirmation screen before anything is written. That is what lets this
module stay a pure function over a string.

Author
: David Young
"""

import glob
import os

SEPARATOR = ","

# THE STEP SHOWS THE PARSE AND NOTHING ELSE - NO JD CODE, WHICH INVITES THE
# USER TO TYPE THE CODE INTO THE TITLE, AND NO FOLDER PATH.
_FIELD_TEMPLATE = "title = «{title}»  description = «{description}»"


def title_and_description(entry):
    """
    *split one argument-step entry into its title and description*

    **Key Arguments:**

    - ``entry`` -- the raw text of the argument step, or `None`

    **Return:**

    - ``parsed`` -- a new `{"title", "description"}` dict, each part stripped

    **Usage:**

    ```python
    from aardvark_jd.alfred import parse
    parsed = parse.title_and_description("Cardiologist, GP referrals")
    ```
    """
    title, _separator, description = (entry or "").partition(SEPARATOR)
    return {"title": title.strip(), "description": description.strip()}


def parse_subtitle(parsed):
    """
    *the two lines the argument step shows back, as one Alfred subtitle*

    An absent description still renders its field: the empty `«»` is
    what tells the user the comma was never typed.

    **Key Arguments:**

    - ``parsed`` -- a `title_and_description` result

    **Return:**

    - ``subtitle`` -- the rendered parse

    **Usage:**

    ```python
    from aardvark_jd.alfred import parse
    subtitle = parse.parse_subtitle(parse.title_and_description("Cardiologist"))
    ```
    """
    return _FIELD_TEMPLATE.format(
        title=parsed.get("title", ""), description=parsed.get("description", ""),
    )


def template_names(categoryFolderPath):
    """
    *the `*.zip` template basenames in a project category's reserved templates folder*

    `add_project`'s reference pick carries the category's folder path
    forward, so the template step finds the templates without a second
    shell-out or a `db` import. The reserved templates folder is the one
    `*templates*` child of the category folder (`P11.04_templates📐`).
    Mirrors `add_project`'s own `sorted(glob(...))` so the two agree on
    what is offered; a missing or empty folder is an empty list, exactly
    as `add_project` treats "no templates".

    **Key Arguments:**

    - ``categoryFolderPath`` -- the project category's folder path, or `""`

    **Return:**

    - ``names`` -- the sorted `*.zip` basenames

    **Usage:**

    ```python
    from aardvark_jd.alfred import parse
    names = parse.template_names(os.environ.get("folder_path", ""))
    ```
    """
    if not categoryFolderPath:
        return []
    return sorted(
        os.path.basename(path)
        for path in glob.glob(os.path.join(categoryFolderPath, "*templates*", "*.zip"))
    )
