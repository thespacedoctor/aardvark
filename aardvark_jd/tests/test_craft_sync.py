import logging
import os

import pytest
import yaml

from aardvark_jd import background_sync
from aardvark_jd import craft_sync as craft_sync_module
from aardvark_jd import db, paths
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.craft_client import CraftApiError
from aardvark_jd.craft_sync import craft_sync
from aardvark_jd.initialiser import initialiser

log = logging.getLogger("test_craft_sync")
log.addHandler(logging.NullHandler())


class FakeCraftClient(object):
    """*records every folder/document/block created or deleted, without any HTTP calls*

    Models the real API's read-delete-insert index refresh. `add_block`
    splits multi-line markdown into **one block per line**, each with its
    own id, because that is what a real `POST /blocks` does (confirmed
    against the live space: a six-line index document comes back as six
    sibling content items). `get_block` reads those per-line items back
    with their markdown, `delete_blocks` removes matching ids, and a
    document's content is therefore `[link row] + [one item per index
    line]` - the shape `_write_index_content` compares against.

    `blocksAdded` records one entry per `add_block` **call**, not per
    resulting block, so it stays a count of API calls made.
    """

    def __init__(self, apiUrl, apiToken):
        self.apiUrl = apiUrl
        self.apiToken = apiToken
        self._counter = 0
        self.folders = []
        self.documents = []
        self.blocksAdded = []
        self.blocksDeleted = []
        self._documentContent = {}
        self.listFolderCalls = 0
        self.listDocumentCalls = 0

    def _next_id(self, prefix):
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def list_folders(self):
        """*rebuild the nested tree the real `GET /folders` returns, from what's been created*"""
        self.listFolderCalls += 1

        def children_of(parentFolderId):
            return [
                {"id": folderId, "name": name, "folders": children_of(folderId)}
                for folderId, name, parent in self.folders if parent == parentFolderId
            ]

        return children_of(None)

    def folder_deep_link(self, folderId, title):
        return f"craftdocs://openfolder?folderId={folderId}&spaceId=space-1&title={title}"

    def create_folder(self, name, parentFolderId=None):
        folderId = self._next_id("folder")
        self.folders.append((folderId, name, parentFolderId))
        return folderId

    def create_document(self, title, folderId=None):
        documentId = self._next_id("doc")
        self.documents.append((documentId, title, folderId))
        self._documentContent[documentId] = []
        return documentId, f"https://craft.example/doc/{documentId}"

    def list_documents(self, folderId):
        self.listDocumentCalls += 1
        return [
            {"id": documentId, "title": title}
            for documentId, title, parent in self.documents
            if parent == folderId
        ]

    def _deep_link(self, itemId):
        return f"https://craft.example/doc/{itemId}"

    def add_block(self, documentId, markdown, position="end"):
        # CRAFT STRIPS TRAILING WHITESPACE FROM A BLOCK'S MARKDOWN WHEN IT STORES
        # IT - CONFIRMED AGAINST THE LIVE SPACE, WHERE A DESCRIPTION-LESS ENTRY
        # SENT AS `... — ` COMES BACK AS `... —`.
        items = [(self._next_id("block"), line.rstrip()) for line in markdown.split("\n")]
        self.blocksAdded.append((documentId, markdown, items[0][0]))
        existing = self._documentContent.setdefault(documentId, [])
        if position == "start":
            self._documentContent[documentId] = items + existing
        else:
            existing.extend(items)
        return items[0][0]

    def get_block(self, blockId):
        content = self._documentContent.get(blockId, [])
        return {"id": blockId, "content": [{"id": bId, "markdown": md} for bId, md in content]}

    def delete_blocks(self, blockIds):
        self.blocksDeleted.extend(blockIds)
        blockIdSet = set(blockIds)
        for documentId, items in self._documentContent.items():
            self._documentContent[documentId] = [(bId, md) for bId, md in items if bId not in blockIdSet]

    def index_bodies(self):
        """*every index markdown body ever added, in write order - includes content later replaced*"""
        return [markdown for _documentId, markdown, _blockId in self.blocksAdded]


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
def craftSettings(dbConn):
    # `system.root_path` is always populated by the time real code ever
    # constructs `craft_sync` - `cl_utils.main` refuses to proceed without
    # it - so this fixture derives the real root from `dbConn` rather than
    # leaving it unset, matching what every caller actually sees.
    rootPath = os.path.dirname(db.get_system_folder(dbConn, "root.index")["folder_path"])
    return {
        "craft": {"enabled": True, "api_url": "https://connect.craft.do/links/abc123/api/v1", "api_token": "fake-token"},
        "system": {"root_path": rootPath},
    }


