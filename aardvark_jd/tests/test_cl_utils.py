import logging
import os

import pytest
import yaml
from docopt import docopt

from aardvark_jd import cl_utils

doc = cl_utils.__doc__

log = logging.getLogger("test_cl_utils")
log.addHandler(logging.NullHandler())


@pytest.mark.parametrize("command,expectedKey", [
    ("init TestSystem /tmp/somewhere", "init"),
    ("add_project P11 Title", "add_project"),
    ("add_project P11 Title -t website", "add_project"),
    ("add_area A Health desc", "add_area"),
    ("add_category A10-19 Doctors desc", "add_category"),
    ("add_id A11 Cardiologist desc", "add_id"),
    ("set_emoji A10-19 X", "set_emoji"),
    ("repair_emoji", "repair_emoji"),
    ("fd cardio", "fd"),
    ("connect_craft https://connect.craft.do/links/abc/api/v1 my-token", "connect_craft"),
    ("craft_sync", "craft_sync"),
    ("connect_todoist my-token", "connect_todoist"),
    ("todoist_sync", "todoist_sync"),
    ("connect_gdrive my-client-id my-client-secret", "connect_gdrive"),
    ("gdrive_sync", "gdrive_sync"),
    ("archive A11.10", "archive"),
    ("archive A11.10 -y", "archive"),
    ("fd", "fd"),
    ("cd A11.10", "cd"),
    ("open", "open"),
    ("completion zsh", "completion"),
    ("shell_init zsh", "shell_init"),
])
def test_docopt_parses_each_subcommand(command, expectedKey):
    args = docopt(doc, command.split(" "))
    assert args[expectedKey] is True


@pytest.mark.parametrize("command", [
    "add_area A Health desc",
    "add_category A10-19 Doctors desc",
])
def test_docopt_accepts_the_emoji_flag(command):
    assert docopt(doc, command.split(" ") + ["-e", "X"])["--emoji"] == "X"
    assert docopt(doc, command.split(" ") + ["--emoji", "X"])["--emoji"] == "X"


def test_emoji_flag_and_set_emoji_positional_do_not_collide():
    # `--emoji` is an option on the add_* commands while `<emoji>` is a
    # positional on set_emoji, so check docopt keeps the two apart
    args = docopt(doc, ["set_emoji", "A10-19", "X"])
    assert args["<emoji>"] == "X"
    assert args["--emoji"] is None


@pytest.fixture
def isolatedHome(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_main_end_to_end(isolatedHome, monkeypatch, capsys):
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)

    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    assert "initialised" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc"]))
    assert "A10-19" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["add_category", "A10-19", "Doctors", "desc"]))
    assert "A11" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["add_id", "A11", "Cardiologist", "desc"]))
    assert "A11.10" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["add_area", "P", "Launches", "desc"]))
    assert "P10-19" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["add_category", "P10-19", "Website", "desc"]))
    assert "P11" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["add_project", "P11", "Relaunch"]))
    assert "P11.10" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["fd", "cardiologist"]))
    assert "A11.10" in capsys.readouterr().out


def test_main_reports_missing_system(isolatedHome, capsys):
    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["fd", "anything"]))
    assert excInfo.value.code == 1
    assert "run `aardvark init" in capsys.readouterr().err


def test_a_normal_command_reasserts_the_dropbox_index_ignore(isolatedHome, monkeypatch):
    """*every non-init command re-asserts the ignore, so a cloned tree self-heals on first use*"""
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)

    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))

    calls = []
    monkeypatch.setattr(
        "aardvark_jd.dropbox_ignore.assert_index_ignored",
        lambda rootPath, log: calls.append(rootPath),
    )
    cl_utils.main(docopt(doc, ["fd", "anything"]))

    assert calls == [f"{rootParent}/TestSystem"]


