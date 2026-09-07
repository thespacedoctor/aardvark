import json
import logging
import os

import pytest
import requests

from aardvark_jd import background_sync, db, http_retry
from aardvark_jd.background_sync import SyncBusy
from aardvark_jd.craft_client import CraftApiError

log = logging.getLogger("test_background_sync")
log.addHandler(logging.NullHandler())


@pytest.fixture
def systemRoot(tmp_path, monkeypatch):
    """*a root whose `00_INDEX🗂️` folder holds the db, the lock and the pending flag*"""
    root = tmp_path / "MySystem"
    indexDir = root / "00_INDEX🗂️"
    indexDir.mkdir(parents=True)
    (indexDir / "aardvark.db").write_bytes(b"")
    return str(root)


# ---------------------------------------------------------------- classify_failure

def test_a_budget_exhaustion_is_classified_rate_limited():
    error = http_retry.BackoffBudgetExhausted("budget of 300s exhausted")
    assert background_sync.classify_failure(error) == "rate-limited"


def test_a_connection_error_is_classified_network():
    assert background_sync.classify_failure(requests.ConnectionError("reset")) == "network"
    assert background_sync.classify_failure(requests.Timeout("slow")) == "network"


def test_a_429_message_is_classified_rate_limited():
    error = RuntimeError("craft API POST /blocks failed (429): Rate limit exceeded")
    assert background_sync.classify_failure(error) == "rate-limited"


def test_an_auth_failure_is_classified_auth():
    error = RuntimeError("craft API GET /folders failed (401): invalid token")
    assert background_sync.classify_failure(error) == "auth"


def test_a_craft_not_found_failure_is_classified_not_found():
    error = CraftApiError(
        "craft API GET /blocks failed (404): Block not found",
        method="GET", path="/blocks", statusCode=404,
    )
    assert background_sync.classify_failure(error) == "not-found"


def test_a_404_that_reads_as_an_auth_failure_is_classified_auth():
    # A REVOKED CRAFT CONNECTION RETURNS 404 FOR EVERY PATH WITH AN AUTH BODY;
    # CLASSING IT `not-found` WOULD TELL THE USER TO RETRY A TOKEN THAT IS DEAD.
    error = CraftApiError(
        "craft API GET /blocks failed (404): invalid token",
        method="GET", path="/blocks", statusCode=404,
    )
    assert background_sync.classify_failure(error) == "auth"


def test_a_craft_api_error_that_is_not_a_404_still_uses_the_message():
    rateLimited = CraftApiError(
        "craft API POST /blocks failed (429): Rate limit exceeded",
        method="POST", path="/blocks", statusCode=429,
    )
    assert background_sync.classify_failure(rateLimited) == "rate-limited"

    serverError = CraftApiError(
        "craft API POST /blocks failed (500): boom", method="POST", path="/blocks", statusCode=500,
    )
    assert background_sync.classify_failure(serverError) == "unknown"


def test_an_unrecognised_failure_is_classified_unknown():
    assert background_sync.classify_failure(RuntimeError("something odd")) == "unknown"


# ---------------------------------------------------------------- the lock

def test_acquiring_a_free_lock_records_this_process(systemRoot):
    pathToLock = background_sync.acquire_lock(systemRoot)
    try:
        with open(pathToLock) as stream:
            held = json.load(stream)
        assert held["pid"] == os.getpid()
    finally:
        background_sync.release_lock(pathToLock)


def test_a_second_acquire_while_a_live_process_holds_it_raises_syncbusy(systemRoot, monkeypatch):
    pathToLock = background_sync.acquire_lock(systemRoot)
    try:
        with pytest.raises(SyncBusy):
            background_sync.acquire_lock(systemRoot)
    finally:
        background_sync.release_lock(pathToLock)


def test_a_lock_held_by_a_dead_process_is_taken_over(systemRoot, monkeypatch):
    """*the worst failure on this map is a stale lock that stops syncing forever*"""
    deadPid = 999_999
    with open(background_sync.lock_path(systemRoot), "w") as stream:
        json.dump({"pid": deadPid, "startedAt": 0.0}, stream)
    monkeypatch.setattr(background_sync, "_pid_is_alive", lambda pid: pid != deadPid)

    pathToLock = background_sync.acquire_lock(systemRoot)

    with open(pathToLock) as stream:
        assert json.load(stream)["pid"] == os.getpid()
    background_sync.release_lock(pathToLock)


