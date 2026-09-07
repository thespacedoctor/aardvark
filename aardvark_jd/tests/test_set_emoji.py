import logging
import os

import pytest
import yaml

from aardvark_jd import db, folders, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.initialiser import initialiser
from aardvark_jd.repair_emoji import repair_emoji
from aardvark_jd.set_emoji import rename_folder_and_reindex, set_emoji

log = logging.getLogger("test_set_emoji")
log.addHandler(logging.NullHandler())


@pytest.fixture
def settingsFile(tmp_path):
    settingsPath = str(tmp_path / "settings.yaml")
    with open(settingsPath, "w") as stream:
        yaml.safe_dump({"version": 1, "system": {"name": None, "root_path": None}}, stream)
    return settingsPath


@pytest.fixture
def populatedSystem(tmp_path, settingsFile):
    """*an initialised system with an area, two categories and IDs beneath them*"""
    rootPath = initialiser(
        log=log, systemName="My Life", parentPath=str(tmp_path), pathToSettingsFile=settingsFile
    ).get()
    dbConn = db.get_connection(paths.find_db_path(rootPath))

    add_area(log=log, dbConn=dbConn, domain="areas", title="Health",
             description="Physical and mental health", chosenEmoji="🩺").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors",
                 description="GP and specialists", chosenEmoji="👩‍⚕️").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Dentists",
                 description="Dental care", chosenEmoji="🦷").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist",
           description="Dr Smith").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Optician",
           description="Annual check").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A12", title="Hygienist",
           description="Six monthly").get()

    yield rootPath, dbConn
    dbConn.close()


def _all_indexed_paths(dbConn):
    """*every folder_path the index holds, keyed by a readable label*"""
    indexed = {}
    for row in db.list_system_folders(dbConn):
        indexed[f"system:{row['folder_key']}"] = row["folder_path"]
    for table, key in (("areas", "area_id"), ("categories", "category_id"),
                       ("ids", "id_id")):
        for row in dbConn.execute(f"SELECT {key}, folder_path FROM {table}").fetchall():
            indexed[f"{table}:{row[key]}"] = row["folder_path"]
    return indexed


def test_every_indexed_path_exists_before_any_rename(populatedSystem):
    _rootPath, dbConn = populatedSystem
    for label, folderPath in _all_indexed_paths(dbConn).items():
        assert os.path.isdir(folderPath), f"{label} is not on disk"


def test_set_area_emoji_cascades_to_categories_and_ids(populatedSystem):
    _rootPath, dbConn = populatedSystem

    label, newFolderPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="A10", newEmoji="🏥"
    ).get()

    assert label == "A10-19"
    assert os.path.basename(newFolderPath) == "A10_19_health🏥"
    assert os.path.isdir(newFolderPath)

    # THE CASCADE: EVERY DESCENDANT ROW MUST NOW POINT SOMEWHERE REAL
    for descriptor, folderPath in _all_indexed_paths(dbConn).items():
        assert os.path.isdir(folderPath), f"{descriptor} was left pointing at a stale path"

    categories = db.list_categories(dbConn, "areas")
    assert len(categories) == 2
    for category in categories:
        assert category["folder_path"].startswith(newFolderPath + "/")

    for category in categories:
        for row in db.list_ids(dbConn, "areas", category["category_id"]):
            assert row["folder_path"].startswith(category["folder_path"] + "/")


def test_set_category_emoji_cascades_to_its_ids_only(populatedSystem):
    _rootPath, dbConn = populatedSystem
    dentistsBefore = db.get_category(dbConn, "areas", 12)["folder_path"]

    _label, newFolderPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="A11", newEmoji="🩻"
    ).get()

    assert os.path.basename(newFolderPath) == "A11_doctors🩻"
    for descriptor, folderPath in _all_indexed_paths(dbConn).items():
        assert os.path.isdir(folderPath), f"{descriptor} was left pointing at a stale path"

    doctors = db.get_category(dbConn, "areas", 11)
    for row in db.list_ids(dbConn, "areas", doctors["category_id"]):
        assert row["folder_path"].startswith(newFolderPath + "/")

    # THE SIBLING CATEGORY MUST BE UNTOUCHED
    assert db.get_category(dbConn, "areas", 12)["folder_path"] == dentistsBefore


