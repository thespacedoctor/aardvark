#!/usr/bin/env python
# encoding: utf-8
"""
*Pick an appropriate emoji for a folder name from its title/description*

Author
: David Young
"""

import re
import sys

import emoji

FALLBACK_EMOJI = "📁"

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at",
    "with", "my", "our", "your",
}

_keywordIndex = None


def _build_keyword_index():
    """
    *build a keyword -> emoji lookup from `emoji.EMOJI_DATA`'s CLDR short names*

    Only fully-qualified emoji are indexed (skips skin-tone/component
    modifiers), and the first emoji seen for a given keyword wins, so
    shorter/more canonical entries (which sort first in `EMOJI_DATA`)
    take priority over obscure variants.

    **Return:**

    - ``keywordIndex`` -- a dict mapping lowercase keyword -> emoji character
    """
    keywordIndex = {}
    for character, data in emoji.EMOJI_DATA.items():
        if data.get("status") != emoji.STATUS["fully_qualified"]:
            continue
        names = [data.get("en", "")] + data.get("alias", [])
        for name in names:
            for keyword in name.strip(":").split("_"):
                keyword = keyword.lower()
                if keyword and keyword not in keywordIndex:
                    keywordIndex[keyword] = character
    return keywordIndex


def _get_keyword_index():
    """
    *lazily build and cache the keyword -> emoji index*

    **Return:**

    - ``keywordIndex`` -- the cached keyword -> emoji index
    """
    global _keywordIndex
    if _keywordIndex is None:
        _keywordIndex = _build_keyword_index()
    return _keywordIndex


def _tokenise(text):
    """
    *split free text into lowercase, stopword-free keyword tokens*

    **Key Arguments:**

    - ``text`` -- the free text to tokenise

    **Return:**

    - ``tokens`` -- a list of lowercase keyword tokens
    """
    words = re.findall(r"[A-Za-z]+", text.lower())
    return [word for word in words if word not in _STOPWORDS]


def _singular_forms(word):
    """
    *candidate singular spellings for a word, most-specific rule first*

    The CLDR short names behind the keyword index are singular, so plural
    titles ("Films", "Templates") miss an otherwise-available emoji. Exact
    matches are always tried before these candidates, so this only ever
    adds coverage.

    **Key Arguments:**

    - ``word`` -- the lowercase word to singularise

    **Return:**

    - ``candidates`` -- a list of candidate singular spellings
    """
    candidates = []
    if len(word) > 4 and word.endswith("ies"):
        candidates.append(word[:-3] + "y")
    if len(word) > 3 and word.endswith("es"):
        candidates.append(word[:-2])
    if len(word) > 2 and word.endswith("s") and not word.endswith("ss"):
        candidates.append(word[:-1])
    return candidates


def pick_emoji(title, description=""):
    """
    *pick an appropriate emoji for a folder from its title and description, offline*

    Looks up each word of ``title`` in turn against the `emoji` package's
    keyword index (trying the word as written before its singular forms),
    then falls back to ``description`` if nothing in the title matched, and
    finally to :py:data:`FALLBACK_EMOJI`.

    This is the offline pick that :py:func:`resolve_emoji` shows as the default.

    **Key Arguments:**

    - ``title`` -- the folder's title
    - ``description`` -- the folder's description. Default `""`.

    **Return:**

    - ``pickedEmoji`` -- the picked emoji character

    **Usage:**

    ```python
    from aardvark_jd import emoji_picker
    pickedEmoji = emoji_picker.pick_emoji("Hospital", "Appointments and visits")
    ```
    """
    keywordIndex = _get_keyword_index()

    for text in (title, description):
        for token in _tokenise(text or ""):
            for candidate in [token] + _singular_forms(token):
                if candidate in keywordIndex:
                    return keywordIndex[candidate]

    return FALLBACK_EMOJI


def resolve_emoji(title, description="", chosenEmoji=None):
    """
    *settle on the emoji for a new folder, from an explicit choice, a prompt, or the offline pick*

    Resolution order:

    1. ``chosenEmoji`` given (the `--emoji` flag) - used verbatim, with no prompt
    2. an interactive session - the offline pick is shown for the user to accept or replace
    3. a non-interactive session - the offline pick is accepted silently

    **Key Arguments:**

    - ``title`` -- the folder's title
    - ``description`` -- the folder's description. Default `""`.
    - ``chosenEmoji`` -- an emoji supplied on the command-line. Default `None`.

    **Return:**

    - ``resolvedEmoji`` -- the emoji to append to the folder name

    **Usage:**

    ```python
    from aardvark_jd import emoji_picker
    resolvedEmoji = emoji_picker.resolve_emoji("Doctors", "GP and specialists", chosenEmoji="🩺")
    ```
    """
    if chosenEmoji:
        return validate_chosen_emoji(chosenEmoji)

    pickedEmoji = pick_emoji(title, description)

    if not sys.stdin.isatty():
        return pickedEmoji

    print(f"Suggested emoji for '{title}': {pickedEmoji}")
    while True:
        reply = input("Press Enter to accept, or type a replacement emoji: ").strip()
        if not reply:
            return pickedEmoji
        try:
            return validate_chosen_emoji(reply)
        except ValueError as error:
            print(f"  {error}")


def resolve_emoji_with_source(title, description="", chosenEmoji=None):
    """
    *`resolve_emoji`, plus where the emoji came from, for the JSON contract*

    The mutating result's `emoji_source` field. Two values reach it from
    the CLI:

    - ``chosen`` -- an emoji was supplied: the `--emoji` flag on the
      terminal, or the emoji Alfred's own emoji step settled on
    - ``offline`` -- the offline keyword pick stood, the bare `📁`
      fallback included

    A third value, ``deferred`` (a folder created with no emoji, to be set
    later with `set_emoji`), is reserved but never produced here: every
    `add_*`/`set_emoji` run resolves to some emoji. The source is only
    read back through `--json`, which never prompts, so the interactive
    branch of `resolve_emoji` - where a user could type a replacement over
    the offline pick - is not a case this has to label.

    **Key Arguments:**

    - ``title`` -- the folder's title
    - ``description`` -- the folder's description. Default `""`.
    - ``chosenEmoji`` -- an emoji supplied on the command-line. Default `None`.

    **Return:**

    - ``resolvedEmoji`` -- the emoji to append to the folder name
    - ``source`` -- `"chosen"` or `"offline"`

    **Usage:**

    ```python
    from aardvark_jd import emoji_picker
    resolvedEmoji, source = emoji_picker.resolve_emoji_with_source("Doctors", "GP")
    ```
    """
    source = "chosen" if chosenEmoji else "offline"
    return resolve_emoji(title, description, chosenEmoji=chosenEmoji), source


def validate_chosen_emoji(chosenEmoji):
    """
    *check a user-supplied emoji is usable in a folder name*

    Deliberately permissive about what counts as an emoji - a user who
    wants a plain symbol should get one - but rejects the characters that
    would break or redirect folder creation.

    **Key Arguments:**

    - ``chosenEmoji`` -- the emoji supplied by the user

    **Return:**

    - ``chosenEmoji`` -- the validated emoji, stripped of surrounding whitespace
    """
    candidate = (chosenEmoji or "").strip()
    if not candidate:
        raise ValueError("an emoji is required")
    for illegal in ("/", "\\", "\n", "\r", "\0"):
        if illegal in candidate:
            raise ValueError(f"'{candidate}' cannot be used in a folder name")
    return candidate