@pytest.fixture
def fakeClient(monkeypatch):
    client = FakeCraftClient(apiUrl="https://connect.craft.do/links/abc123/api/v1", apiToken="fake-token")
    monkeypatch.setattr(craft_sync_module, "CraftClient", lambda apiUrl, apiToken, budget=None, announce=None: client)
    return client


def test_craft_sync_requires_enabled(dbConn):
    with pytest.raises(ValueError):
        craft_sync(log=log, dbConn=dbConn, settings={"craft": {"enabled": False}}).get()


def test_craft_sync_requires_api_url_and_token(dbConn):
    with pytest.raises(ValueError):
        craft_sync(log=log, dbConn=dbConn, settings={"craft": {"enabled": True}}).get()
    with pytest.raises(ValueError):
        craft_sync(log=log, dbConn=dbConn, settings={"craft": {"enabled": True, "api_url": "https://x"}}).get()
    with pytest.raises(ValueError):
        craft_sync(log=log, dbConn=dbConn, settings={"craft": {"enabled": True, "api_token": "tok"}}).get()


def test_craft_sync_mirrors_root_folders(dbConn, craftSettings, fakeClient):
    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    # craft folder names mirror the on-disk names, underscores rendered as spaces
    # and the emoji carried in the name itself (craft has no folder icon field)
    folderNames = {name for _id, name, _parent in fakeClient.folders}
    assert {"01 INBOX📥", "02 PROJECTS🚀", "03 AREAS🧭", "04 RESOURCES📚", "09 ARCHIVE🗄️"} <= folderNames
    assert summary["folders_created"] >= 5

    # the space-root index should link out to all five, and only those five -
    # it's written last, immediately followed by its own Finder/Dropbox link
    # row (see `_refresh_index`), so it's the second-to-last block added
    spaceIndexBody = fakeClient.blocksAdded[-2][1]
    for title in ("01 INBOX📥", "02 PROJECTS🚀", "03 AREAS🧭", "04 RESOURCES📚", "09 ARCHIVE🗄️"):
        assert title in spaceIndexBody

    # folders are linked with a craftdocs://openfolder deep link, not left as plain text
    assert "[01 INBOX📥](craftdocs://openfolder?folderId=" in spaceIndexBody


def test_craft_sync_mirrors_area_category_id_nesting(dbConn, craftSettings, fakeClient):
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    # the decade range keeps its hyphen; everything else mirrors the (lowercased) disk
    # name. the trailing emoji is auto-picked, so match on the prefix only
    folderTitles = {name for _id, name, _parent in fakeClient.folders}
    assert any(name.startswith("A10-19 health") for name in folderTitles)
    assert any(name.startswith("A11 doctors") for name in folderTitles)

    documentTitles = {title for _id, title, _folder in fakeClient.documents}
    assert any(title.startswith("A11.10 cardiologist") for title in documentTitles)

    # the category's own "00 Index" should list the new ID one level down
    assert any("A11.10 cardiologist" in body and "d3" in body for body in fakeClient.index_bodies())


def test_craft_sync_mirrors_an_id_as_a_folder_with_an_inner_index_document(dbConn, craftSettings, fakeClient):
    """*an ID mirrors as a Craft folder (not a bare document), carrying a single "00 Index" document inside it*"""
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    byName = {name: (folderId, parent) for folderId, name, parent in fakeClient.folders}
    categoryFolderId = next(fid for name, (fid, _p) in byName.items() if name.startswith("A11 doctors"))
    idFolderId, idFolderParent = next(
        (fid, parent) for name, (fid, parent) in byName.items() if name.startswith("A11.10 cardiologist")
    )
    assert idFolderParent == categoryFolderId

    idDocumentId, idDocumentTitle, idDocumentFolder = next(
        (docId, title, folder) for docId, title, folder in fakeClient.documents
        if title.startswith("A11.10 cardiologist")
    )
    assert idDocumentFolder == idFolderId

    # the id's own "00 Index" document carries the Finder link row (Darwin only)
    assert any("Finder" in md for _docId, md, _blockId in fakeClient.blocksAdded if _docId == idDocumentId)

    # the category's index links to the id's *folder*, not its inner document
    link = db.get_craft_link(dbConn, "id", "1")
    assert link["craft_folder_id"] == idFolderId
    assert "craftdocs://openfolder" in link["craft_url"]


def test_craft_sync_id_index_document_is_untouched_on_resync(dbConn, craftSettings, fakeClient):
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    documentsAfterFirst = len(fakeClient.documents)
    foldersAfterFirst = len(fakeClient.folders)

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert len(fakeClient.documents) == documentsAfterFirst
    assert len(fakeClient.folders) == foldersAfterFirst
    assert summary["documents_created"] == 0
    assert summary["folders_created"] == 0


