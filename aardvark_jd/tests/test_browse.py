import logging

import pytest
import yaml

from aardvark_jd import browse as browse_module, db, paths, picker
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.browse import browse
from aardvark_jd.initialiser import initialiser

log = logging.getLogger("test_browse")
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
    # EXPLICIT EMOJI, SO THE RENDERED LABELS ARE EXACT RATHER THAN WHATEVER THE
    # SUGGESTER HAPPENS TO PICK FOR "HEALTH" ON THE DAY.
    add_area(log=log, dbConn=conn, domain="areas", title="Health", description="d1",
             chosenEmoji="🏥").get()
    add_category(log=log, dbConn=conn, domain="areas", areaRef="A10", title="Doctors", description="d2",
                 chosenEmoji="🩺").get()
    _code, idFolderPath, _details = add_id(
        log=log, dbConn=conn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3"
    ).get()
    settings = {"system": {"name": "Test", "root_path": rootPath}}
    yield conn, settings, idFolderPath
    conn.close()


def _scripted(monkeypatch, *labels):
    """*drive the picker by option label, so tests read as the user's journey*"""
    seen = []

    def fakeSelect(options, title="", readKey=None, stream=None, initialIndex=0):
        wanted = labels[len(seen)]
        seen.append(wanted)
        for value, label in options:
            if label.startswith(wanted):
                return value
        raise AssertionError(f"no option starting {wanted!r} in {[l for _v, l in options]}")

    monkeypatch.setattr(picker, "select_one", fakeSelect)
    return seen


def test_drilling_all_the_way_down_returns_the_id_folder(seeded, monkeypatch):
    conn, settings, idFolderPath = seeded
    _scripted(monkeypatch, "A areas", "A10-19", "A11", "A11.10")
    assert browse(log=log, dbConn=conn, settings=settings).get() == idFolderPath