def test_set_system_folder_emoji_cascades_to_the_whole_domain(populatedSystem):
    _rootPath, dbConn = populatedSystem

    _label, newFolderPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="root.areas", newEmoji="🎯"
    ).get()

    assert os.path.basename(newFolderPath) == "03_AREAS🎯"
    # RENAMING A SECTION FOLDER MOVES EVERY AREA, CATEGORY AND ID BENEATH IT
    for descriptor, folderPath in _all_indexed_paths(dbConn).items():
        assert os.path.isdir(folderPath), f"{descriptor} was left pointing at a stale path"

    area = db.get_area(dbConn, "areas", 10)
    assert area["folder_path"].startswith(newFolderPath + "/")
    for category in db.list_categories(dbConn, "areas"):
        assert category["folder_path"].startswith(newFolderPath + "/")


def test_search_still_resolves_after_a_rename(populatedSystem):
    from aardvark_jd.search import search

    _rootPath, dbConn = populatedSystem
    set_emoji(log=log, dbConn=dbConn, ref="A10", newEmoji="🏥").get()

    results = search(log=log, dbConn=dbConn, terms=["cardiologist"]).get()
    assert results
    for row in results:
        assert os.path.isdir(row["path"]), "the search index kept a stale path"


def test_set_projects_domain_area_and_category_emoji(tmp_path, settingsFile):
    rootPath = initialiser(
        log=log, systemName="My Life", parentPath=str(tmp_path), pathToSettingsFile=settingsFile
    ).get()
    dbConn = db.get_connection(paths.find_db_path(rootPath))
    add_area(log=log, dbConn=dbConn, domain="projects", title="Launches", description="", chosenEmoji="🚀").get()
    add_category(log=log, dbConn=dbConn, domain="projects", areaRef="P10", title="Website",
                 description="", chosenEmoji="🌐").get()

    label, newFolderPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="P10", newEmoji="🎯"
    ).get()
    assert label == "P10-19"
    assert os.path.basename(newFolderPath) == "P10_19_launches🎯"
    assert os.path.isdir(newFolderPath)

    label, newFolderPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="P11", newEmoji="🖥️"
    ).get()
    assert label == "P11"
    assert os.path.basename(newFolderPath) == "P11_website🖥️"
    assert os.path.isdir(newFolderPath)
    dbConn.close()


def test_set_emoji_is_idempotent(populatedSystem):
    _rootPath, dbConn = populatedSystem
    _label, firstPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="A10", newEmoji="🏥"
    ).get()
    before = _all_indexed_paths(dbConn)

    _label, secondPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="A10", newEmoji="🏥"
    ).get()

    assert secondPath == firstPath
    assert _all_indexed_paths(dbConn) == before


def test_set_emoji_refuses_to_clobber_an_existing_folder(populatedSystem):
    _rootPath, dbConn = populatedSystem
    area = db.get_area(dbConn, "areas", 10)
    collidingPath = os.path.dirname(area["folder_path"]) + "/A10_19_health🏥"
    os.makedirs(collidingPath)

    with pytest.raises(ValueError, match="refusing to overwrite"):
        set_emoji(log=log, dbConn=dbConn, ref="A10", newEmoji="🏥").get()

    # THE ORIGINAL MUST BE LEFT EXACTLY AS IT WAS
    assert db.get_area(dbConn, "areas", 10)["folder_path"] == area["folder_path"]
    assert os.path.isdir(area["folder_path"])