def test_craft_sync_mirrors_the_three_level_system_scaffolding(dbConn, craftSettings, fakeClient):
    """*domain- and area-level system folders, and their reserved subfolders, mirror three levels deep*"""
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    byName = {name: (folderId, parent) for folderId, name, parent in fakeClient.folders}
    documentTitles = {title for _id, title, _folder in fakeClient.documents}

    # the domain's own system folder nests under the domain root, alongside its areas
    areasRootId, _ = byName["03 AREAS🧭"]
    domainSystemFolderId, domainSystemParent = byName["A00-09 system⚙️"]
    assert domainSystemParent == areasRootId

    # the area's own system folder nests under the area, alongside its categories
    areaFolderId = next(fid for name, (fid, _p) in byName.items() if name.startswith("A10-19 health"))
    areaSystemFolderId, areaSystemParent = byName["A10 system⚙️"]
    assert areaSystemParent == areaFolderId

    # a folder-kind reserved subfolder mirrors as a Craft folder, nested inside the system folder
    _inboxFolderId, inboxParent = byName["A10.01 inbox📥"]
    assert inboxParent == areaSystemFolderId

    # a document-kind reserved subfolder mirrors as a Craft document, not a folder
    assert "A10.02 llm🤖" not in byName
    assert any(title.startswith("A10.02 llm") for title in documentTitles)

    # the area's reserved `.00_index` document is now ITS index, listing the area's
    # categories - there's no more free-standing "00 Index" document at area level
    assert any("A11 doctors" in body and "d2" in body for body in fakeClient.index_bodies())

    # a category has no system folder of its own - its reserved subfolders sit directly
    # inside the category folder, alongside its user-created ids
    categoryFolderId = next(fid for name, (fid, _p) in byName.items() if name.startswith("A11 doctors"))
    _catInboxId, catInboxParent = byName["A11.01 inbox📥"]
    assert catInboxParent == categoryFolderId

    # the domain-root system folder's own index lists this domain's areas - also no
    # longer a free-standing "00 Index" document directly under the domain root
    assert any("A10-19 health" in body and "d1" in body for body in fakeClient.index_bodies())


def test_craft_sync_nests_areas_under_their_domain_root(dbConn, craftSettings, fakeClient):
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    byName = {name: (folderId, parent) for folderId, name, parent in fakeClient.folders}
    areasRootId, _ = byName["03 AREAS🧭"]
    areaParents = [parent for name, (_id, parent) in byName.items() if name.startswith("A10-19 health")]
    assert areaParents == [areasRootId]


def test_craft_sync_adopts_folders_already_in_the_space(dbConn, craftSettings, fakeClient):
    """*a folder matching by name+parent is reused, not duplicated - craft re-keys folder ids*"""
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    foldersAfterFirst = list(fakeClient.folders)

    # craft re-keys every folder id behind our back, exactly as the live API does - the
    # nesting itself is untouched, so parent references are rekeyed the same way
    def rekey(folderId):
        return f"rekeyed-{folderId}" if folderId is not None else None

    fakeClient.folders = [
        (rekey(folderId), name, rekey(parent)) for folderId, name, parent in foldersAfterFirst
    ]

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert summary["folders_created"] == 0
    assert len(fakeClient.folders) == len(foldersAfterFirst)
    # the link table should have been refreshed onto the new ids
    link = db.get_craft_link(dbConn, "system_folder", "root.areas")
    assert link["craft_folder_id"].startswith("rekeyed-")
    assert "rekeyed-" in link["craft_url"]


def _index_document_content(fakeClient, dbConn, folderKey):
    """*the live content items of a reserved `.00_index` document, in document order*"""
    link = db.get_craft_link(dbConn, "system_folder", folderKey)
    return fakeClient.get_block(link["craft_document_id"])["content"]


def test_craft_sync_skips_rewriting_an_unchanged_index_document(dbConn, craftSettings, fakeClient):
    """*an unchanged index document costs its `GET` and nothing else - no delete, no insert*

    This is the assertion ticket 09 exists for: it pins that the skip
    *actually happens*, rather than that the output merely looks right. A
    comparison normalised wrongly in the "safe" direction would still
    produce correct content while silently rewriting all 28 index
    documents every run.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert fakeClient.blocksAdded == []
    assert fakeClient.blocksDeleted == []
    assert summary["indexes_refreshed"] == 0
    assert summary["link_rows_written"] == 0


def test_an_index_entry_with_no_description_still_converges(dbConn, craftSettings, fakeClient):
    """*a child with an empty description does not rewrite its index document forever*

    `add_project` always stores an empty description, and the listing
    format puts the description after an em-dash, so such a child renders
    as `- [code title](url) — ` with a **trailing space**. Craft strips
    trailing whitespace when it stores a block, so the stored line never
    equals the computed one and the document rewrites on every single run.
    Observed live: two of the 28 index documents never converged until the
    comparison normalised for it.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert summary["indexes_refreshed"] == 0
    assert fakeClient.blocksAdded == []
    assert fakeClient.blocksDeleted == []


