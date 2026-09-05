#!/usr/bin/env python
# encoding: utf-8
"""
*Offer to correct a typo in a new folder's title, before anything is created*

The check runs **before** the entity exists, in the same `get()` that
resolves the emoji and ahead of the emoji prompt - accepting a correction
changes the title the emoji is derived from. Checking first is what
designs the hard case out entirely: the corrected title is the single
value the folder name, the index row and all three mirrors are built
from, so there is no post-creation rename and no mirror repoint.

It **offers**; it never blocks and never silently rewrites. That is not
politeness, it is arithmetic - most of what it flags is a proper noun,
not a typo, so a checker that corrected without asking would corrupt
titles routinely.

Three rates, each with its denominator, because they have been confused
for one another before:

- **4.3 per cent of titles** fire, measured on 141 real human-typed
  titles under this tuning. Ticket 08 measured 1.4 per cent under the
  old floor of six.
- **1.5 per cent of tokens** on those same live titles.
- **18 per cent of tokens** on a synthetic technical vocabulary. That
  figure is a stress test, not what a real tree does, and it is the one
  previously quoted here without its denominator.

Two rules do most of the work of keeping the false-alarm rate down, and
they matter far more than which wordlist ships (across nine SCOWL sizes
the false-positive count moved by one under the right tokeniser, and by
21 under a naive one):

- check only tokens of **five characters or more**, split on `[_\\-\\s.]`
- offer only when a **distance-1 dictionary word actually exists**

The floor is a trade, not a free win: it also decides what is checked at
all, and at six it made dropped letters - the commonest typo class -
structurally undetectable in the six- and seven-character words that
dominate real titles.

Distance 2 was measured and rejected: 49 per cent false positives and 850
times the runtime, to recover four typos in thirty-four.

The wordlist is the ESDB/SCOWL `en_GB-ise` size-60 list, shipped in
`resources/wordlists/` with its copyright notice. It is a plain list read
into a `frozenset` (+12.3 ms) rather than a spell-checking library
because `spylls` costs 402 ms to load and `symspellpy` 1,212 ms to index,
against a 500 ms budget for the whole command.

Author
: David Young
"""

import os
import re
import sys

from aardvark_jd import vocabulary

_WORDLIST_PATH = os.path.join(
    os.path.dirname(__file__), "resources", "wordlists", "en_GB-ise.txt",
)

# SHORT TOKENS ARE WHERE THE FALSE POSITIVES LIVE - EVERY THREE-LETTER
# FRAGMENT IS ONE EDIT FROM SOME DICTIONARY WORD - BUT THE FLOOR ALSO DECIDES
# WHAT IS CHECKED AT ALL, AND AT SIX IT MADE THE COMMONEST TYPO CLASS
# INVISIBLE: DROPPING A LETTER FROM A SIX-CHARACTER WORD LEAVES FIVE, SO
# `sysem`, `famil` AND `acive` WERE NEVER CHECKED. FIVE COSTS FOUR MORE
# SUSPECT TOKENS ACROSS 141 REAL TITLES, ALL PROPER NOUNS THE LEARNED
# VOCABULARY RETIRES AT ONE DISMISSAL EACH. FOUR IS REJECTED ON ITS OWN
# NUMBERS: THE SAME RECALL, AND 12.8 PER CENT OF TITLES FIRING.
MINIMUM_TOKEN_LENGTH = 5

_TOKEN_SEPARATORS = re.compile(r"[_\-\s.]+")
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"

_words = None


def _load_words():
    """
    *the shipped `en_GB` wordlist, as a `frozenset`, loaded once per process*

    A missing or unreadable wordlist disables the feature rather than
    breaking the command.

    **Return:**

    - ``words`` -- the dictionary, possibly empty
    """
    global _words
    if _words is None:
        try:
            with open(_WORDLIST_PATH, encoding="utf-8") as stream:
                _words = frozenset(
                    stripped for stripped in (line.strip() for line in stream) if stripped
                )
        except (OSError, UnicodeDecodeError):
            _words = frozenset()
    return _words


def enabled(settings):
    """
    *is spell-checking switched on?*

    The clean "always off" exit for someone who creates many folders full
    of fresh proper nouns, where self-silencing on recurring jargon does
    not help.

    **Key Arguments:**

    - ``settings`` -- the aardvark settings dict

    **Return:**

    - ``enabled`` -- `True` unless `spell_check.enabled` is explicitly false
    """
    spellSettings = (settings or {}).get("spell_check")
    if not isinstance(spellSettings, dict):
        return True
    return bool(spellSettings.get("enabled", True))