def test_a_live_but_ancient_lock_is_taken_over_as_a_pid_reuse_backstop(systemRoot, monkeypatch):
    monkeypatch.setattr(background_sync, "_pid_is_alive", lambda pid: True)
    with open(background_sync.lock_path(systemRoot), "w") as stream:
        json.dump({"pid": 4242, "startedAt": 1000.0}, stream)

    tooLate = 1000.0 + background_sync.STALE_LOCK_CUTOFF_SECONDS + 1
    pathToLock = background_sync.acquire_lock(systemRoot, now=tooLate)

    with open(pathToLock) as stream:
        assert json.load(stream)["pid"] == os.getpid()
    background_sync.release_lock(pathToLock)


def test_a_live_lock_inside_the_cutoff_is_not_stolen(systemRoot, monkeypatch):
    """*a healthy long sync must keep its lock - the cutoff exceeds the backoff budget*"""
    monkeypatch.setattr(background_sync, "_pid_is_alive", lambda pid: True)
    with open(background_sync.lock_path(systemRoot), "w") as stream:
        json.dump({"pid": 4242, "startedAt": 1000.0}, stream)

    stillWorking = 1000.0 + http_retry.RUN_BACKOFF_BUDGET_SECONDS + 1
    with pytest.raises(SyncBusy):
        background_sync.acquire_lock(systemRoot, now=stillWorking)


def test_the_stale_cutoff_exceeds_the_backoff_budget():
    """*derived from ticket 14's budget, not chosen separately*"""
    assert background_sync.STALE_LOCK_CUTOFF_SECONDS > http_retry.RUN_BACKOFF_BUDGET_SECONDS


def test_a_corrupt_lockfile_is_treated_as_stale(systemRoot):
    """*a half-written lock must not stop syncing forever*"""
    with open(background_sync.lock_path(systemRoot), "w") as stream:
        stream.write("{not json")

    pathToLock = background_sync.acquire_lock(systemRoot)

    with open(pathToLock) as stream:
        assert json.load(stream)["pid"] == os.getpid()
    background_sync.release_lock(pathToLock)


def test_releasing_a_lock_another_process_now_holds_leaves_it_alone(systemRoot):
    pathToLock = background_sync.acquire_lock(systemRoot)
    # SOMEONE ELSE STOLE IT AS STALE AND IS NOW MID-RUN.
    with open(pathToLock, "w") as stream:
        json.dump({"pid": os.getpid() + 1, "startedAt": 0.0}, stream)

    background_sync.release_lock(pathToLock)

    assert os.path.exists(pathToLock)
    os.unlink(pathToLock)


# ---------------------------------------------------------------- the pending flag

def test_take_pending_is_false_when_nothing_was_flagged(systemRoot):
    assert background_sync.take_pending(systemRoot) is False


def test_set_then_take_pending_round_trips_and_consumes(systemRoot):
    background_sync.set_pending(systemRoot)
    assert background_sync.take_pending(systemRoot) is True
    assert background_sync.take_pending(systemRoot) is False


# ---------------------------------------------------------------- run_sync

class _FakeEngine:
    """*stands in for one of the three sync engines, scripted to succeed or raise*"""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.runs = 0
        self.budgets = []

    def __call__(self, log, dbConn, settings, budget=None, announce=None):
        self.budgets.append(budget)
        return self

    def get(self):
        self.runs += 1
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        return {}


@pytest.fixture
def indexDb():
    conn = db.get_connection(":memory:")
    db.initialise_schema(conn)
    yield conn
    conn.close()


def _patch_engines(monkeypatch, gdrive=None, todoist=None, craft=None):
    """*swap the three engines `run_mirrors` imports for scripted fakes*"""
    import aardvark_jd.craft_sync as craftModule
    import aardvark_jd.gdrive_sync as gdriveModule
    import aardvark_jd.todoist_sync as todoistModule

    engines = {}
    for name, module, attribute, fake in (
        ("gdrive", gdriveModule, "gdrive_sync", gdrive),
        ("todoist", todoistModule, "todoist_sync", todoist),
        ("craft", craftModule, "craft_sync", craft),
    ):
        engine = fake if fake is not None else _FakeEngine([])
        monkeypatch.setattr(module, attribute, engine)
        engines[name] = engine
    return engines


_ALL_ENABLED = {
    "gdrive": {"enabled": True},
    "todoist": {"enabled": True},
    "craft": {"enabled": True},
}