def test_rename_allows_a_case_only_change(populatedSystem, tmp_path):
    """*a rename that only changes case must not trip the collision check*

    On a case-insensitive filesystem (the macOS default - confirmed live
    against a real Dropbox system this session, where renaming
    `01_inbox` to `01_INBOX` failed for exactly this reason before the
    fix), `os.path.exists` on the new, differently-cased path returns True
    even though it resolves to the *same* directory entry as the old path.
    Treating that as a collision would make it impossible to ever correct
    a folder's casing - exactly what renumbering the root skeleton to
    `00_INDEX`/`02_P.ROJECTS`/etc. needs to do for anyone upgrading from
    the old lowercase scheme.
    """
    _rootPath, dbConn = populatedSystem

    oldPath = str(tmp_path / "casetest")
    os.makedirs(oldPath)

    try:
        isCaseInsensitiveFs = os.path.exists(oldPath.upper()) and os.path.samefile(oldPath.upper(), oldPath)
    except OSError:
        isCaseInsensitiveFs = False
    if not isCaseInsensitiveFs:
        pytest.skip("this filesystem is case-sensitive - the scenario under test can't arise")

    updated = {}
    newFolderPath = rename_folder_and_reindex(
        dbConn, oldPath, "CASETEST",
        lambda name, path: updated.update(name=name, path=path),
    )

    assert newFolderPath == str(tmp_path / "CASETEST")
    assert os.path.isdir(newFolderPath)
    assert os.path.basename(newFolderPath) == "CASETEST", "the on-disk name must actually carry the new case"
    assert updated == {"name": "CASETEST", "path": newFolderPath}


def test_failed_index_write_rolls_back_the_rename(populatedSystem, monkeypatch):
    _rootPath, dbConn = populatedSystem
    area = db.get_area(dbConn, "areas", 10)

    def explode(*args, **kwargs):
        raise RuntimeError("index write failed")

    monkeypatch.setattr(db, "rewrite_folder_path_prefix", explode)

    with pytest.raises(RuntimeError):
        set_emoji(log=log, dbConn=dbConn, ref="A10", newEmoji="🏥").get()

    # THE FOLDER MUST BE BACK WHERE IT STARTED, AND THE INDEX UNCHANGED
    assert os.path.isdir(area["folder_path"])
    assert db.get_area(dbConn, "areas", 10)["folder_path"] == area["folder_path"]


def test_unknown_refs_raise_clear_errors(populatedSystem):
    _rootPath, dbConn = populatedSystem

    with pytest.raises(KeyError):
        set_emoji(log=log, dbConn=dbConn, ref="nonsense", newEmoji="🏥").get()
    with pytest.raises(ValueError, match="no area"):
        set_emoji(log=log, dbConn=dbConn, ref="A90", newEmoji="🏥").get()
    with pytest.raises(ValueError, match="no category"):
        set_emoji(log=log, dbConn=dbConn, ref="A19", newEmoji="🏥").get()
    with pytest.raises(ValueError, match="no area"):
        set_emoji(log=log, dbConn=dbConn, ref="P90", newEmoji="🏥").get()
    with pytest.raises(KeyError):
        set_emoji(log=log, dbConn=dbConn, ref="root.nope", newEmoji="🏥").get()


def test_set_emoji_rejects_a_path_breaking_emoji(populatedSystem):
    _rootPath, dbConn = populatedSystem
    with pytest.raises(ValueError, match="cannot be used in a folder name"):
        set_emoji(log=log, dbConn=dbConn, ref="A10", newEmoji="a/b").get()


# ----------------------------------------------------------- repair_emoji


def test_repair_emoji_resets_drifted_system_folders(populatedSystem):
    _rootPath, dbConn = populatedSystem

    # DRIFT TWO FOLDERS, ONE OF THEM A PARENT OF THE OTHER
    set_emoji(log=log, dbConn=dbConn, ref="root.areas", newEmoji="❓").get()
    set_emoji(log=log, dbConn=dbConn, ref="areas.system.02_llm", newEmoji="❓").get()

    repaired = repair_emoji(log=log, dbConn=dbConn).get()
    repairedKeys = {folderKey for folderKey, _path in repaired}
    assert "root.areas" in repairedKeys
    assert "areas.system.02_llm" in repairedKeys

    assert db.get_system_folder(dbConn, "root.areas")["folder_name"] == "03_AREAS🧭"
    assert db.get_system_folder(dbConn, "areas.system.02_llm")["folder_name"] == "A02_llm🤖"

    for descriptor, folderPath in _all_indexed_paths(dbConn).items():
        assert os.path.isdir(folderPath), f"{descriptor} was left pointing at a stale path"