def tokenise(title):
    """
    *split a title into the tokens worth checking*

    **Key Arguments:**

    - ``title`` -- the folder title as typed

    **Return:**

    - ``tokens`` -- the original-case tokens long enough and alphabetic enough to check
    """
    tokens = []
    for token in _TOKEN_SEPARATORS.split(title or ""):
        if len(token) >= MINIMUM_TOKEN_LENGTH and token.isalpha() and token.isascii():
            tokens.append(token)
    return tokens


def _distance_one_variants(word):
    """
    *every string one insertion, deletion, substitution or transposition from `word`*

    **Key Arguments:**

    - ``word`` -- a lowercase token

    **Return:**

    - ``variants`` -- the candidate set, excluding `word` itself
    """
    splits = [(word[:index], word[index:]) for index in range(len(word) + 1)]
    variants = set()
    for left, right in splits:
        if right:
            variants.add(left + right[1:])                                  # DELETION
            for letter in _ALPHABET:
                variants.add(left + letter + right[1:])                     # SUBSTITUTION
        if len(right) > 1:
            variants.add(left + right[1] + right[0] + right[2:])            # TRANSPOSITION
        for letter in _ALPHABET:
            variants.add(left + letter + right)                             # INSERTION
    variants.discard(word)
    return variants


def suggest(token):
    """
    *the best distance-1 dictionary word for a token, or `None` if it needs no correction*

    Returns `None` for a token already in the dictionary - that is the
    common case and must be cheap.

    **Key Arguments:**

    - ``token`` -- the token to check, in any case

    **Return:**

    - ``suggestion`` -- a lowercase dictionary word, or `None`
    """
    words = _load_words()
    if not words:
        return None

    lowered = token.lower()
    if lowered in words:
        return None

    candidates = _distance_one_variants(lowered) & words
    if not candidates:
        return None
    # NO FREQUENCY DATA SHIPS WITH THE LIST, SO PREFER THE LONGEST CANDIDATE
    # AND BREAK TIES ALPHABETICALLY. "LONGEST FIRST" AND "ASSUME A DROPPED
    # LETTER FIRST" ARE THE SAME RULE: AT EDIT DISTANCE 1 A CANDIDATE IS ONLY
    # EVER ONE SHORTER, THE SAME LENGTH, OR ONE LONGER, AND A DROPPED LETTER
    # IS THE COMMONEST TYPO. PREFERRING THE SHORTEST PICKED AGAINST THAT CASE
    # BY CONSTRUCTION - MEASURED AT 57.6 PER CENT RIGHT AND 25.0 PER CENT
    # WRONG, AGAINST 75.0 AND 7.6 PER CENT HERE, AT NO COST TO THE FIRE RATE.
    return min(candidates, key=lambda word: (-len(word), word))


def detect(title, rootPath=None, settings=None, log=None):
    """
    *the suspect tokens in a title, without prompting about any of them*

    The non-prompting half of `check_title`, for callers that render the
    offers themselves rather than asking at a terminal - the `--json`
    contract and, through it, the Alfred confirmation screen. It applies
    the same three filters the prompt path does (the off switch, the
    learned vocabulary, one entry per distinct token) and then stops,
    changing nothing.

    A caller that renders these has *offered* nothing yet, which is why
    the contract keeps them apart from `corrections`: those are
    substitutions already applied to the title.

    **Key Arguments:**

    - ``title`` -- the title as the user typed it
    - ``rootPath`` -- the aardvark system root, for the learned vocabulary. Default `None`, meaning no filtering.
    - ``settings`` -- the aardvark settings dict. Default `None`.
    - ``log`` -- logger. Default `None`.

    **Return:**

    - ``suggestions`` -- one `{token, index, suggested}` dict per suspect token, in title order

    **Usage:**

    ```python
    from aardvark_jd import spell_check
    suggestions = spell_check.detect("Cardilogist notes", rootPath=rootPath, settings=settings)
    ```
    """
    if not title or not enabled(settings):
        return []

    known = vocabulary.load(rootPath, log=log) if rootPath else frozenset()
    suggestions = []
    seen = set()

    for index, token in enumerate(tokenise(title)):
        lowered = token.lower()
        if lowered in known or lowered in seen:
            continue
        suggestion = suggest(token)
        if not suggestion:
            continue
        # THE FIRST POSITION, NOT EVERY ONE. THE DECISION IS ABOUT THE WORD,
        # AND ACCEPTING A CORRECTION REPLACES EVERY OCCURRENCE OF IT.
        seen.add(lowered)
        suggestions.append({"token": token, "index": index, "suggested": suggestion})

    return suggestions


