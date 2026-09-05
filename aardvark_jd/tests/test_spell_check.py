import logging

import pytest

from aardvark_jd import spell_check, vocabulary

log = logging.getLogger("test_spell_check")
log.addHandler(logging.NullHandler())


@pytest.fixture
def interactive(monkeypatch):
    """*pretend stdin is a terminal, and script the answers to the prompts*"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def scripted(answers):
        replies = list(answers)
        prompts = []

        def fakeInput(prompt=""):
            prompts.append(prompt)
            return replies.pop(0) if replies else ""

        monkeypatch.setattr("builtins.input", fakeInput)
        return prompts

    return scripted


@pytest.fixture
def nonInteractive(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)


# ---------------------------------------------------------------- the wordlist

def test_the_shipped_wordlist_is_british_english():
    """*the whole point of `en_GB-ise` - `colour` is a word, `color` is not*"""
    words = spell_check._load_words()

    assert "colour" in words and "organise" in words
    assert "color" not in words and "organize" not in words


def test_the_live_typo_this_feature_exists_for_is_caught():
    """*`aadvark` is a real typo in the user's own tree*"""
    assert spell_check.suggest("aadvark") == "aardvark"


def test_a_correctly_spelled_word_gets_no_suggestion():
    assert spell_check.suggest("cardiologist") is None
    assert spell_check.suggest("aardvark") is None


def test_a_word_two_edits_out_gets_no_suggestion():
    """*distance 2 was measured and rejected - 49 per cent false positives*"""
    assert spell_check.suggest("crdilgist") is None


def test_the_tie_break_prefers_the_longest_candidate():
    """
    *a dropped letter is the commonest typo, so the correction is usually longer*

    Preferring the shortest candidate picks against that case by
    construction, and produces offers that read as broken rather than
    merely unhelpful.
    """
    assert spell_check.suggest("setings") == "settings"      # NOT `stings`
    assert spell_check.suggest("servies") == "services"      # NOT `series`
    assert spell_check.suggest("arhive") == "archive"        # NOT `arrive`


def test_candidates_of_equal_length_still_break_alphabetically():
    """*the rule stays deterministic - `candle` and `cradle` are both distance 1*"""
    assert spell_check.suggest("cadle") == "candle"


def test_a_letter_dropped_from_a_six_letter_word_is_now_checked():
    """
    *the floor of six made the commonest typo class structurally invisible*

    Dropping a letter from a six-character word leaves five, so every one
    of these was skipped before the token ever reached `suggest`.
    """
    assert spell_check.tokenise("famil acive sysem") == ["famil", "acive", "sysem"]
    assert spell_check.suggest("famil") == "family"
    assert spell_check.suggest("acive") == "active"
    assert spell_check.suggest("sysem") == "system"


# ---------------------------------------------------------------- tokenising

def test_tokens_are_split_on_separators_and_short_ones_ignored():
    """*short tokens are where the false positives live*"""
    assert spell_check.tokenise("Aadvark_notes-and.things xyz") == [
        "Aadvark", "notes", "things",
    ]


def test_tokens_below_the_minimum_length_are_never_checked():
    assert spell_check.tokenise("teh cat sat") == []


def test_four_character_tokens_are_still_never_checked():
    """*floor 4 was rejected on its own numbers - 12.8 per cent of titles firing*"""
    assert spell_check.tokenise("woth verb tine") == []


def test_non_alphabetic_tokens_are_skipped():
    assert spell_check.tokenise("A11.10 project2024 hello1") == []


# ------------------------------------------------- detection without a prompt

def test_detect_reports_each_suspect_token_with_its_position():
    """
    *the confirmation screen renders these, so the position has to travel with them*

    `index` is the token's position in `tokenise`'s output, not a
    character offset, so a correction row can substitute without
    re-parsing the title.
    """
    suggestions = spell_check.detect("Cardilogist appointment notes")

    assert suggestions == [
        {"token": "Cardilogist", "index": 0, "suggested": "cardiologist"},
    ]