def test_repair_emoji_handles_the_folder_holding_the_open_database(populatedSystem):
    """*repairing `root.index` renames the very directory the open connection's sqlite file lives in*

    An already-open sqlite connection is permanently write-poisoned the
    instant its containing directory is renamed by *anyone* - even a rename
    it had nothing to do with, and even before that connection has ever
    written anything. Reads still work; every future write fails with
    "attempt to write a readonly database". So this test can't drift
    `root.index` using the fixture's already-open `dbConn` and then keep
    using that same connection for the call under test - by the time the
    drift is in place, `dbConn` is already broken for writes.

    Instead the drift is set up with a short-lived, throwaway connection
    that's closed immediately afterwards - exactly the shape `cl_utils.main`
    itself uses (one fresh connection per CLI invocation) - and
    `repair_emoji` is exercised against a second fresh connection, matching
    how the real "next command" recovers after a run that renamed
    `root.index`.
    """
    rootPath, dbConn = populatedSystem
    dbConn.close()

    # SIMULATE A LEGACY SYSTEM WHERE root.index AND root.areas ALREADY
    # CARRY THE WRONG EMOJI, VIA A CONNECTION THAT'S DISCARDED RIGHT AFTER -
    # NOTHING FROM HERE ON TOUCHES THIS CONNECTION AGAIN.
    setupConn = db.get_connection(paths.find_db_path(rootPath))
    areasRow = db.get_system_folder(setupConn, "root.areas")
    driftedAreasPath = os.path.dirname(areasRow["folder_path"].rstrip("/")) + "/A.REAS❓"
    db.update_system_folder(setupConn, "root.areas", "A.REAS❓", driftedAreasPath)
    db.rewrite_folder_path_prefix(setupConn, areasRow["folder_path"], driftedAreasPath)
    setupConn.commit()
    os.rename(areasRow["folder_path"], driftedAreasPath)

    # THE DRIFTED NAME MUST STILL MATCH `_ROOT_INDEX_GLOB` ("00_INDEX*") - IT'S
    # SIMULATING A WRONG *EMOJI*, NOT A DB THAT'S BECOME UNFINDABLE.
    indexRow = db.get_system_folder(setupConn, "root.index")
    driftedIndexPath = os.path.dirname(indexRow["folder_path"].rstrip("/")) + "/00_INDEX❓"
    db.update_system_folder(setupConn, "root.index", "00_INDEX❓", driftedIndexPath)
    db.rewrite_folder_path_prefix(setupConn, indexRow["folder_path"], driftedIndexPath)
    setupConn.commit()
    os.rename(indexRow["folder_path"], driftedIndexPath)
    setupConn.close()

    # THE ACTUAL COMMAND UNDER TEST: A FRESH CONNECTION, AS `cl_utils.main`
    # OPENS PER INVOCATION - IT HAS NEVER WRITTEN THROUGH A RENAMED FOLDER
    # BEFORE, SO ITS OWN RENAMES (ENDING WITH root.index) MUST ALL SUCCEED.
    repairConn = db.get_connection(paths.find_db_path(rootPath))
    repaired = repair_emoji(log=log, dbConn=repairConn).get()
    repairedKeys = [folderKey for folderKey, _path in repaired]
    assert set(repairedKeys) == {"root.index", "root.areas"}
    assert repairedKeys[-1] == "root.index", "root.index must be repaired last, or later renames break"

    indexRow = db.get_system_folder(repairConn, "root.index")
    expectedEmoji = paths.skeleton_entry("root.index")[5]
    assert indexRow["folder_name"] == folders.system_folder_name("00_INDEX", expectedEmoji)
    assert os.path.isdir(indexRow["folder_path"])
    assert os.path.isfile(f"{indexRow['folder_path']}/aardvark.db")
    assert db.get_system_folder(repairConn, "root.areas")["folder_name"] == "03_AREAS🧭"

    for descriptor, folderPath in _all_indexed_paths(repairConn).items():
        assert os.path.isdir(folderPath), f"{descriptor} was left pointing at a stale path"
    repairConn.close()

    # THE NEXT COMMAND ALSO OPENS ITS OWN FRESH CONNECTION AND MUST BE ABLE
    # TO WRITE, EVEN THOUGH `repairConn` CANNOT ANY MORE.
    nextConn = db.get_connection(paths.find_db_path(rootPath))
    db.insert_system_folder(nextConn, "test.canary", "canary", "/tmp/canary")
    nextConn.commit()
    assert db.get_system_folder(nextConn, "test.canary") is not None
    nextConn.close()