def test_stopping_at_the_category_returns_the_category_folder(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    _scripted(monkeypatch, "A areas", "A10-19", "A11", "→ open")
    folderPath = browse(log=log, dbConn=conn, settings=settings).get()
    assert "A11_doctors" in folderPath


def test_stopping_at_the_area_returns_the_area_folder(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    _scripted(monkeypatch, "A areas", "A10-19", "→ open")
    folderPath = browse(log=log, dbConn=conn, settings=settings).get()
    assert "A10_19_health" in folderPath


def test_cancelling_at_the_top_returns_none(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    monkeypatch.setattr(picker, "select_one", lambda *a, **k: None)
    assert browse(log=log, dbConn=conn, settings=settings).get() is None


def test_going_back_from_an_area_returns_to_the_domain_list(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    calls = []

    def fakeSelect(options, title="", readKey=None, stream=None, initialIndex=0):
        calls.append(title)
        if len(calls) == 1:
            return next(v for v, label in options if label.startswith("A areas"))
        if len(calls) == 2:
            return next(v for v, label in options if label == "← back")
        return None

    monkeypatch.setattr(picker, "select_one", fakeSelect)
    assert browse(log=log, dbConn=conn, settings=settings).get() is None
    # BACK OUT OF THE AREA LIST, THEN CANCEL THE DOMAIN LIST WE RETURNED TO
    assert len(calls) == 3


def test_an_empty_domain_still_offers_a_way_back(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    labels = []

    def fakeSelect(options, title="", readKey=None, stream=None, initialIndex=0):
        labels.append([label for _value, label in options])
        if len(labels) == 1:
            return next(v for v, label in options if label.startswith("P projects"))
        return None

    monkeypatch.setattr(picker, "select_one", fakeSelect)
    browse(log=log, dbConn=conn, settings=settings).get()
    assert labels[1] == ["← back"]


# ---------------------------------------------------------------------- #
# pre-selecting whatever holds the starting path
# ---------------------------------------------------------------------- #

def _capture_indexes(monkeypatch, *labels):
    """*drive the picker by label, recording the initialIndex offered at each level*"""
    seen = []
    indexes = []

    def fakeSelect(options, title="", readKey=None, stream=None, initialIndex=0):
        indexes.append((initialIndex, [label for _value, label in options]))
        if len(seen) >= len(labels):
            return None
        wanted = labels[len(seen)]
        seen.append(wanted)
        for value, label in options:
            if label.startswith(wanted):
                return value
        raise AssertionError(f"no option starting {wanted!r}")

    monkeypatch.setattr(picker, "select_one", fakeSelect)
    return indexes


def test_the_domain_holding_the_starting_path_is_pre_selected(seeded, monkeypatch):
    conn, settings, idFolderPath = seeded
    indexes = _capture_indexes(monkeypatch, "A areas", "A10-19", "A11", "A11.10")
    browse(log=log, dbConn=conn, settings=settings, startPath=idFolderPath).get()
    # "areas" IS THE FIRST DOMAIN, AND THE ID LIVES INSIDE IT
    domainIndex, domainLabels = indexes[0]
    assert domainLabels[domainIndex].startswith("A areas")


def test_the_area_category_and_id_holding_the_starting_path_are_pre_selected(seeded, monkeypatch):
    conn, settings, idFolderPath = seeded
    indexes = _capture_indexes(monkeypatch, "A areas", "A10-19", "A11", "A11.10")
    browse(log=log, dbConn=conn, settings=settings, startPath=idFolderPath).get()

    for level, expectedPrefix in ((1, "A10-19"), (2, "A11 "), (3, "A11.10")):
        index, labels = indexes[level]
        assert labels[index].startswith(expectedPrefix), (level, labels[index])


def test_a_starting_path_outside_the_system_falls_back_to_the_first_option(seeded, monkeypatch, tmp_path):
    conn, settings, _idFolderPath = seeded
    indexes = _capture_indexes(monkeypatch, "A areas", "← back")
    browse(log=log, dbConn=conn, settings=settings, startPath=str(tmp_path)).get()
    assert indexes[0][0] == 0
    # BELOW THE TOP LEVEL THE FALLBACK IS THE FIRST REAL ROW, PAST "open"/"back"
    assert indexes[1][0] == 1


def test_an_area_starting_path_pre_selects_that_area(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    area = conn.execute("SELECT folder_path FROM areas LIMIT 1").fetchone()
    indexes = _capture_indexes(monkeypatch, "A areas", "A10-19", "→ open")
    browse(log=log, dbConn=conn, settings=settings, startPath=area["folder_path"]).get()
    index, labels = indexes[1]
    assert labels[index].startswith("A10-19")


# ---------------------------------------------------------------------- #
# the picker labels the same things the `fd` listing labels
# ---------------------------------------------------------------------- #

def _labels_offered(monkeypatch, *choices):
    """*walk the picker by label prefix, recording the options offered at each level*"""
    seen = []
    offered = []

    def fakeSelect(options, title="", readKey=None, stream=None, initialIndex=0):
        offered.append([label for _value, label in options])
        if len(seen) >= len(choices):
            return None
        wanted = choices[len(seen)]
        seen.append(wanted)
        for value, label in options:
            if label.startswith(wanted):
                return value
        raise AssertionError(f"no option starting {wanted!r} in {offered[-1]}")

    monkeypatch.setattr(picker, "select_one", fakeSelect)
    return offered


def test_the_picker_labels_an_area_with_its_emoji(seeded, monkeypatch):
    """*the same row rendered in two places should read the same in both*"""
    conn, settings, _idFolderPath = seeded
    offered = _labels_offered(monkeypatch, "A areas")
    browse(log=log, dbConn=conn, settings=settings).get()
    assert "A10-19 🏥 Health" in offered[1]


def test_the_picker_labels_a_category_with_its_emoji(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    offered = _labels_offered(monkeypatch, "A areas", "A10-19")
    browse(log=log, dbConn=conn, settings=settings).get()
    assert "A11 🩺 Doctors" in offered[2]


def test_the_picker_leaves_ids_and_domains_without_an_emoji(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    offered = _labels_offered(monkeypatch, "A areas", "A10-19", "A11")
    browse(log=log, dbConn=conn, settings=settings).get()
    assert "A areas" in offered[0]
    assert "A11.10 Cardiologist" in offered[3]


def test_the_picker_falls_back_for_a_blank_area_emoji(seeded, monkeypatch):
    conn, settings, _idFolderPath = seeded
    conn.execute("UPDATE areas SET emoji = '' WHERE decade_start = 10 AND domain = 'areas'")
    conn.commit()
    offered = _labels_offered(monkeypatch, "A areas")
    browse(log=log, dbConn=conn, settings=settings).get()
    assert "A10-19 📁 Health" in offered[1]
