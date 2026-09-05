import logging
import os

import pytest
import yaml

from aardvark_jd import db, locate, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.initialiser import initialiser

log = logging.getLogger("test_locate")
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


@pytest.fixture
def seeded(dbConn):
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    _code, idFolderPath, _details = add_id(
        log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3"
    ).get()
    categoryFolderPath = db.get_category(dbConn, "areas", 11)["folder_path"]
    return dbConn, idFolderPath, categoryFolderPath


def test_entity_for_path_resolves_an_id_folder(seeded):
    dbConn, idFolderPath, _categoryFolderPath = seeded
    entityType, _entityKey, folderPath, label = locate.entity_for_path(dbConn, idFolderPath)
    assert entityType == "id"
    assert folderPath == idFolderPath
    assert label == "Cardiologist"


def test_entity_for_path_resolves_the_deepest_match_from_a_subfolder(seeded):
    dbConn, idFolderPath, _categoryFolderPath = seeded
    entityType, _entityKey, folderPath, _label = locate.entity_for_path(dbConn, f"{idFolderPath}/some/nested/dir")
    assert entityType == "id"
    assert folderPath == idFolderPath


def test_entity_for_path_matches_on_a_path_boundary_not_a_bare_prefix(seeded):
    dbConn, _idFolderPath, categoryFolderPath = seeded
    # a sibling folder that merely shares the category folder's name as a string
    # prefix must not be mistaken for a path inside it
    decoyPath = categoryFolderPath + "_old/somefile.txt"
    entityType, _entityKey, folderPath, _label = locate.entity_for_path(dbConn, decoyPath)
    # falls back to the containing area, not the category it merely resembles
    assert folderPath != categoryFolderPath


def test_entity_for_path_is_case_insensitive(seeded):
    dbConn, idFolderPath, _categoryFolderPath = seeded
    entityType, _entityKey, folderPath, _label = locate.entity_for_path(dbConn, idFolderPath.upper())
    assert entityType == "id"
    assert folderPath == idFolderPath


def test_entity_for_path_raises_outside_the_system(seeded):
    dbConn, _idFolderPath, _categoryFolderPath = seeded
    with pytest.raises(ValueError):
        locate.entity_for_path(dbConn, "/tmp/definitely-not-in-aardvark")


def test_entity_for_path_falls_back_to_the_system_root(seeded):
    dbConn, _idFolderPath, _categoryFolderPath = seeded
    rootPath = os.path.dirname(db.get_system_folder(dbConn, "root.index")["folder_path"])
    entityType, entityKey, folderPath, label = locate.entity_for_path(dbConn, rootPath, rootPath=rootPath)
    assert entityType == "space:index"
    assert entityKey == "root"
    assert folderPath == rootPath
    assert label == "Index"


def test_entity_for_path_without_root_path_still_raises_at_the_root(seeded):
    dbConn, _idFolderPath, _categoryFolderPath = seeded
    rootPath = os.path.dirname(db.get_system_folder(dbConn, "root.index")["folder_path"])
    with pytest.raises(ValueError):
        locate.entity_for_path(dbConn, rootPath)


def test_entity_for_path_prefers_a_deeper_match_over_the_root(seeded):
    dbConn, idFolderPath, _categoryFolderPath = seeded
    rootPath = os.path.dirname(db.get_system_folder(dbConn, "root.index")["folder_path"])
    entityType, _entityKey, folderPath, _label = locate.entity_for_path(dbConn, idFolderPath, rootPath=rootPath)
    assert entityType == "id"
    assert folderPath == idFolderPath
