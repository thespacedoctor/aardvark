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
