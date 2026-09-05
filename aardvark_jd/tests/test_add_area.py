import logging
import os

import pytest
import yaml

from aardvark_jd import db, folders, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.initialiser import initialiser

log = logging.getLogger("test_add_area")
log.addHandler(logging.NullHandler())


@pytest.fixture
def dbConn(tmp_path):
    settingsPath = str(tmp_path / "settings.yaml")
    with open(settingsPath, "w") as stream:
        yaml.safe_dump({"version": 1, "system": {"name": None, "root_path": None}}, stream)
    rootPath = initialiser(
        log=log, systemName="Test", parentPath=str(tmp_path), pathToSettingsFile=settingsPath
    ).get()
    conn = db.get_connection(paths.find_db_path(rootPath))
    yield conn
    conn.close()


@pytest.mark.parametrize("domain,letter", [("areas", "A"), ("resources", "R"), ("projects", "P")])
def test_add_area_happy_path(dbConn, domain, letter):
    code, folderPath, _ = add_area(log=log, dbConn=dbConn, domain=domain, title="Health", description="desc").get()
    assert code == f"{letter}10-19"
    assert f"{letter}10_19_health" in folderPath
    assert os.path.isdir(folderPath)


def test_add_area_domains_are_independent(dbConn):
    codeAreas, _, _ = add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="").get()
    codeResources, _, _ = add_area(log=log, dbConn=dbConn, domain="resources", title="Health", description="").get()
    assert codeAreas == "A10-19"
    assert codeResources == "R10-19"


def test_add_area_exhaustion_surfaces_clear_error(dbConn):
    for _ in range(9):
        add_area(log=log, dbConn=dbConn, domain="areas", title="X", description="").get()
    with pytest.raises(folders.DomainExhaustedError):
        add_area(log=log, dbConn=dbConn, domain="areas", title="Overflow", description="").get()


def test_add_area_invalid_domain(dbConn):
    with pytest.raises(ValueError):
        add_area(log=log, dbConn=dbConn, domain="bogus", title="X", description="").get()


def test_add_area_creates_its_reserved_system_folder(dbConn):
    _code, folderPath, _ = add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="").get()

    systemFolderPath = f"{folderPath}/A10_system⚙️"
    assert os.path.isdir(systemFolderPath)

    row = db.get_system_folder(dbConn, "areas.10.system")
    assert row["folder_name"] == "A10_system⚙️"
    assert row["folder_path"] == systemFolderPath


def test_add_area_creates_its_own_ten_reserved_ids(dbConn):
    """*the area's reserved system folder (occupying the X0 slot) gets its own .00-.09 IDs too*"""
    _code, folderPath, _ = add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="").get()
    systemFolderPath = f"{folderPath}/A10_system⚙️"

    expectedNames = [
        "A10.00_index🗂️", "A10.01_inbox📥", "A10.02_llm🤖", "A10.03_checklists☑️",
        "A10.04_templates📐", "A10.05_links🔗", "A10.06_bin📜", "A10.07_settings🎛️",
        "A10.08_someday💭", "A10.09_archive🗄️",
    ]
    for name in expectedNames:
        assert os.path.isdir(f"{systemFolderPath}/{name}")

    row = db.get_system_folder(dbConn, "areas.10.02_llm")
    assert row["folder_name"] == "A10.02_llm🤖"


def test_an_accepted_correction_reaches_the_folder_name_and_the_index(dbConn, tmp_path, monkeypatch):
    """*checking before creation is what makes one corrected title serve everything downstream*

    The folder on disk, the index row and every mirror are built from the
    same value, so there is no post-creation rename and no mirror repoint.
    """
    import os
    from aardvark_jd import db as dbModule

    rootPath = os.path.dirname(dbModule.get_system_folder(dbConn, "root.areas")["folder_path"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    code, folderPath, _ = add_area(
        log=log, dbConn=dbConn, domain="areas", title="Aadvark", description="d",
        chosenEmoji="🐾", settings={"system": {"root_path": rootPath}},
    ).get()

    assert "aardvark" in os.path.basename(folderPath).lower()
    assert os.path.isdir(folderPath)
    row = dbConn.execute("SELECT title FROM areas WHERE decade_start = 10").fetchone()
    assert row["title"] == "Aardvark"


def test_a_declined_correction_leaves_the_title_as_typed_and_is_remembered(dbConn, tmp_path, monkeypatch):
    import os
    from aardvark_jd import db as dbModule, vocabulary

    rootPath = os.path.dirname(dbModule.get_system_folder(dbConn, "root.areas")["folder_path"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    _code, folderPath, _ = add_area(
        log=log, dbConn=dbConn, domain="areas", title="Aadvark", description="d",
        chosenEmoji="🐾", settings={"system": {"root_path": rootPath}},
    ).get()

    assert "aadvark" in os.path.basename(folderPath).lower()
    assert "aadvark" in vocabulary.load(rootPath)


# ------------------------------------- what the worker reports back to Alfred


def test_add_area_details_carry_the_emoji_source_and_the_suspect_tokens(dbConn, monkeypatch):
    """*`--json` reports the emoji provenance and any suspect token, without prompting*"""
    import os
    from aardvark_jd import db as dbModule

    rootPath = os.path.dirname(dbModule.get_system_folder(dbConn, "root.areas")["folder_path"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    _code, _folderPath, details = add_area(
        log=log, dbConn=dbConn, domain="areas", title="Aadvark", description="d",
        settings={"system": {"root_path": rootPath}}, interactive=False,
    ).get()

    assert details["corrections"] == []
    assert details["suggestions"] == [{"token": "Aadvark", "index": 0, "suggested": "aardvark"}]
    assert details["emoji_source"] == "offline"


def test_add_area_details_label_a_supplied_emoji_chosen(dbConn):
    _code, _folderPath, details = add_area(
        log=log, dbConn=dbConn, domain="areas", title="Health", description="d", chosenEmoji="🩺",
    ).get()

    assert details["emoji_source"] == "chosen"
    assert details["corrections"] == []
    assert details["suggestions"] == []