def test_craft_sync_rewrites_an_index_document_when_a_child_is_added(dbConn, craftSettings, fakeClient):
    """*a changed index document is rewritten, and its link row is force-rewritten with it*"""
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()
    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert summary["indexes_refreshed"] == 1
    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    bodyLines = [item["markdown"] for item in content]
    assert any("A11.11 dermatologist" in line and "d4" in line for line in bodyLines)
    # THE LINK ROW SURVIVES THE REWRITE, AND IS STILL THE DOCUMENT'S FIRST BLOCK.
    assert "Finder" in bodyLines[0]


def test_the_link_row_rewrite_is_coupled_to_the_content_rewrite(dbConn, craftSettings, fakeClient):
    """*`forceRewrite` follows whether the body was actually wiped, in both directions*

    Skipping the content rewrite while still forcing the link-row rewrite
    would silently reintroduce most of the saving; forcing neither when the
    content *did* change would leave `craft_links.craft_block_id` pointing
    at a block that has just been deleted, and the link row would be lost.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    def link_row_block_id():
        return db.get_craft_link(dbConn, "system_folder", "areas.11.00_index")["craft_block_id"]

    # UNCHANGED: NO CONTENT REWRITE, SO NO FORCED LINK-ROW REWRITE EITHER - THE
    # RECORDED BLOCK ID STILL POINTS AT A LIVE BLOCK, SO IT MUST NOT BE REPLACED.
    blockIdBefore = link_row_block_id()
    unchanged = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    assert unchanged["indexes_refreshed"] == 0
    assert unchanged["link_rows_written"] == 0
    assert link_row_block_id() == blockIdBefore

    # CHANGED: THE BODY IS WIPED, SO THIS DOCUMENT'S LINK ROW MUST BE REWRITTEN -
    # A NEW BLOCK ID IS THE PROOF THAT `forceRewrite` WAS PASSED THROUGH.
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()
    changed = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    assert changed["indexes_refreshed"] == 1
    assert link_row_block_id() != blockIdBefore

    # AND THE DOCUMENT IS NOT LEFT CORRUPT: LINK ROW FIRST, THEN THE BODY.
    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    assert "Finder" in content[0]["markdown"]
    assert all(item["markdown"].startswith("- ") for item in content[1:])


def test_craft_sync_rewrites_an_index_document_when_a_child_is_removed(dbConn, craftSettings, fakeClient):
    """*removing a child rewrites its parent index, and the link row is force-rewritten with it*"""
    from aardvark_jd.archive import archive

    archiveSettings = {"craft": {"enabled": False}, "system": craftSettings["system"]}
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    archive(log=log, dbConn=dbConn, ref="A11.10", settings=archiveSettings).get()
    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert summary["indexes_refreshed"] == 1
    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    bodyLines = [item["markdown"] for item in content]
    assert not any("cardiologist" in line for line in bodyLines)
    assert any("dermatologist" in line for line in bodyLines)
    # THE LINK ROW SURVIVES THE REWRITE, STILL THE DOCUMENT'S FIRST BLOCK.
    assert "Finder" in bodyLines[0]


def test_craft_sync_converges_an_empty_index_document(dbConn, craftSettings, fakeClient):
    """*a childless index renders the placeholder and still converges to zero writes on resync*

    The `*(nothing here yet)*` body is the `else` branch of the listing
    builder, and it has to round-trip through the comparison the same way
    a populated body does - otherwise every empty index document rewrites
    on every run.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    # NO ids ADDED, SO THE CATEGORY'S `.00_index` BODY IS THE PLACEHOLDER.
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    assert any("nothing here yet" in item["markdown"] for item in content)

    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()
    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert summary["indexes_refreshed"] == 0
    assert fakeClient.blocksAdded == []
    assert fakeClient.blocksDeleted == []