def test_run_mirrors_records_a_success_marker_for_every_enabled_mirror(indexDb, monkeypatch):
    _patch_engines(monkeypatch)

    failures, abandoned = background_sync.run_mirrors(log, indexDb, _ALL_ENABLED)

    assert failures == []
    assert abandoned is False
    assert db.drifted_mirrors(indexDb) == []
    rows = indexDb.execute("SELECT mirror FROM sync_drift").fetchall()
    assert {row["mirror"] for row in rows} == {"gdrive", "todoist", "craft"}


def test_a_disabled_mirror_is_skipped_entirely(indexDb, monkeypatch):
    engines = _patch_engines(monkeypatch)

    background_sync.run_mirrors(log, indexDb, {"craft": {"enabled": True}})

    assert engines["gdrive"].runs == 0
    assert engines["craft"].runs == 1


def test_one_mirror_failing_does_not_stop_the_others(indexDb, monkeypatch):
    """*the mirrors are independent products - a Drive outage must not leave craft stale*"""
    engines = _patch_engines(monkeypatch, gdrive=_FakeEngine([RuntimeError("drive exploded")]))

    failures, abandoned = background_sync.run_mirrors(log, indexDb, _ALL_ENABLED)

    assert [mirror for mirror, _reason, _cls in failures] == ["gdrive"]
    assert engines["todoist"].runs == 1
    assert engines["craft"].runs == 1
    assert [row["mirror"] for row in db.drifted_mirrors(indexDb)] == ["gdrive"]


def test_a_later_success_clears_an_earlier_drift_marker(indexDb, monkeypatch):
    _patch_engines(monkeypatch, craft=_FakeEngine([RuntimeError("429 rate limit")]))
    background_sync.run_mirrors(log, indexDb, {"craft": {"enabled": True}})
    assert [row["mirror"] for row in db.drifted_mirrors(indexDb)] == ["craft"]

    _patch_engines(monkeypatch)
    background_sync.run_mirrors(log, indexDb, {"craft": {"enabled": True}})

    assert db.drifted_mirrors(indexDb) == []


def test_a_drift_marker_records_the_reason_class(indexDb, monkeypatch):
    _patch_engines(monkeypatch, craft=_FakeEngine([RuntimeError("failed (401): bad token")]))

    background_sync.run_mirrors(log, indexDb, {"craft": {"enabled": True}})

    drifted = db.drifted_mirrors(indexDb)[0]
    assert drifted["last_failure_class"] == "auth"
    assert "bad token" in drifted["last_failure_reason"]


def test_run_sync_repeats_the_repair_when_a_mutation_arrived_mid_run(indexDb, systemRoot, monkeypatch):
    """*the pending flag is re-checked on completion, so the loop drains as the user stops typing*"""
    craft = _FakeEngine([])

    originalGet = craft.get
    def getThenFlagOnce():
        result = originalGet()
        if craft.runs == 1:
            background_sync.set_pending(systemRoot)
        return result
    craft.get = getThenFlagOnce
    _patch_engines(monkeypatch, craft=craft)

    background_sync.run_sync(log, indexDb, {"craft": {"enabled": True}}, systemRoot)

    assert craft.runs == 2
    assert background_sync.take_pending(systemRoot) is False


def test_an_abandoned_run_clears_the_pending_flag_and_does_not_loop(indexDb, systemRoot, monkeypatch):
    """*the hot loop: a rate-limited sync must not restart itself forever, unwatched*"""
    craft = _FakeEngine([http_retry.BackoffBudgetExhausted("budget exhausted")])
    _patch_engines(monkeypatch, craft=craft)
    background_sync.set_pending(systemRoot)

    failures = background_sync.run_sync(log, indexDb, {"craft": {"enabled": True}}, systemRoot)

    assert craft.runs == 1
    assert [cls for _m, _r, cls in failures] == ["rate-limited"]
    assert background_sync.take_pending(systemRoot) is False


def test_run_sync_flags_pending_and_returns_when_another_sync_holds_the_lock(indexDb, systemRoot, monkeypatch):
    engines = _patch_engines(monkeypatch)
    heldLock = background_sync.acquire_lock(systemRoot)
    try:
        failures = background_sync.run_sync(log, indexDb, _ALL_ENABLED, systemRoot)
    finally:
        background_sync.release_lock(heldLock)

    assert failures == []
    assert engines["craft"].runs == 0
    assert background_sync.take_pending(systemRoot) is True