def test_detect_never_prompts_even_on_a_terminal(monkeypatch):
    """*this is the whole point of it - `--json` must detect without asking*"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def refuse(prompt=""):
        raise AssertionError("detect must never prompt")

    monkeypatch.setattr("builtins.input", refuse)

    assert spell_check.detect("Cardilogist notes")


def test_detect_returns_the_title_untouched_by_saying_nothing_about_clean_tokens():
    assert spell_check.detect("Cardiologist appointment notes") == []


def test_detect_reports_a_repeated_token_once_at_its_first_position():
    """*one decision covers every occurrence, exactly as the prompt path does*"""
    suggestions = spell_check.detect("notes Cardilogist and cardilogist")

    assert [item["token"] for item in suggestions] == ["Cardilogist"]
    assert suggestions[0]["index"] == 1


def test_detect_filters_through_the_learned_vocabulary(tmp_path):
    vocabulary.remember(str(tmp_path), "Cardilogist", log=log)

    assert spell_check.detect("Cardilogist notes", rootPath=str(tmp_path), log=log) == []


def test_detect_respects_the_off_switch():
    settings = {"spell_check": {"enabled": False}}

    assert spell_check.detect("Cardilogist notes", settings=settings) == []


def test_detect_copes_with_an_empty_title():
    assert spell_check.detect("") == []
    assert spell_check.detect(None) == []


# ---------------------------------------------------------------- the prompt

def test_accepting_a_correction_rewrites_only_that_token(interactive, tmp_path):
    interactive(["y"])

    corrected = spell_check.check_title("Aadvark notes", rootPath=str(tmp_path), log=log)

    assert corrected == "Aardvark notes"


def test_an_accepted_correction_keeps_the_original_capitalisation(interactive, tmp_path):
    interactive(["y"])
    assert spell_check.check_title("Aadvark", rootPath=str(tmp_path), log=log) == "Aardvark"

    interactive(["y"])
    assert spell_check.check_title("aadvark", rootPath=str(tmp_path), log=log) == "aardvark"


def test_separators_and_other_tokens_survive_a_correction(interactive, tmp_path):
    interactive(["y"])

    corrected = spell_check.check_title("my_aadvark-notes.here", rootPath=str(tmp_path), log=log)

    assert corrected == "my_aardvark-notes.here"


def test_declining_keeps_the_title_exactly_as_typed(interactive, tmp_path):
    interactive(["n"])

    assert spell_check.check_title("Aadvark notes", rootPath=str(tmp_path), log=log) == "Aadvark notes"


def test_a_bare_enter_declines(interactive, tmp_path):
    interactive([""])

    assert spell_check.check_title("Aadvark", rootPath=str(tmp_path), log=log) == "Aadvark"


def test_each_suspect_token_is_prompted_separately_in_title_order(interactive, tmp_path):
    prompts = interactive(["n", "n"])

    spell_check.check_title("aadvark pydantic", rootPath=str(tmp_path), log=log)

    assert len(prompts) == 2
    assert "aadvark" in prompts[0]
    assert "pydantic" in prompts[1]


# ---------------------------------------------------------------- learning

def test_declining_teaches_it_the_word_permanently(interactive, tmp_path):
    """*the low-friction answer is the permanent one - this is why the feature self-silences*"""
    interactive(["n"])
    spell_check.check_title("pydantic models", rootPath=str(tmp_path), log=log)

    assert "pydantic" in vocabulary.load(str(tmp_path))


def test_a_learned_word_is_never_offered_again(interactive, tmp_path):
    interactive(["n"])
    spell_check.check_title("pydantic models", rootPath=str(tmp_path), log=log)

    prompts = interactive([])
    spell_check.check_title("pydantic again", rootPath=str(tmp_path), log=log)

    assert prompts == []


def test_accepting_a_correction_does_not_teach_it_the_word(interactive, tmp_path):
    interactive(["y"])

    spell_check.check_title("Aadvark", rootPath=str(tmp_path), log=log)

    assert vocabulary.load(str(tmp_path)) == frozenset()


def test_without_a_root_path_nothing_is_learned(interactive):
    """*no system root, no vocabulary - but the prompt still works*"""
    interactive(["n"])

    assert spell_check.check_title("Aadvark") == "Aadvark"


# ---------------------------------------------------------------- non-TTY

def test_a_non_interactive_run_creates_the_entity_as_typed(nonInteractive, tmp_path, capsys):
    corrected = spell_check.check_title("Aadvark notes", rootPath=str(tmp_path), log=log)

    assert corrected == "Aadvark notes"
    assert "may be a typo of 'aardvark'" in capsys.readouterr().err


def test_a_non_interactive_run_never_blocks_or_prompts(nonInteractive, tmp_path, monkeypatch):
    def mustNotPrompt(prompt=""):
        raise AssertionError("a non-interactive run must never prompt")

    monkeypatch.setattr("builtins.input", mustNotPrompt)

    spell_check.check_title("Aadvark notes", rootPath=str(tmp_path), log=log)


def test_the_non_interactive_note_is_filtered_through_the_learned_vocabulary(
    nonInteractive, tmp_path, capsys,
):
    """*a token dismissed interactively stays quiet in later scripted runs*"""
    vocabulary.remember(str(tmp_path), "aadvark", log=log)

    spell_check.check_title("Aadvark notes", rootPath=str(tmp_path), log=log)

    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------- the toggle

def test_the_feature_can_be_switched_off(interactive, tmp_path, monkeypatch):
    def mustNotPrompt(prompt=""):
        raise AssertionError("spell check is disabled")

    monkeypatch.setattr("builtins.input", mustNotPrompt)
    settings = {"spell_check": {"enabled": False}}

    assert spell_check.check_title("Aadvark", rootPath=str(tmp_path), settings=settings) == "Aadvark"


def test_the_feature_is_on_by_default():
    assert spell_check.enabled(None) is True
    assert spell_check.enabled({}) is True
    assert spell_check.enabled({"spell_check": {}}) is True
    assert spell_check.enabled({"spell_check": {"enabled": True}}) is True


def test_an_empty_title_is_returned_untouched():
    assert spell_check.check_title("") == ""
    assert spell_check.check_title(None) is None


# ---------------------------------------------------------------- degradation

def test_a_missing_wordlist_disables_the_check_rather_than_breaking_it(
    monkeypatch, interactive, tmp_path,
):
    monkeypatch.setattr(spell_check, "_words", None)
    monkeypatch.setattr(spell_check, "_WORDLIST_PATH", "/no/such/wordlist.txt")

    def mustNotPrompt(prompt=""):
        raise AssertionError("with no wordlist there is nothing to suggest")

    monkeypatch.setattr("builtins.input", mustNotPrompt)
    try:
        assert spell_check.check_title("Aadvark", rootPath=str(tmp_path)) == "Aadvark"
    finally:
        spell_check._words = None


# ---------------------------------------------------------------- repeats and interrupts

def test_a_token_repeated_in_one_title_is_asked_about_once(interactive, tmp_path):
    """*one decision covers every occurrence - asking twice about the same word would be absurd*"""
    prompts = interactive(["y"])

    corrected = spell_check.check_title("aadvark and aadvark", rootPath=str(tmp_path), log=log)

    assert len(prompts) == 1
    assert corrected == "aardvark and aardvark"


def test_declining_a_repeated_token_asks_once_and_learns_once(interactive, tmp_path):
    prompts = interactive(["n"])

    corrected = spell_check.check_title("aadvark and aadvark", rootPath=str(tmp_path), log=log)

    assert len(prompts) == 1
    assert corrected == "aadvark and aadvark"
    assert "aadvark" in vocabulary.load(str(tmp_path))


def test_a_repeated_token_is_noted_once_in_a_non_interactive_run(nonInteractive, tmp_path, capsys):
    spell_check.check_title("aadvark and aadvark", rootPath=str(tmp_path), log=log)

    assert capsys.readouterr().err.count("may be a typo") == 1


def test_ctrl_d_at_the_prompt_declines_without_breaking_the_command(monkeypatch, tmp_path):
    """*this helper promises it cannot break the command, so end-of-input is a decline*"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def endOfInput(prompt=""):
        raise EOFError()

    monkeypatch.setattr("builtins.input", endOfInput)

    assert spell_check.check_title("Aadvark notes", rootPath=str(tmp_path), log=log) == "Aadvark notes"
    # NOT A DELIBERATE DISMISSAL, SO IT TEACHES NOTHING.
    assert vocabulary.load(str(tmp_path)) == frozenset()