def test_craft_sync_restores_a_hand_deleted_link_row(dbConn, craftSettings, fakeClient):
    """*a link row deleted by hand is re-added on the next sync, though the body still matches*

    The comparison must include the expected link row, not just the body.
    An index document whose link row someone removed in Craft still has a
    body that equals the computed listing exactly, so a body-only
    comparison skips it and the row never heals. `develop`'s
    unconditional rewrite restored it on every run.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    link = db.get_craft_link(dbConn, "system_folder", "areas.11.00_index")
    documentId = link["craft_document_id"]
    assert "Finder" in fakeClient._documentContent[documentId][0][1]
    # HAND-DELETE THE LINK-ROW BLOCK, LEAVING A BODY THAT STILL MATCHES THE LISTING.
    fakeClient._documentContent[documentId] = fakeClient._documentContent[documentId][1:]

    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()
    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert summary["indexes_refreshed"] == 1
    healed = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    assert "Finder" in healed[0]["markdown"]
    assert all(item["markdown"].startswith("- ") for item in healed[1:])


def test_craft_sync_replaces_a_missing_tracked_link_row_block(dbConn, craftSettings, fakeClient, monkeypatch):
    """*a link-row block deleted outside aardvark does not abort its later rewrite*"""
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    link = db.get_craft_link(dbConn, "id:index", "1")
    missingBlockId = link["craft_block_id"]

    monkeypatch.setattr(craft_sync_module.doc_links, "hookmark_url", lambda folderPath: "hook://changed")
    realDelete = fakeClient.delete_blocks

    def delete_blocks_or_not_found(blockIds):
        if missingBlockId in blockIds:
            realDelete(blockIds)
            raise CraftApiError(
                "craft API DELETE /blocks failed (404): Block not found",
                method="DELETE", path="/blocks", statusCode=404,
            )
        realDelete(blockIds)

    fakeClient.delete_blocks = delete_blocks_or_not_found

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    recoveredLink = db.get_craft_link(dbConn, "id:index", "1")
    assert recoveredLink["craft_block_id"] != missingBlockId
    assert "hook://changed" in recoveredLink["links_markdown"]


def test_craft_sync_recovers_a_stale_link_row_document_id_after_a_post_not_found(
    dbConn, craftSettings, fakeClient, monkeypatch,
):
    """*a link-row write creates a fresh document after Craft rejects its stored page id*"""
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    link = db.get_craft_link(dbConn, "id:index", "1")
    originalId = link["craft_document_id"]

    dbConn.execute(
        "UPDATE craft_links SET craft_document_id = ? WHERE entity_type = ? AND entity_key = ?",
        ("stale-document", "id:index", "1"),
    )
    dbConn.commit()
    monkeypatch.setattr(craft_sync_module.doc_links, "hookmark_url", lambda folderPath: "hook://changed")
    realAdd = fakeClient.add_block

    def add_block_or_not_found(documentId, markdown, position="end"):
        if documentId == "stale-document":
            raise CraftApiError(
                "craft API POST /blocks failed (404): Block not found",
                method="POST", path="/blocks", statusCode=404,
            )
        return realAdd(documentId, markdown, position=position)

    fakeClient.add_block = add_block_or_not_found

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    recoveredLink = db.get_craft_link(dbConn, "id:index", "1")
    assert recoveredLink["craft_document_id"] not in {"stale-document", originalId}
    assert any(document[0] == recoveredLink["craft_document_id"] for document in fakeClient.documents)
    assert summary["documents_repaired"] == 1
    assert "hook://changed" in recoveredLink["links_markdown"]


def test_index_comparison_is_exact_when_no_link_row_is_present(dbConn, craftSettings, fakeClient, monkeypatch):
    """*with no link row, a removed first child is still detected and repaired*

    Off Darwin, with no Dropbox or Drive link, `_write_link_row` writes
    nothing and an index document is body-only. The earlier tail-only
    comparison treated a body-only document's first block as a possible
    link row, so dropping exactly the first child produced a tail that
    lined up, the comparison returned a false match, and the removed
    entry stayed in the document forever.
    """
    monkeypatch.setattr(craft_sync_module.doc_links, "hookmark_url", lambda folderPath: None)
    from aardvark_jd.archive import archive

    archiveSettings = {"craft": {"enabled": False}, "system": craftSettings["system"]}
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    assert "Finder" not in content[0]["markdown"]
    assert "cardiologist" in content[0]["markdown"]

    archive(log=log, dbConn=dbConn, ref="A11.10", settings=archiveSettings).get()
    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()
    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert summary["indexes_refreshed"] == 1
    healed = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    assert not any("cardiologist" in item["markdown"] for item in healed)


def test_a_link_row_with_no_remaining_source_stops_churning_its_index(dbConn, craftSettings, fakeClient, monkeypatch):
    """*when every link source is gone, the recorded row is cleared, not compared against forever*

    Off Darwin with no Dropbox/Drive/Todoist link, `_write_link_row` can
    write nothing. If it also left `craft_links.links_markdown` set, the
    index-content comparison would expect a link row the document no
    longer has and rewrite it on every single run.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    assert db.get_craft_link(dbConn, "system_folder", "areas.11.00_index")["links_markdown"]

    # LOSE THE LAST LINK SOURCE, AND MAKE A CHANGE THAT REWRITES THE INDEX.
    monkeypatch.setattr(craft_sync_module.doc_links, "hookmark_url", lambda folderPath: None)
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert not db.get_craft_link(dbConn, "system_folder", "areas.11.00_index")["links_markdown"]

    fakeClient.blocksAdded.clear()
    fakeClient.blocksDeleted.clear()
    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    assert summary["indexes_refreshed"] == 0
    assert fakeClient.blocksAdded == []
    assert fakeClient.blocksDeleted == []