def test_main_reports_clear_error_for_an_invalid_domain_letter(isolatedHome, capsys):
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["add_area", "Q", "X", "desc"]))
    assert excInfo.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_main_set_emoji_and_repair_emoji_end_to_end(isolatedHome, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)

    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "-e", "X"]))
    capsys.readouterr()

    cl_utils.main(docopt(doc, ["set_emoji", "A10-19", "Y"]))
    out = capsys.readouterr().out
    assert "A10-19" in out
    assert "A10_19_healthY" in out

    # a freshly initialised system needs no repair
    cl_utils.main(docopt(doc, ["repair_emoji"]))
    assert "already matches the current naming convention" in capsys.readouterr().out

    cl_utils.main(docopt(doc, ["set_emoji", "root.areas", "Z"]))
    capsys.readouterr()
    cl_utils.main(docopt(doc, ["repair_emoji"]))
    assert "root.areas" in capsys.readouterr().out


def test_main_emoji_flag_skips_the_picker(isolatedHome, monkeypatch, capsys):
    from aardvark_jd import emoji_picker

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    def boom(*args, **kwargs):
        raise AssertionError("--emoji must bypass the emoji picker entirely")

    monkeypatch.setattr(emoji_picker, "pick_emoji", boom)

    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    cl_utils.main(docopt(doc, ["add_area", "A", "Taxes", "desc", "-e", "T"]))
    assert "A10_19_taxesT" in capsys.readouterr().out


_CRAFT_API_URL = "https://connect.craft.do/links/abc123/api/v1"


class FakeCraftClient(object):
    """*records every folder/document/block created or deleted, without any HTTP calls*

    Models the real API's read-delete-insert index refresh - see the
    identical fake in `test_craft_sync.py` for the full rationale.
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

    def _next_id(self, prefix):
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def list_folders(self):
        """*rebuild the nested tree the real `GET /folders` returns, from what's been created*"""

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
        return [
            {"id": documentId, "title": title}
            for documentId, title, parent in self.documents
            if parent == folderId
        ]

    def _deep_link(self, itemId):
        return f"https://craft.example/doc/{itemId}"

    def add_block(self, documentId, markdown, position="end"):
        blockId = self._next_id("block")
        self.blocksAdded.append((documentId, markdown, blockId))
        self._documentContent.setdefault(documentId, []).append((blockId, markdown))
        return blockId

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
def fakeCraftClient(monkeypatch):
    client = FakeCraftClient(apiUrl=_CRAFT_API_URL, apiToken="fake-token")
    monkeypatch.setattr("aardvark_jd.craft_sync.CraftClient", lambda apiUrl, apiToken, budget=None, announce=None: client)
    return client


def test_connect_craft_persists_settings_and_runs_initial_sync(isolatedHome, fakeCraftClient, capsys):
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    settingsPath = str(isolatedHome / ".config" / "aardvark" / "aardvark.yaml")
    cl_utils.main(docopt(doc, ["connect_craft", _CRAFT_API_URL, "my-token", "-s", settingsPath]))
    out = capsys.readouterr().out
    assert "craft connected" in out
    assert len(fakeCraftClient.folders) >= 5

    with open(settingsPath) as stream:
        savedSettings = yaml.safe_load(stream)
    assert savedSettings["craft"]["enabled"] is True
    assert savedSettings["craft"]["api_url"] == _CRAFT_API_URL
    assert savedSettings["craft"]["api_token"] == "my-token"


def test_connect_craft_without_s_flag_still_persists_to_the_default_settings_file(
    isolatedHome, fakeCraftClient, capsys,
):
    """*regression test for the bug where craft.enabled never survived past the connecting process*

    `connect_craft` used to only write settings back out when `-s` was
    passed explicitly, unlike `init` which already falls back to the
    default `~/.config/aardvark/aardvark.yaml`. That meant a bare
    `connect_craft <url> <token>` (no `-s`) looked like it worked - the
    initial sync ran - but `craft.enabled` was never saved, so every
    later command silently skipped its auto-push.
    """
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    cl_utils.main(docopt(doc, ["connect_craft", _CRAFT_API_URL, "my-token"]))
    assert "craft connected" in capsys.readouterr().out

    defaultSettingsPath = str(isolatedHome / ".config" / "aardvark" / "aardvark.yaml")
    with open(defaultSettingsPath) as stream:
        savedSettings = yaml.safe_load(stream)
    assert savedSettings["craft"]["enabled"] is True

    # THE REAL REGRESSION TEST: A LATER COMMAND, ALSO RUN WITHOUT `-s`, MUST
    # PICK UP `craft.enabled` FROM THAT SAME DEFAULT FILE AND AUTO-PUSH.
    fakeCraftClient.folders.clear()
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "--wait"]))
    capsys.readouterr()
    assert any(name.startswith("A10-19 health") for _id, name, _parent in fakeCraftClient.folders)