def test_run_sync_releases_the_lock_even_when_a_mirror_raises(indexDb, systemRoot, monkeypatch):
    _patch_engines(monkeypatch, craft=_FakeEngine([RuntimeError("boom")]))

    background_sync.run_sync(log, indexDb, {"craft": {"enabled": True}}, systemRoot)

    assert not os.path.exists(background_sync.lock_path(systemRoot))


# ---------------------------------------------------------------- the spawn

def test_spawn_detached_runs_craft_sync_in_its_own_session(monkeypatch):
    captured = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            self.pid = 4321

    monkeypatch.setattr(background_sync.subprocess, "Popen", FakePopen)

    pid = background_sync.spawn_detached(pathToSettingsFile="/tmp/settings.yaml", log=log)

    assert pid == 4321
    # THE MODULE, NOT THE `av` CONSOLE SCRIPT - SAME INTERPRETER, NO `PATH` DEPENDENCE.
    # `-P` KEEPS THE CHILD'S CWD OFF `sys.path`, SO A STRAY `aardvark_jd/` OR
    # `requests.py` IN THE DIRECTORY THE USER HAPPENED TO RUN FROM CANNOT BE
    # IMPORTED BY THE BACKGROUND SYNC.
    assert captured["command"][:4] == [
        background_sync.sys.executable, "-P", "-m", "aardvark_jd.cl_utils",
    ]
    assert captured["command"][4] == "craft_sync"
    assert captured["command"][-2:] == ["-s", "/tmp/settings.yaml"]
    assert captured["kwargs"]["start_new_session"] is True


def test_spawn_detached_warns_but_does_not_raise_when_the_spawn_fails(monkeypatch, capsys):
    def boom(command, **kwargs):
        raise OSError("no fork for you")

    monkeypatch.setattr(background_sync.subprocess, "Popen", boom)

    assert background_sync.spawn_detached(log=log) is None
    assert "could not start the background sync" in capsys.readouterr().err


def test_pid_liveness_treats_a_foreign_process_as_alive(monkeypatch):
    """*`PermissionError` means the pid exists but is someone else's - not a free lock*"""
    def notYours(pid, signal):
        raise PermissionError("not yours")

    monkeypatch.setattr(background_sync.os, "kill", notYours)
    assert background_sync._pid_is_alive(4242) is True


def test_pid_liveness_is_false_for_a_dead_process(monkeypatch):
    def gone(pid, signal):
        raise ProcessLookupError("gone")

    monkeypatch.setattr(background_sync.os, "kill", gone)
    assert background_sync._pid_is_alive(4242) is False


def test_losing_the_race_to_replace_a_stale_lock_concedes(systemRoot, monkeypatch):
    """*two runs both spotting the same stale lock must not both proceed*"""
    with open(background_sync.lock_path(systemRoot), "w") as stream:
        json.dump({"pid": 999_999, "startedAt": 0.0}, stream)
    monkeypatch.setattr(background_sync, "_pid_is_alive", lambda pid: pid == 999_999 + 1)

    realOpen = background_sync.os.open

    def alwaysTaken(path, flags, mode=0o777):
        # THE OTHER RUN RECREATES THE LOCK BETWEEN OUR UNLINK AND OUR CREATE,
        # EVERY TIME - SO THE SECOND ATTEMPT MUST CONCEDE RATHER THAN LOOP.
        if flags & os.O_EXCL:
            raise FileExistsError(path)
        return realOpen(path, flags, mode)

    monkeypatch.setattr(background_sync.os, "open", alwaysTaken)

    with pytest.raises(SyncBusy):
        background_sync.acquire_lock(systemRoot)


def test_releasing_an_already_removed_lock_is_harmless(systemRoot):
    pathToLock = background_sync.acquire_lock(systemRoot)
    os.unlink(pathToLock)
    background_sync.release_lock(pathToLock)  # MUST NOT RAISE


def test_set_pending_swallows_a_write_failure(systemRoot, monkeypatch):
    """*the flag is an optimisation - the next mutating command spawns a fresh sync regardless*"""
    monkeypatch.setattr(
        background_sync, "pending_path", lambda rootPath: "/no/such/dir/.sync.pending",
    )
    background_sync.set_pending(systemRoot)  # MUST NOT RAISE