def test_a_failed_index_rewrite_leaves_content_not_an_empty_document(dbConn, craftSettings, fakeClient):
    """*a rate limit landing mid-rewrite leaves the document holding content, never empty*

    `_write_index_content` inserts the new body before deleting the old
    one, so a failure between the two calls leaves the document briefly
    doubled rather than silently empty - which the next whole-tree repair
    then reconciles.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()

    realDelete = fakeClient.delete_blocks

    def deleteThatFails(blockIds):
        raise CraftApiError("craft API DELETE /blocks failed (429): rate limited mid-rewrite")

    fakeClient.delete_blocks = deleteThatFails
    with pytest.raises(CraftApiError):
        craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    fakeClient.delete_blocks = realDelete

    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    bodyText = " ".join(item["markdown"] for item in content)
    assert content != []
    # THE NEW BODY WAS INSERTED BEFORE THE DELETE FAILED.
    assert "dermatologist" in bodyText


def test_craft_sync_is_idempotent(dbConn, craftSettings, fakeClient):
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    foldersAfterFirst = len(fakeClient.folders)
    documentsAfterFirst = len(fakeClient.documents)
    blocksAddedAfterFirst = len(fakeClient.blocksAdded)

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert len(fakeClient.folders) == foldersAfterFirst
    assert len(fakeClient.documents) == documentsAfterFirst
    assert summary["folders_created"] == 0
    assert summary["documents_created"] == 0
    # nothing changed between the two runs, so the second one writes nothing at all:
    # each index document is read, compared against the listing it already holds, and
    # left alone - and because its content was never wiped, its link row keeps a valid
    # recorded block id and is skipped too. A repair run over an unchanged tree is now
    # reads only, which is what took the whole-tree walk back under Craft's rate limit.
    assert summary["indexes_refreshed"] == 0
    assert summary["link_rows_written"] == 0
    assert fakeClient.blocksDeleted == []
    assert len(fakeClient.blocksAdded) == blocksAddedAfterFirst


def test_craft_sync_mirrors_the_projects_domain_like_areas_and_resources(dbConn, craftSettings, fakeClient):
    from aardvark_jd.add_project import add_project

    add_area(log=log, dbConn=dbConn, domain="projects", title="Launches", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="projects", areaRef="P10", title="Website", description="d2").get()
    add_project(log=log, dbConn=dbConn, categoryRef="P11", templateName="blank", projectTitle="Relaunch").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    byName = {name: (folderId, parent) for folderId, name, parent in fakeClient.folders}
    projectsRootId, _ = byName["02 PROJECTS🚀"]
    areaFolderId, areaParent = next(
        (fid, parent) for name, (fid, parent) in byName.items() if name.startswith("P10-19 launches")
    )
    assert areaParent == projectsRootId
    categoryFolderId, categoryParent = next(
        (fid, parent) for name, (fid, parent) in byName.items() if name.startswith("P11 website")
    )
    assert categoryParent == areaFolderId

    documentTitles = {title for _id, title, _folder in fakeClient.documents}
    assert any(title.startswith("P11.10 relaunch") for title in documentTitles)


# ---------------------------------------------------------------------- #
# document adoption
# ---------------------------------------------------------------------- #

def _filed_documents(client):
    """*the documents that live inside a folder, which are the ones adoption can reach*"""
    return [entry for entry in client.documents if entry[2] is not None]


def test_craft_sync_adopts_a_document_when_its_link_row_is_missing(dbConn, craftSettings, fakeClient):
    """a rebuilt index, a v4 migration or an archive can drop the link row"""
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    filedBefore = _filed_documents(fakeClient)

    # WIPE EVERY RECORDED DOCUMENT ID, AS A LOST DATABASE WOULD
    dbConn.execute("UPDATE craft_links SET craft_document_id = NULL, craft_url = NULL")
    dbConn.commit()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    # EVERY DOCUMENT THAT LIVES IN A FOLDER IS ADOPTED RATHER THAN REMADE.
    # THE SPACE-ROOT INDEX IS UNFILED (`folderId` OF `None`), SO IT CANNOT BE
    # LOOKED UP AND IS THE ONE DOCUMENT STILL RECREATED - SEE `_adopt_document`.
    assert _filed_documents(fakeClient) == filedBefore


def test_craft_sync_relinks_the_adopted_document(dbConn, craftSettings, fakeClient):
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    linkRow = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")
    before = linkRow["craft_document_id"] if linkRow else None

    dbConn.execute("UPDATE craft_links SET craft_document_id = NULL, craft_url = NULL")
    dbConn.commit()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    after = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")["craft_document_id"]
    assert after == before


def test_craft_sync_recovers_a_stale_index_document_id_by_creating_a_replacement_never_adopting(
    dbConn, craftSettings, fakeClient,
):
    """*a 404 on a persisted index document id creates a fresh document, never binding a same-title one*

    A same-title document sitting in the folder is not proof of ownership.
    Adopting it would let the index writer delete an unrelated user page's
    content wholesale, so recovery always creates a new document instead.
    """
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    link = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")
    sameTitleId = link["craft_document_id"]
    sameTitleContentBefore = list(fakeClient._documentContent[sameTitleId])

    # MODEL A DOCUMENT ID CRAFT HAS REMOVED WHILE A SAME-TITLE DOCUMENT REMAINS FILED.
    dbConn.execute(
        "UPDATE craft_links SET craft_document_id = ?, craft_block_id = ?, craft_url = ?, links_markdown = ? "
        "WHERE entity_type = ? AND entity_key = ?",
        ("stale-document", "stale-block", "https://craft.example/doc/stale-document", "stale link row", "system_folder", "areas.system.00_index"),
    )
    dbConn.commit()
    originalGetBlock = fakeClient.get_block

    def get_block_or_not_found(blockId):
        if blockId == "stale-document":
            raise CraftApiError(
                "craft API GET /blocks failed (404): Block not found",
                method="GET", path="/blocks", statusCode=404,
            )
        return originalGetBlock(blockId)

    fakeClient.get_block = get_block_or_not_found

    summary = craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    recoveredLink = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")
    newId = recoveredLink["craft_document_id"]
    assert newId not in {"stale-document", sameTitleId}
    assert any(document[0] == newId for document in fakeClient.documents)
    assert summary["documents_repaired"] == 1
    assert recoveredLink["craft_block_id"] != "stale-block"
    assert recoveredLink["craft_url"] != "https://craft.example/doc/stale-document"
    assert recoveredLink["links_markdown"] != "stale link row"
    # THE SAME-TITLE DOCUMENT ALREADY IN THE FOLDER IS LEFT EXACTLY AS IT WAS.
    assert any(document[0] == sameTitleId for document in fakeClient.documents)
    assert fakeClient._documentContent[sameTitleId] == sameTitleContentBefore


def test_craft_sync_recovers_a_stale_index_document_id_by_creating_a_replacement(
    dbConn, craftSettings, fakeClient,
):
    """*a stale index document without a same-title replacement is recreated once*"""
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    link = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")
    originalId = link["craft_document_id"]

    fakeClient.documents = [document for document in fakeClient.documents if document[0] != originalId]
    del fakeClient._documentContent[originalId]
    dbConn.execute(
        "UPDATE craft_links SET craft_document_id = ? WHERE entity_type = ? AND entity_key = ?",
        ("stale-document", "system_folder", "areas.system.00_index"),
    )
    dbConn.commit()
    originalGetBlock = fakeClient.get_block

    def get_block_or_not_found(blockId):
        if blockId == "stale-document":
            raise CraftApiError(
                "craft API GET /blocks failed (404): Block not found",
                method="GET", path="/blocks", statusCode=404,
            )
        return originalGetBlock(blockId)

    fakeClient.get_block = get_block_or_not_found

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    recoveredLink = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")
    assert recoveredLink["craft_document_id"] not in {originalId, "stale-document"}
    assert any(document[0] == recoveredLink["craft_document_id"] for document in fakeClient.documents)


def test_craft_sync_aborts_after_too_many_stale_document_ids(dbConn, craftSettings, fakeClient):
    """*a 404 on every index document is a dead or misdirected connection, not drift - fail loud, never loop*"""
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    for _ in range(9):
        add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d").get()
    add_area(log=log, dbConn=dbConn, domain="resources", title="Refs", description="d1").get()
    for _ in range(4):
        add_category(log=log, dbConn=dbConn, domain="resources", areaRef="R10", title="Books", description="d").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    def get_block_always_404(blockId):
        raise CraftApiError(
            "craft API GET /blocks failed (404): Block not found",
            method="GET", path="/blocks", statusCode=404,
        )

    fakeClient.get_block = get_block_always_404
    documentsBefore = len(fakeClient.documents)

    with pytest.raises(CraftApiError, match="repair aborted") as raised:
        craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    created = len(fakeClient.documents) - documentsBefore
    assert created == craft_sync_module._MAX_DOCUMENT_REPAIRS_PER_RUN
    # THE ABORT IS A SYSTEMIC FAULT NEEDING ATTENTION, NEVER A TRANSIENT ONE:
    # ITS WORDING MUST NOT MAKE `classify_failure` CALL IT `network` OR `not-found`.
    assert background_sync.classify_failure(raised.value) == "unknown"


def test_a_second_failure_during_link_row_recovery_leaves_a_tracked_replacement(
    dbConn, craftSettings, fakeClient, monkeypatch,
):
    """*if the retry `add_block` also fails, `craft_links` already points at the fresh tracked document*

    The core promise: a replacement is created and recorded before the
    retry, so a later API failure never leaves the row pointing at the
    dead document - the next run resumes from the recorded replacement.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    monkeypatch.setattr(craft_sync_module.doc_links, "hookmark_url", lambda folderPath: "hook://changed")

    dbConn.execute(
        "UPDATE craft_links SET craft_document_id = ? WHERE entity_type = ? AND entity_key = ?",
        ("stale-document", "id:index", "1"),
    )
    dbConn.commit()
    knownDocuments = {document[0] for document in fakeClient.documents}
    realAdd = fakeClient.add_block

    def add_block_that_keeps_failing(documentId, markdown, position="end"):
        if documentId == "stale-document":
            raise CraftApiError(
                "craft API POST /blocks failed (404): Block not found",
                method="POST", path="/blocks", statusCode=404,
            )
        if documentId not in knownDocuments:
            # THE FRESHLY CREATED REPLACEMENT: THE RETRY FAILS TOO.
            raise CraftApiError("craft API POST /blocks failed (429): rate limited on the retry")
        return realAdd(documentId, markdown, position=position)

    fakeClient.add_block = add_block_that_keeps_failing

    with pytest.raises(CraftApiError):
        craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    link = db.get_craft_link(dbConn, "id:index", "1")
    assert link["craft_document_id"] != "stale-document"
    assert any(document[0] == link["craft_document_id"] for document in fakeClient.documents)