def test_craft_sync_command_requires_connect_first(isolatedHome, capsys):
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["craft_sync"]))
    assert excInfo.value.code == 1
    assert "craft is not connected" in capsys.readouterr().err


def test_add_area_auto_pushes_to_craft_once_connected(isolatedHome, fakeCraftClient, capsys):
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    settingsPath = str(isolatedHome / ".config" / "aardvark" / "aardvark.yaml")
    cl_utils.main(docopt(doc, ["connect_craft", _CRAFT_API_URL, "my-token", "-s", settingsPath]))
    capsys.readouterr()

    # `--wait` FORCES THE FOREGROUND PATH; WITHOUT IT THE SYNC IS HANDED TO A
    # DETACHED PROCESS AND THIS TEST'S FAKE CLIENT WOULD NEVER SEE IT.
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "--wait"]))
    assert "A10-19" in capsys.readouterr().out

    # the craft folder mirrors the on-disk name (lowercased, emoji suffixed)
    folderTitles = {name for _id, name, _parent in fakeCraftClient.folders}
    assert any(name.startswith("A10-19 health") for name in folderTitles)

    # THE DOMAIN-ROOT INDEX MUST ACTUALLY LIST THE NEW AREA, NOT JUST HAVE ITS
    # FOLDER CREATED - THE PRIOR VERSION OF THIS TEST ONLY CHECKED THE LATTER,
    # WHICH IS HOW A BLANK INDEX DOCUMENT SHIPPED UNDETECTED.
    assert any("A10-19 health" in body for body in fakeCraftClient.index_bodies())


def test_repair_emoji_auto_pushes_to_craft_once_connected(isolatedHome, monkeypatch, fakeCraftClient, capsys):
    """*regression test: `repair_emoji` used to never sync to craft at all, even when connected*"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "-e", "X"]))
    capsys.readouterr()

    settingsPath = str(isolatedHome / ".config" / "aardvark" / "aardvark.yaml")
    cl_utils.main(docopt(doc, ["connect_craft", _CRAFT_API_URL, "my-token", "-s", settingsPath]))
    capsys.readouterr()

    cl_utils.main(docopt(doc, ["set_emoji", "A10-19", "Y", "--wait"]))
    capsys.readouterr()

    blocksDeletedBefore = len(fakeCraftClient.blocksDeleted)
    cl_utils.main(docopt(doc, ["repair_emoji", "--wait"]))
    capsys.readouterr()
    assert len(fakeCraftClient.blocksDeleted) > blocksDeletedBefore
    assert any("A10-19 healthY" in body for body in fakeCraftClient.index_bodies())


def test_the_usage_docs_match_the_live_docopt_string():
    """docs/source/usage.md embeds __doc__ by hand, and had already drifted once"""
    import os

    usagePath = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs", "source", "usage.md",
    )
    if not os.path.exists(usagePath):
        pytest.skip("docs are not shipped in the installed package")

    with open(usagePath, encoding="utf-8") as usageFile:
        rendered = usageFile.read()

    # COMPARE LINE BY LINE, IGNORING THE FENCE AND THE UNIFORM INDENT
    for line in doc.strip("\n").split("\n"):
        if line.strip():
            assert line.strip() in rendered, line.strip()


# ---------------------------------------------------------------------- #
# backgrounded sync - see `background_sync` and `docs/adr/0001-...`
# ---------------------------------------------------------------------- #

@pytest.fixture
def connectedSystem(isolatedHome, fakeCraftClient, capsys):
    """*an initialised system with craft connected, ready for a mutating command*"""
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    settingsPath = str(isolatedHome / ".config" / "aardvark" / "aardvark.yaml")
    cl_utils.main(docopt(doc, ["connect_craft", _CRAFT_API_URL, "my-token", "-s", settingsPath]))
    capsys.readouterr()
    return f"{rootParent}/TestSystem"


def test_a_mutating_command_hands_sync_to_a_detached_process_and_returns(
    connectedSystem, monkeypatch, fakeCraftClient, capsys,
):
    """*the whole point: `add_area` must not wait for four services' round trips*"""
    from aardvark_jd import background_sync

    spawns = []
    monkeypatch.setattr(
        background_sync, "spawn_detached",
        lambda pathToSettingsFile=None, log=None: spawns.append(pathToSettingsFile) or 4321,
    )
    foldersBefore = len(fakeCraftClient.folders)

    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc"]))

    assert "A10-19" in capsys.readouterr().out
    assert len(spawns) == 1
    # AND IT DID NOT SYNC IN THE FOREGROUND.
    assert len(fakeCraftClient.folders) == foldersBefore


