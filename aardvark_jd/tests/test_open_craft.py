import logging
import subprocess
import sys

import pytest
import yaml

from aardvark_jd import db, doc_links, locate, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.initialiser import initialiser
from aardvark_jd.open_craft import open_craft

log = logging.getLogger("test_open_craft")
log.addHandler(logging.NullHandler())


def _url_for(openedUrls, serviceLabel):
    """*pull one service's URL back out of `open_craft`'s `(label, url)` list, or None*"""
    return next((url for label, url in openedUrls if label == serviceLabel), None)


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
    _code, idFolderPath, _details = add_id(
        log=log, dbConn=conn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3"
    ).get()
    yield conn, idFolderPath, rootPath
    conn.close()


def test_open_craft_raises_when_not_yet_synced(seeded, monkeypatch):
    dbConn, idFolderPath, _rootPath = seeded
    with pytest.raises(ValueError):
        open_craft(log=log, dbConn=dbConn, path=idFolderPath).get()


def test_open_craft_opens_the_linked_url_on_darwin(seeded, monkeypatch):
    dbConn, idFolderPath, _rootPath = seeded
    entityType, entityKey, _folderPath, _label = locate.entity_for_path(dbConn, idFolderPath)
    db.upsert_craft_link(dbConn, entityType, entityKey, craftDocumentId="doc-1", craftUrl="craftdocs://open?blockId=doc-1")

    monkeypatch.setattr(sys, "platform", "darwin")
    captured = {}
    monkeypatch.setattr(subprocess, "run", lambda args, check=False: captured.setdefault("args", args))

    label, openedUrls = open_craft(log=log, dbConn=dbConn, path=idFolderPath).get()
    craftUrl = _url_for(openedUrls, doc_links.CRAFT_LABEL)
    todoistUrl = _url_for(openedUrls, doc_links.TODOIST_LABEL)

    assert label == "Cardiologist"
    assert craftUrl == "craftdocs://open?blockId=doc-1"
    assert todoistUrl is None
    assert captured["args"] == ["open", "craftdocs://open?blockId=doc-1"]


def test_open_craft_uses_webbrowser_off_darwin(seeded, monkeypatch):
    dbConn, idFolderPath, _rootPath = seeded
    entityType, entityKey, _folderPath, _label = locate.entity_for_path(dbConn, idFolderPath)
    db.upsert_craft_link(dbConn, entityType, entityKey, craftDocumentId="doc-1", craftUrl="craftdocs://open?blockId=doc-1")

    monkeypatch.setattr(sys, "platform", "linux")
    captured = {}
    monkeypatch.setattr("webbrowser.open", lambda url: captured.setdefault("url", url))

    open_craft(log=log, dbConn=dbConn, path=idFolderPath).get()

    assert captured["url"] == "craftdocs://open?blockId=doc-1"


def test_open_craft_defaults_to_the_current_directory(seeded, monkeypatch):
    dbConn, idFolderPath, _rootPath = seeded
    entityType, entityKey, _folderPath, _label = locate.entity_for_path(dbConn, idFolderPath)
    db.upsert_craft_link(dbConn, entityType, entityKey, craftDocumentId="doc-1", craftUrl="craftdocs://open?blockId=doc-1")

    monkeypatch.chdir(idFolderPath)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda args, check=False: None)

    label, openedUrls = open_craft(log=log, dbConn=dbConn).get()
    _craftUrl = _url_for(openedUrls, doc_links.CRAFT_LABEL)
    _todoistUrl = _url_for(openedUrls, doc_links.TODOIST_LABEL)
    assert label == "Cardiologist"