def test_an_index_content_delete_404_still_surfaces(dbConn, craftSettings, fakeClient):
    """*`_write_index_content`'s own bulk delete is deliberately not routed through the 404-swallowing wrapper*"""
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="d3").get()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Dermatologist", description="d4").get()

    def delete_404(blockIds):
        raise CraftApiError(
            "craft API DELETE /blocks failed (404): Block not found",
            method="DELETE", path="/blocks", statusCode=404,
        )

    fakeClient.delete_blocks = delete_404

    with pytest.raises(CraftApiError):
        craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()


def test_craft_sync_preserves_a_document_link_after_a_non_not_found_read_failure(
    dbConn, craftSettings, fakeClient,
):
    """*only a structured GET /blocks 404 can replace a persisted document link*"""
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    link = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")
    before = tuple(link[column] for column in ("craft_document_id", "craft_block_id", "craft_url", "links_markdown"))

    def get_block_that_fails(blockId):
        raise CraftApiError(
            "craft API GET /blocks failed (500): response text includes (404)",
            method="GET", path="/blocks", statusCode=500,
        )

    fakeClient.get_block = get_block_that_fails

    with pytest.raises(CraftApiError):
        craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    after = db.get_craft_link(dbConn, "system_folder", "areas.system.00_index")
    assert tuple(after[column] for column in ("craft_document_id", "craft_block_id", "craft_url", "links_markdown")) == before