def test_the_wait_flag_syncs_in_the_foreground_instead_of_spawning(
    connectedSystem, monkeypatch, fakeCraftClient, capsys,
):
    from aardvark_jd import background_sync

    spawns = []
    monkeypatch.setattr(
        background_sync, "spawn_detached",
        lambda pathToSettingsFile=None, log=None: spawns.append(pathToSettingsFile) or 4321,
    )

    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "--wait"]))

    capsys.readouterr()
    assert spawns == []
    assert any(name.startswith("A10-19 health") for _id, name, _parent in fakeCraftClient.folders)


def test_the_wait_flag_exits_non_zero_when_a_mirror_fails(connectedSystem, monkeypatch, capsys):
    """*not "the command failed" - the entity exists and a mirror did not sync*"""
    from aardvark_jd import background_sync

    monkeypatch.setattr(
        background_sync, "run_mirrors",
        lambda log, dbConn, settings, announce=None: ([("craft", "429 rate limited", "rate-limited")], False),
    )

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "--wait"]))

    assert excInfo.value.code == 1
    assert "craft sync failed (rate-limited)" in capsys.readouterr().err


def test_a_later_command_warns_that_the_last_sync_failed(connectedSystem, monkeypatch, capsys):
    """*the drift marker is what makes a failure in a detached process visible at all*"""
    from aardvark_jd import background_sync

    monkeypatch.setattr(
        background_sync, "spawn_detached", lambda pathToSettingsFile=None, log=None: 4321,
    )
    from aardvark_jd import db, paths

    indexDbConn = db.get_connection(paths.find_db_path(connectedSystem))
    db.record_sync_failure(indexDbConn, "craft", "429 rate limited", "rate-limited")
    indexDbConn.close()

    cl_utils.main(docopt(doc, ["fd", "anything"]))

    assert "last sync failed for craft" in capsys.readouterr().err


def test_no_drift_warning_when_every_mirror_is_healthy(connectedSystem, monkeypatch, capsys):
    from aardvark_jd import background_sync

    monkeypatch.setattr(
        background_sync, "spawn_detached", lambda pathToSettingsFile=None, log=None: 4321,
    )
    cl_utils.main(docopt(doc, ["fd", "anything"]))

    assert "last sync failed" not in capsys.readouterr().err


def test_a_mutating_command_does_not_spawn_when_no_mirror_is_connected(isolatedHome, monkeypatch, capsys):
    """*nothing to sync, so nothing to spawn - an unconnected system pays no subprocess cost*"""
    from aardvark_jd import background_sync

    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    spawns = []
    monkeypatch.setattr(
        background_sync, "spawn_detached",
        lambda pathToSettingsFile=None, log=None: spawns.append(1) or 4321,
    )
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc"]))

    assert spawns == []