def cased_suggestion(original, replacement):
    """
    *carry the original token's capitalisation onto its replacement*

    **Key Arguments:**

    - ``original`` -- the token as the user typed it
    - ``replacement`` -- the lowercase dictionary word

    **Return:**

    - ``cased`` -- the replacement, capitalised to match
    """
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement.capitalize()
    return replacement


def _replace_token(title, token, replacement):
    """
    *substitute one token in a title, leaving every separator and other token alone*

    **Key Arguments:**

    - ``title`` -- the full title
    - ``token`` -- the token to replace, as it appears
    - ``replacement`` -- what to put there

    **Return:**

    - ``title`` -- the title with that one token replaced
    """
    # THE LOOKAROUNDS GUARD LETTERS, NOT DIGITS, SO A TITLE PAIRING A
    # DIGIT-SUFFIXED TOKEN WITH THE SAME BARE MISSPELLING (`aadvark2 aadvark`)
    # WOULD MATCH INSIDE THE FORMER FIRST. `tokenise` NEVER OFFERS A TOKEN
    # CONTAINING A DIGIT, SO THAT ONLY MISPLACES A CORRECTION THE USER ASKED
    # FOR, AND ONLY IN A TITLE SHAPED THAT WAY.
    return re.sub(
        rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", replacement, title, count=1,
    )


def substituted_title(title, token, suggested):
    """
    *accept one suggestion, without asking about it*

    The substitution half of the prompt path, for callers that collected
    the answer in their own UI - the Alfred confirmation screen's
    correction rows. It carries the typed capitalisation onto the
    lowercase dictionary word and replaces **every** occurrence, because
    the decision is about the word rather than the position.

    **Key Arguments:**

    - ``title`` -- the title to substitute into
    - ``token`` -- the suspect token, as the user typed it
    - ``suggested`` -- the lowercase dictionary word to put there

    **Return:**

    - ``title`` -- a new title with that token replaced, unchanged if it was not there

    **Usage:**

    ```python
    from aardvark_jd import spell_check
    title = spell_check.substituted_title("Aadvark notes", "Aadvark", "aardvark")
    ```
    """
    replacement = cased_suggestion(token, suggested)
    while True:
        replaced = _replace_token(title, token, replacement)
        if replaced == title:
            return title
        title = replaced


def check_title(title, rootPath=None, settings=None, log=None):
    """
    *offer a correction for each suspect token, and return the title to actually use*

    Interactive sessions get one `[y/N]` prompt per suspect token, in
    title order. Accepting substitutes that token. **Declining - `N` or a
    bare Enter - records the token in the learned vocabulary permanently**,
    so the low-friction answer is the one that makes the feature go quiet
    on recurring jargon. That self-silencing is what makes this worth
    shipping at all.

    Non-interactive sessions (scripts, CI, the test suite) never block:
    the title is used exactly as typed and one note per suspect token goes
    to stderr. Those notes are filtered through the same learned
    vocabulary, so a token dismissed interactively stays quiet in later
    scripted runs.

    **Key Arguments:**

    - ``title`` -- the title as the user typed it
    - ``rootPath`` -- the aardvark system root, for the learned vocabulary. Default `None`, meaning no learning.
    - ``settings`` -- the aardvark settings dict. Default `None`.
    - ``log`` -- logger. Default `None`.

    **Return:**

    - ``title`` -- the corrected title, or the original if nothing was accepted

    **Usage:**

    ```python
    from aardvark_jd import spell_check
    title = spell_check.check_title("Aadvark notes", rootPath=rootPath, settings=settings)
    ```
    """
    return _check_title(title, rootPath=rootPath, settings=settings, log=log)[0]