def test_a_craft_api_without_document_listing_still_creates(dbConn, craftSettings, fakeClient, monkeypatch):
    """list_documents returning [] must degrade to the old create-anyway behaviour"""
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()
    documentsAfterFirstSync = len(fakeClient.documents)

    monkeypatch.setattr(fakeClient, "list_documents", lambda folderId: [])
    dbConn.execute("UPDATE craft_links SET craft_document_id = NULL, craft_url = NULL")
    dbConn.commit()
    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    assert len(fakeClient.documents) > documentsAfterFirstSync


def test_an_entry_with_no_description_has_no_dangling_em_dash(dbConn, craftSettings, fakeClient):
    """*`add_project` always stores an empty description, so every project rendered as `... —`*

    Surfaced while diagnosing the trailing-whitespace comparison failure:
    the listing format put the description after an em-dash unconditionally.
    """
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    entry = next(item["markdown"] for item in content if "cardiologist" in item["markdown"])
    assert not entry.rstrip().endswith("—")
    assert "cardiologist" in entry


def test_an_entry_with_a_description_still_shows_it_after_an_em_dash(dbConn, craftSettings, fakeClient):
    add_area(log=log, dbConn=dbConn, domain="areas", title="Health", description="d1").get()
    add_category(log=log, dbConn=dbConn, domain="areas", areaRef="A10", title="Doctors", description="d2").get()
    add_id(log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="heart stuff").get()

    craft_sync(log=log, dbConn=dbConn, settings=craftSettings).get()

    content = _index_document_content(fakeClient, dbConn, "areas.11.00_index")
    entry = next(item["markdown"] for item in content if "cardiologist" in item["markdown"])
    assert "— heart stuff" in entry