def test_archive_also_hands_off_a_whole_tree_repair(connectedSystem, monkeypatch, capsys):
    """*archive moves folders the mirrors adopt by name, so the index documents need reconciling*"""
    from aardvark_jd import background_sync

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr(
        background_sync, "spawn_detached", lambda pathToSettingsFile=None, log=None: 4321,
    )
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc"]))
    cl_utils.main(docopt(doc, ["add_category", "A10-19", "Doctors", "desc"]))
    capsys.readouterr()

    spawns = []
    monkeypatch.setattr(
        background_sync, "spawn_detached",
        lambda pathToSettingsFile=None, log=None: spawns.append(1) or 4321,
    )
    cl_utils.main(docopt(doc, ["archive", "A11", "-y"]))

    assert "archived A11" in capsys.readouterr().out
    assert len(spawns) == 1


def test_the_background_carrier_syncs_a_gdrive_only_system(isolatedHome, monkeypatch, capsys):
    """*regression: the carrier must not self-gate on craft*

    `spawn_detached` runs `aardvark craft_sync`. Gating that command on
    `craft.enabled` made every background sync a silent no-op for anyone
    who had connected only Google Drive - it exited 1 into `/dev/null`
    before any mirror ran, so nothing synced and no drift marker was even
    written.
    """
    import yaml
    from aardvark_jd import background_sync

    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()
    settingsPath = str(isolatedHome / ".config" / "aardvark" / "aardvark.yaml")

    savedSettings = yaml.safe_load(open(settingsPath))
    savedSettings["gdrive"] = {
        "enabled": True, "client_id": "x", "client_secret": "y", "refresh_token": "z",
    }
    with open(settingsPath, "w") as stream:
        yaml.safe_dump(savedSettings, stream)

    ran = []
    monkeypatch.setattr(
        background_sync, "run_mirrors",
        lambda log, dbConn, settings, announce=None: ran.append(settings) or ([], False),
    )

    cl_utils.main(docopt(doc, ["craft_sync", "-s", settingsPath]))

    # THE CARRIER RAN THE MIRRORS INSTEAD OF DYING ON THE MISSING CRAFT.
    assert len(ran) == 1
    assert ran[0]["gdrive"]["enabled"] is True
    assert "craft is not connected - syncing the other mirrors only" in capsys.readouterr().err


def test_the_carrier_still_errors_when_nothing_at_all_is_connected(isolatedHome, capsys):
    """*the original contract: `craft_sync` on an unconnected system is an error*"""
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    capsys.readouterr()

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["craft_sync"]))
    assert excInfo.value.code == 1
    assert "craft is not connected" in capsys.readouterr().err


def test_a_mirror_failure_reason_cannot_smuggle_terminal_escapes(connectedSystem, monkeypatch, capsys):
    """*the reason carries a remote API response body, and `--wait` prints it to a real terminal*"""
    from aardvark_jd import background_sync

    nasty = "rate limited \x1b[2J\x07 and cleared your screen"
    monkeypatch.setattr(
        background_sync, "run_mirrors",
        lambda log, dbConn, settings, announce=None: ([("craft", nasty, "rate-limited")], False),
    )

    with pytest.raises(SystemExit):
        cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "--wait"]))

    err = capsys.readouterr().err
    assert "\x1b" not in err and "\x07" not in err
    assert "rate limited" in err and "cleared your screen" in err


def test_fd_on_an_id_ref_prints_a_bare_label_and_a_wide_path_gutter(isolatedHome, capsys):
    """*an ID owns no emoji, so its one-line output stays `code title  path`*"""
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)

    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "-e", "\N{HOSPITAL}"]))
    cl_utils.main(docopt(doc, ["add_category", "A10-19", "Doctors", "desc", "-e", "\N{STETHOSCOPE}"]))
    cl_utils.main(docopt(doc, ["add_id", "A11", "Cardiologist", "desc"]))
    capsys.readouterr()

    cl_utils.main(docopt(doc, ["fd", "A11.10"]))
    line = capsys.readouterr().out.strip()

    assert line.startswith("A11.10 Cardiologist  /")
    assert "\N{FILE FOLDER}" not in line