def test_repair_emoji_migrates_pre_existing_areas_categories_and_ids(tmp_path, settingsFile):
    """*repair renames folders created under the old naming convention, and backfills missing scaffolding*

    Simulates a system where an area/category/id were created (and their
    folders made on disk) before both the `<X>` naming convention and the
    reserved system scaffolding existed - i.e. inserted directly rather
    than via `add_area`/`add_category`/`add_id`, exactly as Dave's real
    pre-existing system at `~/Dropbox/aardvark` looks today.
    """
    rootPath = initialiser(
        log=log, systemName="Legacy", parentPath=str(tmp_path), pathToSettingsFile=settingsFile
    ).get()
    dbConn = db.get_connection(paths.find_db_path(rootPath))
    areasRoot = paths.resolve(dbConn, "root.areas")

    oldAreaName = "10-19 Health🏥"
    oldAreaPath = f"{areasRoot}/{oldAreaName}"
    os.makedirs(oldAreaPath)
    areaId = db.insert_area(dbConn, "areas", 10, 19, "Health", "desc", "🏥", oldAreaName, oldAreaPath)

    oldCategoryName = "11 Doctors🩺"
    oldCategoryPath = f"{oldAreaPath}/{oldCategoryName}"
    os.makedirs(oldCategoryPath)
    categoryId = db.insert_category(
        dbConn, areaId, "areas", 11, "Doctors", "desc", "🩺", oldCategoryName, oldCategoryPath
    )

    oldIdName = "11.01 Cardiologist"
    oldIdPath = f"{oldCategoryPath}/{oldIdName}"
    os.makedirs(oldIdPath)
    db.insert_id(dbConn, categoryId, "areas", 11, 1, "Cardiologist", "desc", oldIdName, oldIdPath)

    repair_emoji(log=log, dbConn=dbConn).get()

    area = db.get_area(dbConn, "areas", 10)
    assert area["folder_name"] == "A10_19_health🏥"
    assert os.path.isdir(area["folder_path"])
    assert not os.path.isdir(oldAreaPath)

    category = db.get_category(dbConn, "areas", 11)
    assert category["folder_name"] == "A11_doctors🩺"
    assert os.path.isdir(category["folder_path"])

    idRow = dbConn.execute("SELECT * FROM ids WHERE ac_number = 11 AND item_number = 1").fetchone()
    assert idRow["folder_name"] == "A11.01_cardiologist"
    assert os.path.isdir(idRow["folder_path"])

    # RESERVED SCAFFOLDING DIDN'T EXIST FOR THIS PRE-MIGRATION AREA/CATEGORY -
    # REPAIR MUST HAVE BACKFILLED IT
    assert db.get_system_folder(dbConn, "areas.10.system") is not None
    assert os.path.isdir(f"{area['folder_path']}/A10_system⚙️")
    assert db.get_system_folder(dbConn, "areas.11.00_index") is not None
    assert os.path.isdir(f"{category['folder_path']}/A11.00_index🗂️")

    # THE AREA'S OWN RESERVED SYSTEM FOLDER MUST HAVE ITS TEN RESERVED IDS
    # BACKFILLED TOO, NOT JUST THE FOLDER ITSELF
    assert db.get_system_folder(dbConn, "areas.10.02_llm") is not None
    assert os.path.isdir(f"{area['folder_path']}/A10_system⚙️/A10.02_llm🤖")

    dbConn.close()


def test_repair_emoji_is_idempotent(populatedSystem):
    _rootPath, dbConn = populatedSystem

    # A FRESHLY INITIALISED SYSTEM ALREADY MATCHES THE SKELETON
    assert repair_emoji(log=log, dbConn=dbConn).get() == []

    set_emoji(log=log, dbConn=dbConn, ref="root.areas", newEmoji="❓").get()
    assert len(repair_emoji(log=log, dbConn=dbConn).get()) == 1

    before = _all_indexed_paths(dbConn)
    assert repair_emoji(log=log, dbConn=dbConn).get() == []
    assert _all_indexed_paths(dbConn) == before
