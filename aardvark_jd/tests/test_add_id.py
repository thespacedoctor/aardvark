import logging
import os

import pytest
import yaml

from aardvark_jd import db, folders, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.initialiser import initialiser

log = logging.getLogger("test_add_id")
log.addHandler(logging.NullHandler())


@pytest.fixture
def dbConnWithCategory(tmp_path):
    settingsPath = str(tmp_path / "settings.yaml")
    with open(settingsPath, "w") as stream:
        yaml.safe_dump({"version": 1, "system": {"name": None, "root_path": None}}, stream)
    rootPath = initialiser(
        log=log, systemName="Test", parentPath=str(tmp_path), pathToSettingsFile=settingsPath
    ).get()
    conn = db.get_connection(paths.find_db_path(rootPath))
    add_area(log=log, dbConn=conn, domain="areas", title="Health", description="").get()
    add_category(log=log, dbConn=conn, domain="areas", areaRef="A10", title="Doctors", description="").get()
    yield conn
    conn.close()


def test_add_id_happy_path(dbConnWithCategory):
    code, folderPath, _details = add_id(
        log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
        title="Cardiologist", description="Dr Smith",
    ).get()
    assert code == "A11.10"
    folderName = os.path.basename(folderPath)
    assert folderName == "A11.10_cardiologist"
    for character in folderName:
        assert ord(character) < 0x1F000
    assert os.path.isdir(folderPath)


def test_add_id_happy_path_projects_domain(tmp_path):
    settingsPath = str(tmp_path / "settings.yaml")
    with open(settingsPath, "w") as stream:
        yaml.safe_dump({"version": 1, "system": {"name": None, "root_path": None}}, stream)
    rootPath = initialiser(
        log=log, systemName="Test", parentPath=str(tmp_path), pathToSettingsFile=settingsPath
    ).get()
    conn = db.get_connection(paths.find_db_path(rootPath))
    add_area(log=log, dbConn=conn, domain="projects", title="Launches", description="").get()
    add_category(log=log, dbConn=conn, domain="projects", areaRef="P10", title="Website", description="").get()

    code, folderPath, _details = add_id(
        log=log, dbConn=conn, domain="projects", categoryRef="P11",
        title="Redesign", description="",
    ).get()
    assert code == "P11.10"
    assert os.path.basename(folderPath) == "P11.10_redesign"
    assert os.path.isdir(folderPath)
    conn.close()


def test_add_id_unknown_category_raises_clear_error(dbConnWithCategory):
    with pytest.raises(ValueError):
        add_id(
            log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A12",
            title="X", description="",
        ).get()


def test_add_id_exhaustion_surfaces_clear_error(dbConnWithCategory):
    # ITEM NUMBERS 00-09 ARE RESERVED FOR THE CATEGORY'S SYSTEM IDS, SO ONLY
    # 90 USER-CREATED IDS (10..99) FIT BEFORE EXHAUSTION
    for _ in range(90):
        add_id(
            log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
            title="X", description="",
        ).get()
    with pytest.raises(folders.IdExhaustedError):
        add_id(
            log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
            title="Overflow", description="",
        ).get()


def test_an_accepted_correction_reaches_the_id_folder_and_index(dbConnWithCategory, monkeypatch):
    """*`add_id` gained a `settings` param purely so it can find the learned vocabulary*"""
    rootPath = os.path.dirname(db.get_system_folder(dbConnWithCategory, "root.areas")["folder_path"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    _code, folderPath, _details = add_id(
        log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
        title="Aadvark", description="d", settings={"system": {"root_path": rootPath}},
    ).get()

    assert "aardvark" in os.path.basename(folderPath).lower()
    row = dbConnWithCategory.execute("SELECT title FROM ids WHERE title LIKE 'A%'").fetchone()
    assert row["title"] == "Aardvark"


def test_add_id_still_works_with_no_settings_at_all(dbConnWithCategory):
    """*`settings` is optional - an omitted one must not break the command*"""
    code, folderPath, _details = add_id(
        log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
        title="Cardiologist", description="d",
    ).get()

    assert code == "A11.10"
    assert os.path.isdir(folderPath)


# ---------------------------------------- what the worker reports back to Alfred

def test_add_id_reports_the_suspect_tokens_it_never_prompted_about(
    dbConnWithCategory, monkeypatch,
):
    """
    *headless, the check applies nothing, so `suggestions` is the only field with anything in it*

    This is what `--json` hands the Alfred confirmation screen: the
    entity was created as typed, and the offers are still outstanding.
    """
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    rootPath = os.path.dirname(
        db.get_system_folder(dbConnWithCategory, "root.areas")["folder_path"]
    )

    _code, _folderPath, details = add_id(
        log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
        title="Aadvark", description="d", settings={"system": {"root_path": rootPath}},
    ).get()

    assert details["corrections"] == []
    assert details["suggestions"] == [
        {"token": "Aadvark", "index": 0, "suggested": "aardvark"},
    ]


def test_add_id_reports_an_applied_correction(dbConnWithCategory, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    rootPath = os.path.dirname(
        db.get_system_folder(dbConnWithCategory, "root.areas")["folder_path"]
    )

    _code, _folderPath, details = add_id(
        log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
        title="Aadvark", description="d", settings={"system": {"root_path": rootPath}},
    ).get()

    assert details["corrections"] == [{"from": "Aadvark", "to": "Aardvark"}]
    assert details["suggestions"] == []


def test_add_id_reports_nothing_for_a_clean_title(dbConnWithCategory):
    _code, _folderPath, details = add_id(
        log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
        title="Cardiologist", description="d",
    ).get()

    assert details == {"corrections": [], "suggestions": []}


def test_add_id_never_prompts_when_it_is_told_not_to(dbConnWithCategory, monkeypatch):
    """*`--json` promises it never prompts, and a tty is not what makes that true*"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def refuse(prompt=""):
        raise AssertionError("a non-interactive add_id must never prompt")

    monkeypatch.setattr("builtins.input", refuse)
    rootPath = os.path.dirname(
        db.get_system_folder(dbConnWithCategory, "root.areas")["folder_path"]
    )

    code, _folderPath, details = add_id(
        log=log, dbConn=dbConnWithCategory, domain="areas", categoryRef="A11",
        title="Aadvark", description="d", settings={"system": {"root_path": rootPath}},
        interactive=False,
    ).get()

    assert code == "A11.10"
    assert details["suggestions"]