def test_fd_on_a_category_ref_prints_the_emoji_in_the_tree(isolatedHome, capsys):
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)

    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "desc", "-e", "\N{HOSPITAL}"]))
    cl_utils.main(docopt(doc, ["add_category", "A10-19", "Doctors", "desc", "-e", "\N{STETHOSCOPE}"]))
    capsys.readouterr()

    cl_utils.main(docopt(doc, ["fd", "A11"]))

    assert "A11 \N{STETHOSCOPE} Doctors" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# THE `--json` CONTRACT. INTERNAL AND UNSTABLE - SEE `json_output.py` AND
# `docs/alfred-workflow-spec.md`. THE ALFRED WORKFLOW IS ITS ONLY CONSUMER.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", [
    "fd --json",
    "fd --json --archived",
    "fd cardio --json",
    "open --json",
    "open /some/path --json",
    "add_id A11 Cardiologist heart --json",
])
def test_docopt_accepts_the_json_flag_where_the_contract_defines_it(command):
    args = docopt(doc, command.split(" "))
    assert args["--json"] is True


@pytest.mark.parametrize("command", ["cd A11.10 --json", "repair_emoji --json"])
def test_docopt_rejects_the_json_flag_where_the_contract_does_not_define_it(command):
    with pytest.raises(SystemExit):
        docopt(doc, command.split(" "))


def _seededSystem(isolatedHome, capsys):
    """*a two-domain system with an area, a category and two IDs, ready to dump*"""
    rootParent = str(isolatedHome / "root_parent")
    os.makedirs(rootParent)
    cl_utils.main(docopt(doc, ["init", "TestSystem", rootParent]))
    cl_utils.main(docopt(doc, ["add_area", "A", "Health", "the body"]))
    cl_utils.main(docopt(doc, ["add_category", "A10-19", "Doctors", "clinicians"]))
    cl_utils.main(docopt(doc, ["add_id", "A11", "Cardiologist", "heart"]))
    cl_utils.main(docopt(doc, ["add_id", "A11", "Dentist", "teeth"]))
    cl_utils.main(docopt(doc, ["add_area", "R", "Reading", "books"]))
    capsys.readouterr()
    return rootParent


def test_fd_json_emits_a_versioned_envelope_with_a_system_block(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)

    assert payload["aardvark_json"] == 1
    assert payload["system"]["name"] == "TestSystem"
    assert payload["system"]["root_path"].endswith("TestSystem")
    assert payload["system"]["generated_at"].endswith("Z")
    assert payload["system"]["version"]


def test_fd_json_is_flat_and_in_index_order(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)

    assert [entity["code"] for entity in payload["entities"]] == [
        "A10-19", "A11", "A11.10", "A11.11", "R10-19",
    ]
    assert all("children" not in entity for entity in payload["entities"])
    assert all(entity["archived"] is False for entity in payload["entities"])
    assert "archived" not in payload


def test_fd_json_carries_every_mirror_url_slot_even_when_unsynced(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)

    urls = payload["entities"][0]["urls"]
    assert set(urls) == {"finder", "craft", "todoist", "drive", "dropbox"}
    assert urls["craft"] is None


def test_fd_json_on_a_ref_returns_that_subtree_flat(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd", "A11", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)

    assert [entity["code"] for entity in payload["entities"]] == ["A11", "A11.10", "A11.11"]


def test_fd_json_on_a_keyword_returns_the_search_matches(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd", "cardiologist", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)

    assert [entity["code"] for entity in payload["entities"]] == ["A11.10"]


def test_fd_json_archived_adds_a_sibling_array_and_leaves_entities_live(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)
    cl_utils.main(docopt(doc, ["archive", "A11.11", "-y"]))
    capsys.readouterr()

    cl_utils.main(docopt(doc, ["fd", "--json", "--archived"]))
    payload = jsonModule.loads(capsys.readouterr().out)

    assert [entity["code"] for entity in payload["entities"]] == ["A10-19", "A11", "A11.10", "R10-19"]
    assert [entity["code"] for entity in payload["archived"]] == ["A11.11"]
    assert payload["archived"][0]["archived"] is True
    assert payload["archived"][0]["urls"]["finder"] is None


def test_archived_without_json_fails_loudly_rather_than_silently(isolatedHome, capsys):
    """*`--archived` only shapes the contract, so on its own it is a mistake worth naming*"""
    _seededSystem(isolatedHome, capsys)

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["fd", "--archived"]))

    assert excInfo.value.code == 1
    assert "--archived" in capsys.readouterr().err