def test_the_three_mirrors_share_one_backoff_budget(indexDb, monkeypatch):
    """*a command's total backoff is bounded however many mirrors it runs*

    This is what `STALE_LOCK_CUTOFF_SECONDS` is derived from: per-mirror
    budgets would put a legitimate run's worst case at three times the
    cutoff's own basis, so a healthy-but-throttled sync could have its
    lock stolen mid-flight.
    """
    engines = _patch_engines(monkeypatch)

    background_sync.run_mirrors(log, indexDb, _ALL_ENABLED)

    handedOut = [engines[name].budgets[0] for name in ("gdrive", "todoist", "craft")]
    assert all(budget is not None for budget in handedOut)
    assert handedOut[0] is handedOut[1] is handedOut[2]


def test_the_stale_lock_cutoff_exceeds_one_whole_invocation_of_backoff(indexDb, monkeypatch):
    """*the cutoff must clear the worst-case legitimate run, budget included*"""
    engines = _patch_engines(monkeypatch)
    background_sync.run_mirrors(log, indexDb, _ALL_ENABLED)
    sharedBudget = engines["craft"].budgets[0]

    assert (
        background_sync.STALE_LOCK_CUTOFF_SECONDS
        > sharedBudget.totalSeconds
    )


# ---------------------------------------------------------------- held_lock

def test_held_lock_takes_and_releases_the_lock(systemRoot):
    with background_sync.held_lock(systemRoot, log):
        assert os.path.exists(background_sync.lock_path(systemRoot))
    assert not os.path.exists(background_sync.lock_path(systemRoot))


def test_held_lock_warns_and_proceeds_when_a_background_sync_holds_it(systemRoot, capsys):
    """*an explicitly requested foreground sync proceeds - silently doing nothing is worse*"""
    otherRunsLock = background_sync.acquire_lock(systemRoot)
    try:
        with background_sync.held_lock(systemRoot, log):
            ranAnyway = True
    finally:
        background_sync.release_lock(otherRunsLock)

    assert ranAnyway is True
    assert "a background sync is already running" in capsys.readouterr().err


def test_held_lock_does_not_release_a_lock_it_never_took(systemRoot):
    otherRunsLock = background_sync.acquire_lock(systemRoot)
    try:
        with background_sync.held_lock(systemRoot, log):
            pass
        # THE OTHER RUN'S LOCK SURVIVES OURS EXITING.
        assert os.path.exists(otherRunsLock)
    finally:
        background_sync.release_lock(otherRunsLock)


@pytest.mark.parametrize("badPid", [0, -1, -999])
def test_a_lockfile_with_a_special_pid_is_treated_as_stale(systemRoot, badPid):
    """*`os.kill` reports pid 0 and negatives as "alive", so they must never reach it*

    Pid `0` means the caller's process group and `-1` every process the
    user may signal; both succeed for signal 0. An unvalidated value here
    would defeat the liveness check and hold the lock until the age cutoff.
    """
    with open(background_sync.lock_path(systemRoot), "w") as stream:
        json.dump({"pid": badPid, "startedAt": 0.0}, stream)

    assert background_sync.is_lock_stale(background_sync.lock_path(systemRoot)) is True

    pathToLock = background_sync.acquire_lock(systemRoot)
    with open(pathToLock) as stream:
        assert json.load(stream)["pid"] == os.getpid()
    background_sync.release_lock(pathToLock)


@pytest.mark.parametrize("badPid", [2 ** 31, 1e999])
def test_a_lockfile_with_an_out_of_range_pid_is_treated_as_stale(systemRoot, badPid):
    """*an oversized pid must not escape as `OverflowError` and stop syncing silently*

    `os.kill` raises `OverflowError` above the C `int` range, and a JSON
    `1e999` parses to `inf` and raises the same from `int()`. Neither is
    an `OSError`, so an unguarded one would leave `acquire_lock` as a
    traceback into the detached child's `/dev/null`.
    """
    with open(background_sync.lock_path(systemRoot), "w") as stream:
        stream.write(json.dumps({"pid": badPid, "startedAt": 0.0}))

    assert background_sync.is_lock_stale(background_sync.lock_path(systemRoot)) is True

    pathToLock = background_sync.acquire_lock(systemRoot)
    background_sync.release_lock(pathToLock)


def test_set_pending_refuses_to_follow_a_symlink(systemRoot, tmp_path):
    """*a symlink planted at the flag path must not redirect the write onto another file*"""
    target = tmp_path / "innocent.txt"
    target.write_text("do not clobber me")
    os.symlink(str(target), background_sync.pending_path(systemRoot))

    background_sync.set_pending(systemRoot)  # MUST NOT RAISE

    assert target.read_text() == "do not clobber me"
