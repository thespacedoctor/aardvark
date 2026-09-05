import logging
import os

import pytest
import yaml

from aardvark_jd import codes, db, folders, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.archive import archive
from aardvark_jd.initialiser import initialiser

log = logging.getLogger("test_archive")
log.addHandler(logging.NullHandler())


@pytest.fixture
def seeded(tmp_path):
    settingsPath = str(tmp_path / "settings.yaml")
    with open(settingsPath, "w") as stream:
        yaml.safe_dump({"version": 1, "system": {"name": None, "root_path": None}}, stream)
    rootPath = initialiser(
        log=log, systemName="Test", parentPath=str(tmp_path), pathToSettingsFile=settingsPath
    ).get()
    conn = db.get_connection(paths.find_db_path(rootPath))
    add_area(log=log, dbConn=conn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=conn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=conn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    add_id(log=log, dbConn=conn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()
    settings = {"system": {"name": "Test", "root_path": rootPath}}
    yield conn, rootPath, settings
    conn.close()


def test_archiving_an_id_moves_it_into_the_category_archive(seeded):
    conn, _rootPath, settings = seeded
    code, archivedPath, _warnings = archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()

    assert code == "A11.10"
    assert "A11.09_archive" in archivedPath
    assert os.path.isdir(archivedPath)


def test_the_archived_folder_name_carries_a_datestamp(seeded):
    conn, _rootPath, settings = seeded
    _code, archivedPath, _warnings = archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()
    assert "__archived_" in os.path.basename(archivedPath)


def test_an_archived_id_leaves_the_live_index(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()
    assert db.get_id(conn, "areas", 11, 10) is None


def test_an_archived_id_is_recorded(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()
    rows = db.list_archived_entities(conn)
    assert [row["code"] for row in rows] == ["A11.10"]
    assert rows[0]["title"] == "Cardiologist"
    assert rows[0]["original_path"] != rows[0]["archived_path"]


def test_an_archived_id_drops_out_of_search(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()
    hits = conn.execute(
        "SELECT count(*) FROM search_index WHERE title = 'Cardiologist'"
    ).fetchone()[0]
    assert hits == 0


def test_the_freed_id_number_is_handed_to_the_next_id(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()
    code, _folderPath, _details = add_id(
        log=log, dbConn=conn, domain="areas", categoryRef="A11", title="Podiatrist", description="d5"
    ).get()
    assert code == "A11.10"


def test_archiving_a_category_moves_it_into_the_area_archive(seeded):
    conn, _rootPath, settings = seeded
    code, archivedPath, _warnings = archive(log=log, dbConn=conn, ref="A11", settings=settings).get()
    assert code == "A11"
    assert "A10.09_archive" in archivedPath
    assert os.path.isdir(archivedPath)


def test_archiving_a_category_records_its_ids_too(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A11", settings=settings).get()
    codes_ = sorted(row["code"] for row in db.list_archived_entities(conn))
    assert codes_ == ["A11", "A11.10", "A11.11"]


def test_archiving_a_category_clears_its_reserved_scaffolding_rows(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A11", settings=settings).get()
    remaining = conn.execute(
        "SELECT count(*) FROM system_folders WHERE folder_key LIKE 'areas.11.%'"
    ).fetchone()[0]
    assert remaining == 0


def test_a_reused_category_number_gets_its_own_fresh_scaffolding(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A11", settings=settings).get()
    code, folderPath = add_category(
        log=log, dbConn=conn, domain="areas", areaRef="A10", title="Physio", description="d6"
    ).get()
    assert code == "A11"
    rows = conn.execute(
        "SELECT folder_path FROM system_folders WHERE folder_key LIKE 'areas.11.%'"
    ).fetchall()
    assert len(rows) == 10
    assert all(row["folder_path"].startswith(folderPath) for row in rows)


def test_archiving_an_area_moves_it_into_the_domain_archive(seeded):
    conn, _rootPath, settings = seeded
    code, archivedPath, _warnings = archive(log=log, dbConn=conn, ref="A10-19", settings=settings).get()
    assert code == "A10-19"
    assert "A09_archive" in archivedPath
    assert os.path.isdir(archivedPath)


def test_archiving_an_area_records_every_descendant(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A10-19", settings=settings).get()
    codes_ = sorted(row["code"] for row in db.list_archived_entities(conn))
    assert codes_ == ["A10-19", "A11", "A11.10", "A11.11"]


def test_the_freed_decade_is_handed_to_the_next_area(seeded):
    conn, _rootPath, settings = seeded
    archive(log=log, dbConn=conn, ref="A10-19", settings=settings).get()
    code, _folderPath = add_area(
        log=log, dbConn=conn, domain="areas", title="Finance", description="d7"
    ).get()
    assert code == "A10-19"


def test_descendant_folder_paths_follow_the_move(seeded):
    conn, _rootPath, settings = seeded
    _code, archivedPath, _warnings = archive(log=log, dbConn=conn, ref="A11", settings=settings).get()
    idRow = next(
        row for row in db.list_archived_entities(conn) if row["code"] == "A11.10"
    )
    assert idRow["archived_path"].startswith(archivedPath)
    assert not idRow["original_path"].startswith(archivedPath)


def test_an_unknown_ref_raises(seeded):
    conn, _rootPath, settings = seeded
    with pytest.raises(ValueError):
        archive(log=log, dbConn=conn, ref="A11.99", settings=settings).get()


def test_a_non_johnny_decimal_ref_raises(seeded):
    conn, _rootPath, settings = seeded
    with pytest.raises(ValueError):
        archive(log=log, dbConn=conn, ref="root.areas", settings=settings).get()


def test_archiving_never_touches_the_index_database(seeded):
    """00_INDEX holds the open sqlite file - it must never be movable"""
    conn, rootPath, settings = seeded
    indexFolder = os.path.dirname(paths.find_db_path(rootPath))
    target = archive(log=log, dbConn=conn, ref="A11.10", settings=settings)
    with pytest.raises(ValueError):
        target._guard(indexFolder)


def test_a_second_archive_of_a_reused_number_does_not_collide(seeded):
    """the datestamp is what stops two A11.10s landing on top of each other"""
    conn, _rootPath, settings = seeded
    _c1, firstPath, _w1 = archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()
    add_id(log=log, dbConn=conn, domain="areas", categoryRef="A11", title="Podiatrist", description="d5").get()
    _c2, secondPath, _w2 = archive(log=log, dbConn=conn, ref="A11.10", settings=settings).get()
    assert firstPath != secondPath
    assert os.path.isdir(firstPath) and os.path.isdir(secondPath)