def test_open_craft_resolves_the_bare_system_root(seeded, monkeypatch):
    dbConn, _idFolderPath, rootPath = seeded
    db.upsert_craft_link(dbConn, "space:index", "root", craftDocumentId="doc-root", craftUrl="craftdocs://open?blockId=doc-root")

    monkeypatch.setattr(sys, "platform", "darwin")
    captured = {}
    monkeypatch.setattr(subprocess, "run", lambda args, check=False: captured.setdefault("args", args))

    settings = {"system": {"root_path": rootPath}}
    label, openedUrls = open_craft(log=log, dbConn=dbConn, path=rootPath, settings=settings).get()
    craftUrl = _url_for(openedUrls, doc_links.CRAFT_LABEL)
    todoistUrl = _url_for(openedUrls, doc_links.TODOIST_LABEL)

    assert label == "Index"
    assert craftUrl == "craftdocs://open?blockId=doc-root"
    assert todoistUrl is None
    assert captured["args"] == ["open", "craftdocs://open?blockId=doc-root"]


def test_open_craft_without_settings_still_resolves_a_normal_entity(seeded, monkeypatch):
    dbConn, idFolderPath, _rootPath = seeded
    entityType, entityKey, _folderPath, _label = locate.entity_for_path(dbConn, idFolderPath)
    db.upsert_craft_link(dbConn, entityType, entityKey, craftDocumentId="doc-1", craftUrl="craftdocs://open?blockId=doc-1")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda args, check=False: None)

    label, openedUrls = open_craft(log=log, dbConn=dbConn, path=idFolderPath).get()
    _craftUrl = _url_for(openedUrls, doc_links.CRAFT_LABEL)
    _todoistUrl = _url_for(openedUrls, doc_links.TODOIST_LABEL)
    assert label == "Cardiologist"


def test_open_craft_opens_todoist_link_alongside_craft(seeded, monkeypatch):
    dbConn, idFolderPath, _rootPath = seeded
    entityType, entityKey, _folderPath, _label = locate.entity_for_path(dbConn, idFolderPath)
    db.upsert_craft_link(dbConn, entityType, entityKey, craftDocumentId="doc-1", craftUrl="craftdocs://open?blockId=doc-1")
    db.upsert_todoist_link(dbConn, entityType, entityKey, todoistProjectId="proj-1", todoistUrl="https://app.todoist.com/app/project/proj-1")

    monkeypatch.setattr(sys, "platform", "darwin")
    opened = []
    monkeypatch.setattr(subprocess, "run", lambda args, check=False: opened.append(args[1]))

    label, openedUrls = open_craft(log=log, dbConn=dbConn, path=idFolderPath).get()
    craftUrl = _url_for(openedUrls, doc_links.CRAFT_LABEL)
    todoistUrl = _url_for(openedUrls, doc_links.TODOIST_LABEL)

    assert label == "Cardiologist"
    assert craftUrl == "craftdocs://open?blockId=doc-1"
    assert todoistUrl == "https://app.todoist.com/app/project/proj-1"
    assert opened == ["craftdocs://open?blockId=doc-1", "https://app.todoist.com/app/project/proj-1"]


def test_open_craft_opens_todoist_only_when_craft_not_synced(seeded, monkeypatch):
    dbConn, idFolderPath, _rootPath = seeded
    entityType, entityKey, _folderPath, _label = locate.entity_for_path(dbConn, idFolderPath)
    db.upsert_todoist_link(dbConn, entityType, entityKey, todoistProjectId="proj-1", todoistUrl="https://app.todoist.com/app/project/proj-1")

    monkeypatch.setattr(sys, "platform", "darwin")
    opened = []
    monkeypatch.setattr(subprocess, "run", lambda args, check=False: opened.append(args[1]))

    label, openedUrls = open_craft(log=log, dbConn=dbConn, path=idFolderPath).get()
    craftUrl = _url_for(openedUrls, doc_links.CRAFT_LABEL)
    todoistUrl = _url_for(openedUrls, doc_links.TODOIST_LABEL)

    assert label == "Cardiologist"
    assert craftUrl is None
    assert todoistUrl == "https://app.todoist.com/app/project/proj-1"
    assert opened == ["https://app.todoist.com/app/project/proj-1"]
