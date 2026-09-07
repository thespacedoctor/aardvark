"""
*Referential-integrity checks on the shipped Alfred `info.plist`*

The workflow spec deliberately leaves `info.plist` semantically untested -
"it is data, and Alfred is its parser". That covers meaning. It does not
cover integrity: a mistyped `scriptfile`, a dangling `destinationuid` or a
command row wired nowhere is silent at author time, broken at run time,
and reachable by no other test in the suite. Slice 3 more than triples
the hand-authored object count, so these assertions check structure only
and never behaviour.
"""

import functools
import os
import plistlib
from importlib.resources import files
from pathlib import Path

import pytest

from aardvark_jd.alfred import items

ALFRED_ROOT = Path(str(files("aardvark_jd"))) / "resources" / "alfred"
PLIST_PATH = ALFRED_ROOT / "info.plist"

# `_resolve.sh` IS SOURCED BY EVERY OTHER SCRIPT AND NEVER NAMED AS A
# `scriptfile`; IT IS THE ONE LEGITIMATE UNREFERENCED SHELL SCRIPT.
UNREFERENCED_SCRIPTS = {"_resolve.sh"}

# THE SLICE-2 `add_id` COMMAND ENTRY POINT AND ITS ROUTER TARGET. THE
# ROUTER REPLACED `add_id_reference` AS THE COMMAND-ROW DESTINATION OF THE
# `5A08` CONDITIONAL; A REGRESSION THAT DROPPED THE REWIRE WOULD LEAVE
# EVERY NEW FLOW UNREACHABLE.
COMMAND_GATE_UID = "6F1B0A54-1C1E-4C3B-9C0A-2B7F1D0E5A08"
COMMAND_ROUTER_UID = "6F1B0A54-1C1E-4C3B-9C0A-2B7F1D0E5A18"


@functools.lru_cache(maxsize=1)
def _plist():
    if not PLIST_PATH.exists():
        pytest.skip("the workflow is not shipped in this installation")
    # THE CACHED DICT IS ONLY EVER READ BY THE HELPERS BELOW, NEVER MUTATED.
    return plistlib.loads(PLIST_PATH.read_bytes())


def _objects():
    return _plist()["objects"]


def _object_uids():
    return {entry["uid"] for entry in _objects()}


def _scriptfiles():
    return {
        entry["config"]["scriptfile"]
        for entry in _objects()
        if entry.get("config", {}).get("scriptfile")
    }


def _conditionals():
    return [e for e in _objects() if e["type"] == "alfred.workflow.utility.conditional"]


def _edges(sourceUid):
    return _plist()["connections"].get(sourceUid, [])


# --------------------------------------------------------- scripts on disk

def test_every_scriptfile_reference_resolves_to_an_executable_file():
    for scriptfile in _scriptfiles():
        path = ALFRED_ROOT / scriptfile
        assert path.is_file(), f"{scriptfile} is referenced but missing"
        assert os.access(path, os.X_OK), f"{scriptfile} is referenced but not executable"


def test_every_shipped_shell_script_is_wired_into_the_workflow():
    """*catches "wired four of five flows" - 27 orphans before slice 3 landed*"""
    referenced = {Path(scriptfile).name for scriptfile in _scriptfiles()}
    onDisk = {path.name for path in (ALFRED_ROOT / "scripts").glob("*.sh")}
    orphans = onDisk - referenced - UNREFERENCED_SCRIPTS
    assert not orphans, f"shell scripts shipped but wired nowhere: {sorted(orphans)}"


def test_every_shell_wrapper_has_its_python_sibling():
    """
    *the plist names the `.sh`; the `.sh` execs a same-stem `.py` the plist never sees*

    A `<flow>_confirm.sh` runs `"$aardvarkInterpreter" .../<flow>_confirm.py`,
    so a missing or misnamed `.py` is a run-time-only failure the
    scriptfile check above cannot reach.
    """
    scriptsDir = ALFRED_ROOT / "scripts"
    for shellScript in scriptsDir.glob("*.sh"):
        if shellScript.name in UNREFERENCED_SCRIPTS:
            continue
        sibling = shellScript.with_suffix(".py")
        if not sibling.exists():
            # A FEW `*_create.sh` STEPS SHELL OUT DIRECTLY AND HAVE NO
            # PYTHON PARTNER; THAT IS FINE, ONLY A *MISSING NAMED* ONE IS NOT.
            assert f'{sibling.name}"' not in shellScript.read_text(), (
                f"{shellScript.name} names {sibling.name} but it does not exist"
            )
            continue
        assert os.access(sibling, os.X_OK), f"{sibling.name} exists but is not executable"