def test_ctrl_d_abandons_the_remaining_prompts(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    calls = []

    def endOfInput(prompt=""):
        calls.append(prompt)
        raise EOFError()

    monkeypatch.setattr("builtins.input", endOfInput)
    spell_check.check_title("aadvark pydantic", rootPath=str(tmp_path), log=log)

    assert len(calls) == 1


def test_a_non_dict_or_falsey_toggle_value_switches_it_off(monkeypatch, tmp_path):
    """*`enabled: 0` in YAML must disable it, not just a literal `false`*"""
    def mustNotPrompt(prompt=""):
        raise AssertionError("spell check is disabled")

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", mustNotPrompt)

    assert spell_check.enabled({"spell_check": {"enabled": 0}}) is False
    assert spell_check.check_title(
        "Aadvark", rootPath=str(tmp_path), settings={"spell_check": {"enabled": 0}},
    ) == "Aadvark"


def test_checked_title_finds_the_root_path_from_settings(interactive, tmp_path):
    """*the one place the four add_* commands share, so the lookup lives in one place*"""
    interactive(["n"])
    settings = {"system": {"root_path": str(tmp_path)}}

    assert spell_check.checked_title("Aadvark", settings, log) == "Aadvark"
    assert "aadvark" in vocabulary.load(str(tmp_path))


def test_checked_title_copes_with_no_settings_at_all(interactive):
    interactive(["n"])
    assert spell_check.checked_title("Aadvark", None, log) == "Aadvark"


# ------------------------------------------ what the mutating commands report

def test_the_details_report_an_accepted_substitution_as_a_correction(interactive, tmp_path):
    """
    *`corrections` is what was applied, and the contract keeps it separate from what was merely offered*
    """
    interactive(["y"])
    settings = {"system": {"root_path": str(tmp_path)}}

    details = spell_check.checked_title_details("Aadvark notes", settings, log)

    assert details["title"] == "Aardvark notes"
    assert details["corrections"] == [{"from": "Aadvark", "to": "Aardvark"}]


def test_a_declined_suggestion_is_no_correction(interactive, tmp_path):
    interactive(["n"])
    settings = {"system": {"root_path": str(tmp_path)}}

    details = spell_check.checked_title_details("Aadvark notes", settings, log)

    assert details["title"] == "Aadvark notes"
    assert details["corrections"] == []


def test_the_details_carry_the_suggestions_a_headless_run_never_offered(
    nonInteractive, tmp_path, capsys,
):
    """
    *the case the whole field exists for*

    Headless, the check prompts about nothing and applies nothing, so
    `corrections` is empty in exactly the run Alfred needs filled.
    Detection runs anyway and lands in `suggestions`.
    """
    settings = {"system": {"root_path": str(tmp_path)}}

    details = spell_check.checked_title_details("Aadvark notes", settings, log)

    assert details["title"] == "Aadvark notes"
    assert details["corrections"] == []
    assert details["suggestions"] == [
        {"token": "Aadvark", "index": 0, "suggested": "aardvark"},
    ]


def test_a_corrected_token_no_longer_appears_as_a_suggestion(interactive, tmp_path):
    """*detection runs on the title actually being used, not the one typed*"""
    interactive(["y"])
    settings = {"system": {"root_path": str(tmp_path)}}

    details = spell_check.checked_title_details("Aadvark notes", settings, log)

    assert details["suggestions"] == []


def test_a_clean_title_reports_neither(interactive):
    details = spell_check.checked_title_details("Cardiologist notes", None, log)

    assert details == {
        "title": "Cardiologist notes", "corrections": [], "suggestions": [],
    }


# ------------------------------------ substituting a suggestion without a prompt

def test_substituting_a_suggestion_carries_the_original_capitalisation():
    """*the suggestion is a lowercase dictionary word; the typed case wins*"""
    assert spell_check.substituted_title(
        "Aadvark notes", "Aadvark", "aardvark",
    ) == "Aardvark notes"
    assert spell_check.substituted_title(
        "AADVARK notes", "AADVARK", "aardvark",
    ) == "AARDVARK notes"


def test_substituting_a_suggestion_replaces_every_occurrence():
    """*the decision is about the word, exactly as at the prompt*"""
    assert spell_check.substituted_title(
        "aadvark and aadvark", "aadvark", "aardvark",
    ) == "aardvark and aardvark"


def test_substituting_leaves_the_other_tokens_and_separators_alone():
    assert spell_check.substituted_title(
        "Aadvark_notes and things", "Aadvark", "aardvark",
    ) == "Aardvark_notes and things"


def test_substituting_a_token_that_is_not_there_changes_nothing():
    assert spell_check.substituted_title("notes", "Aadvark", "aardvark") == "notes"


# ------------------------------ `--json` never prompts, whatever stdin happens to be

def test_the_check_can_be_told_not_to_prompt_even_on_a_terminal(monkeypatch, tmp_path):
    """
    *`--json` promises it never prompts, and a tty is not what makes that true*

    Alfred's subprocess has no tty, so inferring it from `isatty` happens
    to work there and blocks forever for anyone running `--json` from a
    real terminal.
    """
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def refuse(prompt=""):
        raise AssertionError("a non-interactive check must never prompt")

    monkeypatch.setattr("builtins.input", refuse)
    settings = {"system": {"root_path": str(tmp_path)}}

    details = spell_check.checked_title_details(
        "Aadvark notes", settings, log, interactive=False,
    )

    assert details["title"] == "Aadvark notes"
    assert details["corrections"] == []
    assert details["suggestions"] == [
        {"token": "Aadvark", "index": 0, "suggested": "aardvark"},
    ]


def test_the_check_still_reads_the_terminal_when_it_is_not_told(interactive, tmp_path):
    """*the default stays "ask if there is someone to ask"*"""
    interactive(["y"])
    settings = {"system": {"root_path": str(tmp_path)}}

    details = spell_check.checked_title_details("Aadvark notes", settings, log)

    assert details["title"] == "Aardvark notes"