def test_fd_without_json_still_prints_the_human_tree(isolatedHome, capsys):
    """*regression guard: the contract must not disturb what `fd` has always printed*"""
    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd"]))
    out = capsys.readouterr().out

    assert "A11.10 Cardiologist" in out
    assert "aardvark_json" not in out


def test_open_json_returns_the_record_without_opening_anything(isolatedHome, monkeypatch, capsys):
    import json as jsonModule

    from aardvark_jd import open_craft as openCraftModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)
    idPath = [entity for entity in payload["entities"] if entity["code"] == "A11.10"][0]["folder_path"]

    def boom(*args, **kwargs):
        raise AssertionError("`open --json` must not open anything")

    monkeypatch.setattr(openCraftModule, "open_craft", boom)

    cl_utils.main(docopt(doc, ["open", idPath, "--json"]))
    result = jsonModule.loads(capsys.readouterr().out)["result"]

    assert result["action"] == "open"
    assert result["label"] == "Cardiologist"
    assert result["entity"]["code"] == "A11.10"


def test_open_json_on_an_entity_synced_to_nothing_is_not_an_error(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["fd", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)
    idPath = [entity for entity in payload["entities"] if entity["code"] == "A11.10"][0]["folder_path"]

    cl_utils.main(docopt(doc, ["open", idPath, "--json"]))
    result = jsonModule.loads(capsys.readouterr().out)["result"]

    assert all(result["entity"]["urls"][mirror] is None for mirror in ("craft", "todoist", "drive"))


def test_a_clear_error_under_json_lands_on_stdout_with_a_stable_kind(isolatedHome, capsys):
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["open", "/nowhere/at/all", "--json"]))

    captured = capsys.readouterr()
    assert excInfo.value.code != 0
    # ALFRED READS STDOUT REGARDLESS OF EXIT CODE, SO THE OBJECT ALWAYS ARRIVES.
    payload = jsonModule.loads(captured.out)
    assert payload["aardvark_json"] == 1
    assert payload["error"]["kind"]
    assert payload["error"]["message"]


def test_a_missing_system_under_json_is_an_error_envelope_not_prose(isolatedHome, capsys):
    import json as jsonModule

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["fd", "--json"]))

    captured = capsys.readouterr()
    assert excInfo.value.code == 1
    assert jsonModule.loads(captured.out)["error"]["kind"] == "no_system"
    # STDOUT CARRIES THE OBJECT AND NOTHING ELSE. THE PROSE IS NOT REPEATED
    # ON STDERR EITHER - IT IS THE OBJECT'S OWN `message` NOW.
    assert "no aardvark system found" not in captured.err


def test_the_very_first_json_invocation_on_a_machine_prints_only_the_object(isolatedHome, capsys):
    """*set-up announces the settings file it writes on its first run, and prose in front of the object would make the whole stream unparseable*"""
    import json as jsonModule

    # NO PRIOR `aardvark` CALL: THIS IS THE RUN THAT CREATES
    # `~/.config/aardvark/aardvark.yaml`.
    with pytest.raises(SystemExit):
        cl_utils.main(docopt(doc, ["fd", "--json"]))

    captured = capsys.readouterr()
    assert jsonModule.loads(captured.out)["error"]["kind"] == "no_system"
    assert "Default settings have been added" in captured.err


# --------------------------------------------------- the mutating result shape


def test_add_id_json_returns_the_uniform_mutating_result(isolatedHome, capsys):
    """*one shape across every mutating command, so Alfred renders them all the same way*"""
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["add_id", "A11", "Podiatrist", "feet", "--json"]))
    payload = jsonModule.loads(capsys.readouterr().out)

    assert payload["aardvark_json"] == 1
    result = payload["result"]
    assert result["action"] == "add_id"
    assert result["sync"] == "none"
    assert result["corrections"] == []
    assert result["suggestions"] == []
    assert result["warnings"] == []
    assert "emoji_source" not in result
    assert "template_used" not in result