def test_no_object_inlines_a_script_body():
    """*the spec's External Script rule: a body is a file, never plist text*"""
    for entry in _objects():
        config = entry.get("config", {})
        if config.get("scriptfile"):
            assert config.get("type") == 8
            assert config.get("script") == ""


# --------------------------------------------------------- the connection graph

def test_object_uids_are_unique():
    uids = [entry["uid"] for entry in _objects()]
    assert len(uids) == len(set(uids))


def test_every_connection_endpoint_is_a_known_object():
    known = _object_uids()
    connections = _plist()["connections"]
    for source, edges in connections.items():
        assert source in known, f"connection from unknown object {source}"
        for edge in edges:
            assert edge["destinationuid"] in known, (
                f"{source} points at unknown object {edge['destinationuid']}"
            )


def test_every_object_has_a_uidata_entry():
    """*an object with no canvas entry vanishes from Alfred's editor*"""
    assert set(_plist()["uidata"]) == _object_uids()


def test_every_conditional_output_is_matched_by_exactly_one_edge():
    for conditional in _conditionals():
        conditionUids = {c["uid"] for c in conditional["config"]["conditions"]}
        edges = _edges(conditional["uid"])
        wired = {e["sourceoutputuid"] for e in edges if "sourceoutputuid" in e}
        assert wired == conditionUids, (
            f"{conditional['uid']}: conditions {conditionUids} vs wired outputs {wired}"
        )
        elseEdges = [e for e in edges if "sourceoutputuid" not in e]
        assert len(elseEdges) == 1, f"{conditional['uid']} needs exactly one else edge"
        # ALFRED ROUTES A CONDITIONAL'S `else` BRANCH THROUGH THE ONE EDGE
        # WITH NO `sourceoutputuid`, AND IT MUST BE LAST. A REORDER (E.G.
        # AFTER AN ALFRED SAVE) WOULD PASS THE COUNT CHECK BUT MISROUTE.
        assert "sourceoutputuid" not in edges[-1], (
            f"{conditional['uid']}'s else edge is not last"
        )


def test_the_command_gate_routes_command_rows_to_the_router():
    """*the one rewired edge: `5A08` command output must reach `5A18`, not `add_id_reference`*"""
    router = _command_router()
    assert router["uid"] == COMMAND_ROUTER_UID
    destinations = {edge["destinationuid"] for edge in _edges(COMMAND_GATE_UID)}
    assert COMMAND_ROUTER_UID in destinations


# --------------------------------------------------------- plist <-> command list

def _command_router():
    for conditional in _conditionals():
        strings = {c["matchstring"] for c in conditional["config"]["conditions"]}
        if {"add_area", "add_id", "archive"} <= strings:
            return conditional
    raise AssertionError("no command router conditional found")


def test_every_mutating_command_row_is_routed_to_a_first_step():
    """*adding a command row in `items` without wiring it here fails, and the reverse*"""
    router = _command_router()
    routed = {c["matchstring"] for c in router["config"]["conditions"]}
    commands = {command for command, _, _ in items._COMMANDS}
    assert routed == commands


def test_every_flow_reaches_its_create_and_success_scripts():
    router = _command_router()
    connections = _plist()["connections"]
    byUid = {entry["uid"]: entry for entry in _objects()}
    outputs = {c["uid"]: c["matchstring"] for c in router["config"]["conditions"]}

    for edge in _edges(router["uid"]):
        command = outputs.get(edge.get("sourceoutputuid"))
        if command is None:
            continue
        # add_id keeps its own slice-2 chain; it is exercised elsewhere.
        if command == "add_id":
            continue

        seen = set()
        stack = [edge["destinationuid"]]
        while stack:
            uid = stack.pop()
            if uid in seen:
                continue
            seen.add(uid)
            stack.extend(e["destinationuid"] for e in connections.get(uid, []))

        reachedScripts = {
            byUid[uid]["config"]["scriptfile"]
            for uid in seen
            if byUid.get(uid, {}).get("config", {}).get("scriptfile")
        }
        assert f"scripts/{command}_create.sh" in reachedScripts, command
        assert f"scripts/{command}_success.sh" in reachedScripts, command