def _check_title(title, rootPath=None, settings=None, log=None, interactive=None):
    """
    *`check_title`'s engine, reporting the substitutions it made as well as the title*

    Split out because the mutating commands have to tell the caller
    **what** was changed, not only that something was, and duplicating a
    prompt loop to do it would be two loops to keep in step.

    **Key Arguments:**

    - ``title`` -- the title as the user typed it
    - ``rootPath`` -- the aardvark system root, for the learned vocabulary. Default `None`.
    - ``settings`` -- the aardvark settings dict. Default `None`.
    - ``log`` -- logger. Default `None`.
    - ``interactive`` -- may this prompt? Default `None`, meaning "ask if stdin is a terminal".

    **Return:**

    - ``title`` -- the corrected title
    - ``corrections`` -- one `{"from", "to"}` dict per substitution actually applied
    """
    corrections = []

    if not title or not enabled(settings):
        return title, corrections

    known = vocabulary.load(rootPath, log=log) if rootPath else frozenset()
    # A CALLER THAT PROMISES NEVER TO PROMPT - `--json` - SAYS SO, RATHER THAN
    # BEING INFERRED FROM THE AMBIENT TTY. THE INFERENCE HOLDS FOR ALFRED,
    # WHOSE SUBPROCESS HAS NO TERMINAL, AND BLOCKS FOREVER FOR ANYONE RUNNING
    # `--json` FROM A REAL ONE.
    if interactive is None:
        interactive = sys.stdin.isatty()
    # A TITLE CAN REPEAT A TOKEN. ONE DECISION COVERS EVERY OCCURRENCE OF IT -
    # ASKING TWICE ABOUT THE SAME WORD IN ONE TITLE WOULD BE ABSURD, AND THE
    # FIRST DECLINE HAS ALREADY LEARNED IT ANYWAY.
    handled = set()

    for token in tokenise(title):
        lowered = token.lower()
        if lowered in known or lowered in handled:
            continue
        suggestion = suggest(token)
        if not suggestion:
            continue
        handled.add(lowered)

        if not interactive:
            print(
                f"note: '{token}' in title may be a typo of '{suggestion}'",
                file=sys.stderr,
            )
            continue

        corrected = cased_suggestion(token, suggestion)
        try:
            reply = input(f"'{token}' - did you mean '{corrected}'? [y/N] ")
        except EOFError:
            # Ctrl-D AT THE PROMPT. THIS HELPER PROMISES IT CANNOT BREAK THE
            # COMMAND, SO AN END-OF-INPUT IS A DECLINE, NOT A TRACEBACK - BUT
            # IT IS NOT A DELIBERATE DISMISSAL, SO IT TEACHES NOTHING.
            print(file=sys.stderr)
            break

        if reply.strip().lower() in ("y", "yes"):
            title = substituted_title(title, token, suggestion)
            # ONE ENTRY PER DECISION, NOT PER OCCURRENCE, MATCHING THE PROMPT.
            corrections.append({"from": token, "to": corrected})
        elif rootPath:
            # DECLINING TEACHES IT THE WORD. THIS IS THE WHOLE REASON THE
            # FEATURE IS TOLERABLE: WHAT IT FLAGS ON A REAL TREE IS MOSTLY
            # PROPER NOUNS, AND EACH IS RETIRED BY ONE DISMISSAL.
            vocabulary.remember(rootPath, token, log=log)

    return title, corrections


def checked_title(rawTitle, settings=None, log=None):
    """
    *the title to build a new entity from, after offering to correct any typo in it*

    The single entry point the four `add_*` commands call, so the way the
    system root is located stays in one place.

    **Key Arguments:**

    - ``rawTitle`` -- the title as the user typed it
    - ``settings`` -- the aardvark settings dict. Default `None`.
    - ``log`` -- logger. Default `None`.

    **Return:**

    - ``title`` -- the title to actually use
    """
    return checked_title_details(rawTitle, settings=settings, log=log)["title"]


def checked_title_details(rawTitle, settings=None, log=None, interactive=None):
    """
    *the title to build a new entity from, and everything the caller has to report about it*

    What `checked_title` returns, plus the two fields the JSON contract
    carries and keeps strictly apart:

    - ``corrections`` -- substitutions **applied**, empty when the check
      was skipped, declined or never prompted at all
    - ``suggestions`` -- suspect tokens **offered and not accepted**,
      detected on the title actually being used

    A headless run is exactly the case the second field exists for: it
    prompts about nothing and so applies nothing, leaving `corrections`
    empty in the one run the Alfred confirmation screen needs filled.
    Detection therefore runs regardless of whether anything was asked.

    **Key Arguments:**

    - ``rawTitle`` -- the title as the user typed it
    - ``settings`` -- the aardvark settings dict. Default `None`.
    - ``log`` -- logger. Default `None`.
    - ``interactive`` -- may this prompt? Default `None`, meaning "ask if stdin is a terminal". `--json` passes `False`, because that promise is the caller's to make and not the terminal's to imply.

    **Return:**

    - ``details`` -- a new `{"title", "corrections", "suggestions"}` dict

    **Usage:**

    ```python
    from aardvark_jd import spell_check
    details = spell_check.checked_title_details("Aadvark notes", settings, log)
    ```
    """
    rootPath = ((settings or {}).get("system") or {}).get("root_path")
    title, corrections = _check_title(
        rawTitle, rootPath=rootPath, settings=settings, log=log, interactive=interactive,
    )
    return {
        "title": title,
        "corrections": corrections,
        "suggestions": detect(title, rootPath=rootPath, settings=settings, log=log),
    }