def test_the_sync_label_says_what_became_of_the_mirroring(isolatedHome, monkeypatch, capsys):
    """*`sync` reports the disposition, not what was asked for*"""
    spawned = []
    monkeypatch.setattr(
        cl_utils.background_sync, "spawn_detached",
        lambda **kwargs: spawned.append(kwargs),
    )
    settings = {"system": {"root_path": str(isolatedHome)}, "craft": {"enabled": True}}

    label = cl_utils._hand_off_sync({}, log, None, settings)

    assert label == "backgrounded"
    assert spawned


def test_the_sync_label_is_none_when_no_mirror_is_connected(isolatedHome):
    settings = {"system": {"root_path": str(isolatedHome)}}

    assert cl_utils._hand_off_sync({}, log, None, settings) == "none"


def test_add_id_json_carries_the_new_entity_record(isolatedHome, capsys):
    """*the success surface is built from this record, which is the whole recall story*"""
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["add_id", "A11", "Podiatrist", "feet", "--json"]))
    entity = jsonModule.loads(capsys.readouterr().out)["result"]["entity"]

    assert entity["code"] == "A11.12"
    assert entity["id"] == "areas:A11.12"
    assert entity["type"] == "id"
    assert entity["title"] == "Podiatrist"
    assert entity["description"] == "feet"
    assert entity["folder_path"].endswith("A11.12_podiatrist")
    assert entity["urls"]["finder"]
    assert entity["urls"]["craft"] is None


def test_add_id_json_prints_the_object_and_no_prose(isolatedHome, capsys):
    """*prose in front of the object would make the whole stream unparseable*"""
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["add_id", "A11", "Podiatrist", "feet", "--json"]))
    captured = capsys.readouterr()

    jsonModule.loads(captured.out)
    assert "A11.12  " not in captured.out


def test_add_id_json_reports_the_suspect_tokens_it_never_prompted_about(
    isolatedHome, capsys,
):
    """
    *`--json` runs detection despite never prompting*

    Otherwise `suggestions` would be empty in exactly the run the
    confirmation screen needs it filled for.
    """
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    cl_utils.main(docopt(doc, ["add_id", "A11", "Aadvark", "notes", "--json"]))
    result = jsonModule.loads(capsys.readouterr().out)["result"]

    assert result["corrections"] == []
    assert result["suggestions"] == [
        {"token": "Aadvark", "index": 0, "suggested": "aardvark"},
    ]
    assert result["entity"]["title"] == "Aadvark"


def test_add_id_json_forks_its_failures_into_the_error_envelope(isolatedHome, capsys):
    """*a script filter cannot raise, so a bad category has to arrive as an object*"""
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)

    with pytest.raises(SystemExit) as excInfo:
        cl_utils.main(docopt(doc, ["add_id", "A99", "Podiatrist", "feet", "--json"]))

    captured = capsys.readouterr()
    assert excInfo.value.code == 1
    assert jsonModule.loads(captured.out)["error"]["kind"] == "value_error"


def test_add_id_json_never_prompts_even_from_a_real_terminal(
    isolatedHome, monkeypatch, capsys,
):
    """
    *`--json` promises it never prompts, and a tty is not what makes that true*

    Alfred's subprocess has no terminal, so inferring it from `isatty`
    happens to work there and blocks forever for anyone running `--json`
    from a real shell.
    """
    import json as jsonModule

    _seededSystem(isolatedHome, capsys)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def refuse(prompt=""):
        raise AssertionError("`--json` must never prompt")

    monkeypatch.setattr("builtins.input", refuse)

    cl_utils.main(docopt(doc, ["add_id", "A11", "Aadvark", "notes", "--json"]))
    result = jsonModule.loads(capsys.readouterr().out)["result"]

    assert result["entity"]["title"] == "Aadvark"
    assert result["corrections"] == []
    assert result["suggestions"] == [
        {"token": "Aadvark", "index": 0, "suggested": "aardvark"},
    ]
