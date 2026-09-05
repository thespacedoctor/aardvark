import logging
import os

import pytest
import yaml

from aardvark_jd import db, emoji_picker, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.initialiser import initialiser

log = logging.getLogger("test_resolve_emoji")
log.addHandler(logging.NullHandler())


@pytest.fixture
def settingsFile(tmp_path):
    settingsPath = str(tmp_path / "settings.yaml")
    with open(settingsPath, "w") as stream:
        yaml.safe_dump({"version": 1, "system": {"name": None, "root_path": None}}, stream)
    return settingsPath


@pytest.fixture
def systemDbConn(tmp_path, settingsFile):
    rootPath = initialiser(
        log=log, systemName="My Life", parentPath=str(tmp_path), pathToSettingsFile=settingsFile
    ).get()
    dbConn = db.get_connection(paths.find_db_path(rootPath))
    yield dbConn
    dbConn.close()


@pytest.fixture
def nonInteractive(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


# --------------------------------------------------------- chosen emoji wins


def test_chosen_emoji_skips_the_prompt(interactive, monkeypatch):
    def noInput(*args, **kwargs):
        raise AssertionError("must not prompt when an emoji was supplied")

    monkeypatch.setattr("builtins.input", noInput)
    assert emoji_picker.resolve_emoji("Doctors", "GP", chosenEmoji="🩺") == "🩺"


def test_chosen_emoji_is_stripped():
    assert emoji_picker.resolve_emoji("Doctors", chosenEmoji="  🩺  ") == "🩺"


@pytest.mark.parametrize(
    "bad, expected",
    [
        ("a/b", "cannot be used in a folder name"),
        ("a\\b", "cannot be used in a folder name"),
        ("x\ny", "cannot be used in a folder name"),
        ("", "an emoji is required"),
    ],
)
def test_path_breaking_chosen_emoji_is_rejected(bad, expected):
    with pytest.raises(ValueError, match=expected):
        emoji_picker.validate_chosen_emoji(bad)


# ---------------------------------------------------------------- non-TTY


def test_non_tty_takes_the_offline_pick_without_prompting(nonInteractive, monkeypatch):
    monkeypatch.setattr(emoji_picker, "pick_emoji", lambda *a, **k: "🩺")

    def noInput(*args, **kwargs):
        raise AssertionError("must not prompt in a non-interactive session")

    monkeypatch.setattr("builtins.input", noInput)
    assert emoji_picker.resolve_emoji("Doctors") == "🩺"


def test_non_tty_offline_pick_end_to_end(nonInteractive):
    # a real keyword hit and a real miss, straight through the offline index
    assert emoji_picker.resolve_emoji("Hospital") == "🏥"
    assert emoji_picker.resolve_emoji("Xyzzyqwerty Blergh") == emoji_picker.FALLBACK_EMOJI


# -------------------------------------------------------------------- TTY


def test_tty_accepts_the_offline_pick_on_a_bare_enter(interactive, monkeypatch, capsys):
    monkeypatch.setattr(emoji_picker, "pick_emoji", lambda *a, **k: "🩺")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")

    assert emoji_picker.resolve_emoji("Doctors") == "🩺"
    assert "🩺" in capsys.readouterr().out


def test_tty_lets_the_user_type_the_emoji(interactive, monkeypatch):
    monkeypatch.setattr(emoji_picker, "pick_emoji", lambda *a, **k: emoji_picker.FALLBACK_EMOJI)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "🩺")
    assert emoji_picker.resolve_emoji("Doctors") == "🩺"


def test_tty_reprompts_after_an_unusable_reply(interactive, monkeypatch, capsys):
    monkeypatch.setattr(emoji_picker, "pick_emoji", lambda *a, **k: emoji_picker.FALLBACK_EMOJI)
    replies = iter(["a/b", "🏥"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(replies))

    assert emoji_picker.resolve_emoji("Doctors") == "🏥"
    assert "cannot be used in a folder name" in capsys.readouterr().out


# ------------------------------------------------------------- emoji_source


def test_resolve_with_source_labels_a_supplied_emoji_chosen():
    emoji, source = emoji_picker.resolve_emoji_with_source("Doctors", chosenEmoji="🩺")
    assert (emoji, source) == ("🩺", "chosen")


def test_resolve_with_source_labels_the_offline_pick_offline(nonInteractive):
    emoji, source = emoji_picker.resolve_emoji_with_source("Hospital")
    assert (emoji, source) == ("🏥", "offline")


def test_resolve_with_source_calls_the_fallback_offline_not_deferred(nonInteractive):
    emoji, source = emoji_picker.resolve_emoji_with_source("Xyzzyqwerty Blergh")
    assert (emoji, source) == (emoji_picker.FALLBACK_EMOJI, "offline")


# -------------------------------------------------- wired through the workers


def test_add_area_honours_the_chosen_emoji(systemDbConn, interactive):
    _code, folderPath, _ = add_area(
        log=log, dbConn=systemDbConn, domain="areas", title="Health",
        description="...", chosenEmoji="🩺",
    ).get()

    assert os.path.basename(folderPath) == "A10_19_health🩺"
    assert db.get_area(systemDbConn, "areas", 10)["emoji"] == "🩺"


def test_add_category_honours_the_chosen_emoji(systemDbConn, interactive):
    add_area(log=log, dbConn=systemDbConn, domain="areas", title="Health",
             description="...", chosenEmoji="🩺").get()
    _code, folderPath, _ = add_category(
        log=log, dbConn=systemDbConn, domain="areas", areaRef="A10", title="Doctors",
        description="...", chosenEmoji="👩‍⚕️",
    ).get()

    assert os.path.basename(folderPath) == "A11_doctors👩‍⚕️"
    assert db.get_category(systemDbConn, "areas", 11)["emoji"] == "👩‍⚕️"


def test_non_interactive_worker_takes_the_offline_pick(systemDbConn, nonInteractive):
    _code, folderPath, _ = add_area(
        log=log, dbConn=systemDbConn, domain="areas", title="Hospital", description="...",
    ).get()
    assert os.path.basename(folderPath) == "A10_19_hospital🏥"
