#!/usr/bin/env python
# encoding: utf-8
"""
*Hand the remote mirroring to a detached process, and record what happened*

A mutating command mirrors the tree out to Google Drive, Todoist and
craft.do, and measurement put `av add_project` at 30.7 s against a 500 ms
target - 29.9 s of it network, across services in a fixed order with no
single dominant offender left to optimise away. So the mutating commands
now do their local work, spawn `av craft_sync` in a new session, and
exit. See `docs/adr/0001-mutating-commands-hand-sync-to-a-detached-process.md`.

Three mechanisms live here:

- **The spawn.** `spawn_detached` starts `craft_sync` - which already runs
  `gdrive -> todoist -> craft` in the mandated order - in its own session,
  with its streams at `/dev/null`, and returns immediately. One spawn of a
  command that already exists, and so no new sync code path.
- **The lock.** At most one sync runs at a time, held by a lockfile beside
  `aardvark.db` inside `00_INDEX🗂️` (per-system by construction, and
  per-machine for free because `dropbox_ignore` excludes that directory).
  A mutation arriving while a sync runs sets a **pending flag** rather than
  starting a second writer; the running sync re-checks it on completion and
  goes round again. Not a queue - a whole-tree repair subsumes every
  mutation made during the previous run, so one slot is enough and the loop
  drains as soon as the user stops typing.
- **The drift marker.** The process that would have reported a failure has
  exited, so each mirror's outcome is recorded in `sync_drift` instead
  (`db.record_sync_success` / `db.record_sync_failure`), `browse` renders
  it, and the next command prints a one-line warning.

**A stale lock is the worst available failure on this map** - it would stop
syncing silently and permanently, fixed only by deleting a file the user
does not know exists. So the lockfile carries a pid and a start time, and
is treated as stale when the pid is gone, with an age cutoff as a backstop
against pid reuse. That cutoff is *derived from* `http_retry`'s per-run
backoff budget rather than chosen separately: it must exceed the longest
legitimate run, or a healthy sync has its lock stolen mid-flight.

Author
: David Young
"""

import contextlib
import json
import os
import subprocess
import sys
import time

import requests

from aardvark_jd import db, http_retry
from aardvark_jd.craft_client import CraftApiError

# A PID MUST FIT A C `int` OR `os.kill` RAISES `OverflowError` RATHER THAN
# REPORTING THE PROCESS MISSING.
_MAX_PID = 2 ** 31 - 1

_LOCK_BASENAME = ".sync.lock"
_PENDING_BASENAME = ".sync.pending"

# A LEGITIMATE RUN IS ITS ACTUAL NETWORK WORK PLUS, AT WORST, THE WHOLE
# BACKOFF BUDGET. DERIVED FROM THAT BUDGET RATHER THAN PICKED SEPARATELY -
# TWO MAGIC NUMBERS IN SEPARATE MODULES WOULD DRIFT APART, AND A CUTOFF
# BELOW THE BUDGET WOULD STEAL A HEALTHY SYNC'S LOCK MID-FLIGHT.
SYNC_WORK_ALLOWANCE_SECONDS = 600
STALE_LOCK_CUTOFF_SECONDS = (
    http_retry.RUN_BACKOFF_BUDGET_SECONDS + SYNC_WORK_ALLOWANCE_SECONDS
)


class SyncBusy(Exception):
    """*raised when another sync already holds the lock; the caller sets the pending flag instead*"""


def classify_failure(error):
    """
    *the reason class a drift marker records for a failed mirror*

    "craft is rate limited" resolves itself and "craft's token expired"
    never will, and those need opposite responses from the user - so the
    marker carries a class, not merely a message.

    **Key Arguments:**

    - ``error`` -- the exception that ended the mirror's run

    **Return:**

    - ``failureClass`` -- `rate-limited`, `auth`, `network`, `not-found` or `unknown`
    """
    if isinstance(error, http_retry.BackoffBudgetExhausted):
        return "rate-limited"
    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return "network"

    message = str(error).lower()
    if "429" in message or "rate limit" in message or "ratelimitexceeded" in message:
        return "rate-limited"
    if "401" in message or "403" in message or "unauthor" in message or "token" in message:
        return "auth"
    # A STRUCTURED 404 IS BENIGN DRIFT - A DOCUMENT DELETED IN CRAFT - BUT ONLY
    # ONCE THE MESSAGE HAS BEEN RULED OUT AS AN AUTH FAILURE FIRST: A REVOKED
    # CRAFT CONNECTION RETURNS 404 FOR EVERY PATH, AND `not-found` READS TO THE
    # USER AS "JUST RETRY" WHERE `auth` TELLS THEM THE TOKEN IS DEAD.
    if isinstance(error, CraftApiError) and error.statusCode == 404:
        return "not-found"
    if "timed out" in message or "connection" in message:
        return "network"
    return "unknown"


# ---------------------------------------------------------------------- #
# the lock and the pending flag
# ---------------------------------------------------------------------- #

def _index_dir(rootPath):
    """*the `00_INDEX🗂️` directory holding the database, the lock and the pending flag*"""
    from aardvark_jd import paths

    return os.path.dirname(paths.find_db_path(rootPath))


def lock_path(rootPath):
    """*where this system's sync lockfile lives*"""
    return os.path.join(_index_dir(rootPath), _LOCK_BASENAME)


def pending_path(rootPath):
    """*where this system's pending-sync flag lives*"""
    return os.path.join(_index_dir(rootPath), _PENDING_BASENAME)


def _pid_is_alive(pid):
    """
    *is a process with this pid currently running?*

    Signal 0 also succeeds for a **zombie** - a process that has exited but
    whose parent has not reaped it - so this reports a zombie as alive. That
    is harmless here, and only because of who asks: the staleness check runs
    in a later, unrelated `aardvark` process, by which time the sync's parent
    (the mutating command that spawned it) has long exited and the child has
    been reparented and reaped. A caller that spawned the sync *and stayed
    alive* would see its own exited child as alive until it waited on it.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # THE PROCESS EXISTS BUT BELONGS TO SOMEONE ELSE - STILL ALIVE.
        return True
    return True


def _read_lock(pathToLock):
    """
    *the lockfile's recorded pid and start time, or `None` if it is absent or unreadable*

    A corrupt lockfile is treated as absent rather than as a permanent
    block: a half-written file must not be able to stop syncing forever.

    The pid is rejected unless it is a real process id, at **both** ends.
    `os.kill` gives `0` and negative values special meanings - the caller's
    process group, and every process the user may signal - and both report
    "alive", so an unvalidated `0` or `-1` would make the liveness check
    useless. A value above the C `int` range raises `OverflowError` from
    `os.kill`, and a JSON `1e999` parses to `inf` and raises the same from
    `int()`; neither is an `OSError`, so an unguarded one would escape
    `acquire_lock` as a traceback into the detached child's `/dev/null` and
    stop syncing silently on every spawn until the age cutoff - exactly the
    failure this module exists to prevent.

    The file lives in a Dropbox-synced tree, and the exclusion that keeps
    it local is macOS-only, so an odd value can arrive from another machine
    as well as from a half-written local write.
    """
    try:
        with open(pathToLock) as stream:
            held = json.load(stream)
        pid = int(held["pid"])
        startedAt = float(held["startedAt"])
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return None
    if not 1 <= pid <= _MAX_PID:
        return None
    return pid, startedAt


def is_lock_stale(pathToLock, now=None):
    """
    *does an existing lockfile belong to a process that is no longer running, or has run too long?*

    **Key Arguments:**

    - ``pathToLock`` -- the lockfile path
    - ``now`` -- the current epoch time, for tests. Default `None`, meaning `time.time()`.

    **Return:**

    - ``stale`` -- `True` if the lock can safely be taken over
    """
    held = _read_lock(pathToLock)
    if held is None:
        # UNREADABLE OR CORRUPT - TAKING IT OVER IS SAFER THAN NEVER SYNCING AGAIN.
        return True
    pid, startedAt = held
    if not _pid_is_alive(pid):
        return True
    # THE PID IS ALIVE, BUT PIDS ARE REUSED - AN AGE BACKSTOP CATCHES A
    # LOCKFILE WHOSE RECORDED PID NOW BELONGS TO AN UNRELATED PROCESS.
    return (now if now is not None else time.time()) - startedAt > STALE_LOCK_CUTOFF_SECONDS


def acquire_lock(rootPath, now=None):
    """
    *take the sync lock, or raise `SyncBusy` if a live sync already holds it*

    Uses `O_CREAT | O_EXCL`, so two processes racing to create the file
    cannot both win. A lock whose holder is gone (or which has outlived
    `STALE_LOCK_CUTOFF_SECONDS`) is removed and retaken.

    **Key Arguments:**

    - ``rootPath`` -- the aardvark system root
    - ``now`` -- the current epoch time, for tests. Default `None`.

    **Return:**

    - ``pathToLock`` -- the path of the lock now held

    **Raises:**

    - ``SyncBusy`` -- another live sync holds the lock
    """
    pathToLock = lock_path(rootPath)
    payload = json.dumps({
        "pid": os.getpid(),
        "startedAt": now if now is not None else time.time(),
    })

    for attempt in (1, 2):
        try:
            handle = os.open(
                pathToLock,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o644,
            )
        except FileExistsError:
            if attempt == 2 or not is_lock_stale(pathToLock, now=now):
                raise SyncBusy(f"another sync is already running (lock: {pathToLock})")
            # STALE - CLEAR IT AND TRY EXACTLY ONCE MORE. IF ANOTHER PROCESS
            # WINS THE RACE TO RECREATE IT, THE SECOND ATTEMPT CONCEDES.
            try:
                os.unlink(pathToLock)
            except FileNotFoundError:
                pass
        else:
            with os.fdopen(handle, "w") as stream:
                stream.write(payload)
            return pathToLock

    raise SyncBusy(f"another sync is already running (lock: {pathToLock})")


def release_lock(pathToLock):
    """
    *release a sync lock this process holds*

    Only removes a lockfile recording **this** process's pid, so a lock
    already stolen as stale by another run is left to its new owner.

    That read-then-unlink is **not atomic**, and POSIX offers no way to
    make it so on a plain path. If our run overran the stale cutoff and
    another run stole the lock in the window between the two, we would
    unlink a live lock. Reaching that window at all requires the cutoff
    to have already been exceeded, which is itself the failure the cutoff
    is sized to prevent; the consequence is one extra concurrent sync,
    not corruption, and the next run re-establishes a single holder.

    **Key Arguments:**

    - ``pathToLock`` -- the lockfile path, as returned by `acquire_lock`
    """
    held = _read_lock(pathToLock)
    if held is not None and held[0] != os.getpid():
        return
    try:
        os.unlink(pathToLock)
    except FileNotFoundError:
        pass


@contextlib.contextmanager
def held_lock(rootPath, log):
    """
    *hold the sync lock for a foreground sync, or run anyway with a warning if it is busy*

    For the `connect_*` and explicit `*_sync` commands, which sync in the
    foreground rather than through `run_sync`. Without this they could
    write the mirrors and the index concurrently with a detached carrier
    spawned by an earlier mutating command.

    A busy lock **warns and proceeds** rather than refusing: the user
    asked for this sync explicitly and in the foreground, and silently
    doing nothing would be worse than the overlap. That is the same
    judgement `connect_*` already makes by staying in the foreground at
    all - a first backfill is the run the user is most invested in seeing
    finish.

    **Key Arguments:**

    - ``rootPath`` -- the aardvark system root
    - ``log`` -- logger
    """
    pathToLock = None
    try:
        pathToLock = acquire_lock(rootPath)
    except SyncBusy:
        log.warning("a background sync is already running; this foreground sync overlaps it")
        print(
            "note: a background sync is already running - this may duplicate its work",
            file=sys.stderr,
        )
    except OSError as error:
        # THE LOCK IS A GUARD, NOT A GATE - AN UNREACHABLE INDEX DIRECTORY IS
        # THE NEXT LINE'S PROBLEM, NOT A REASON TO REFUSE THE SYNC.
        log.warning("could not take the sync lock: %s", error)

    try:
        yield
    finally:
        if pathToLock is not None:
            release_lock(pathToLock)


def set_pending(rootPath):
    """
    *record that a mutation arrived while a sync was running*

    One slot, not a queue: the running sync's whole-tree repair subsumes
    every mutation made during it, so a second marker would buy nothing.

    **Key Arguments:**

    - ``rootPath`` -- the aardvark system root
    """
    try:
        # `O_NOFOLLOW` SO A SYMLINK PLANTED AT THIS PATH CANNOT REDIRECT THE
        # WRITE ONTO ANOTHER FILE. THE LOCK IS SAFE WITHOUT IT (`O_EXCL |
        # O_CREAT` REFUSES A SYMLINK), BUT THIS PLAIN TRUNCATING WRITE IS NOT.
        handle = os.open(
            pending_path(rootPath),
            os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW,
            0o644,
        )
        with os.fdopen(handle, "w") as stream:
            stream.write("1")
    except OSError:
        # THE FLAG IS AN OPTIMISATION, NOT A GUARANTEE - THE NEXT MUTATING
        # COMMAND SPAWNS A FRESH SYNC REGARDLESS.
        pass


def take_pending(rootPath):
    """
    *consume the pending flag, returning whether one was set*

    **Key Arguments:**

    - ``rootPath`` -- the aardvark system root

    **Return:**

    - ``wasPending`` -- `True` if a mutation arrived during the run just finished
    """
    try:
        os.unlink(pending_path(rootPath))
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def clear_pending(rootPath):
    """
    *drop the pending flag without acting on it*

    Used by a run that **abandoned** rather than completed. Looping after
    an abandoned run is the hot loop ticket 14 found: a rate-limited sync
    would burn its budget, abandon, see the flag, restart, and repeat
    forever in a detached process nobody is watching. The work is not
    lost - the next mutating command spawns a fresh sync, and a whole-tree
    repair picks up everything missed.

    **Key Arguments:**

    - ``rootPath`` -- the aardvark system root
    """
    take_pending(rootPath)


# ---------------------------------------------------------------------- #
# the spawn
# ---------------------------------------------------------------------- #

def spawn_detached(pathToSettingsFile=None, log=None):
    """
    *start `av craft_sync` in its own session and return immediately*

    Runs the module rather than the `av` console script, so the child is
    guaranteed the same interpreter and virtualenv as the parent with no
    dependence on `PATH`. `start_new_session=True` detaches it from the
    parent's process group, so it survives the shell that spawned it and
    is not killed by a `Ctrl-C` aimed at the parent. Its streams go to
    `/dev/null` - it has no terminal to report to, which is exactly why
    the drift marker exists.

    **Key Arguments:**

    - ``pathToSettingsFile`` -- the settings file to pass through as `-s`, or `None` for the default
    - ``log`` -- logger, for recording the spawn. Default `None`.

    **Return:**

    - ``pid`` -- the detached child's pid, or `None` if the spawn failed
    """
    # `-P` KEEPS THE CHILD'S WORKING DIRECTORY OFF `sys.path`. `python -m`
    # OTHERWISE PREPENDS IT, SO RUNNING A MUTATING COMMAND FROM A DIRECTORY
    # HOLDING A STRAY `aardvark_jd/` OR `requests.py` WOULD HAVE THE
    # BACKGROUND SYNC IMPORT THAT INSTEAD. THE PARENT IS SAFE EITHER WAY -
    # IT RUNS FROM THE `av` CONSOLE SCRIPT, WHICH INJECTS NO CWD.
    command = [sys.executable, "-P", "-m", "aardvark_jd.cl_utils", "craft_sync"]
    if pathToSettingsFile:
        command += ["-s", pathToSettingsFile]

    try:
        with open(os.devnull, "wb") as devnull:
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL, stdout=devnull, stderr=devnull,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as error:
        if log:
            log.warning("could not spawn a background sync: %s", error)
        print(f"warning: could not start the background sync: {error}", file=sys.stderr)
        return None

    if log:
        log.info("spawned a background sync (pid %s)", child.pid)
    return child.pid


# ---------------------------------------------------------------------- #
# the run itself
# ---------------------------------------------------------------------- #

def run_mirrors(log, dbConn, settings, announce=None):
    """
    *run the three mirrors in order, recording each one's outcome as a drift marker*

    The mirrors are independent products, so a failure in one does not
    stop the others: a Drive outage must not leave craft stale when craft
    is healthy. Each mirror's outcome is recorded either way, and the
    degraded output self-heals - when a failed mirror later succeeds, the
    link-row markdown it feeds differs from what was stored and is
    rewritten by the content comparison.

    **Key Arguments:**

    - ``log`` -- logger
    - ``dbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    - ``announce`` -- optional callable for retry messages (foreground prints, background logs). Default `None`.

    **Return:**

    - ``failures`` -- a list of `(mirror, reason, failureClass)`, empty if every enabled mirror succeeded
    - ``abandoned`` -- `True` if any mirror exhausted its backoff budget, so the run must not loop
    """
    from aardvark_jd.craft_sync import craft_sync
    from aardvark_jd.gdrive_sync import gdrive_sync
    from aardvark_jd.todoist_sync import todoist_sync

    # ORDER IS MANDATED, NOT INCIDENTAL: THE TODOIST DESCRIPTION EMBEDS THE
    # DRIVE URL, AND THE CRAFT LINK ROW EMBEDS THE TODOIST URL.
    engines = (
        ("gdrive", "gdrive", gdrive_sync),
        ("todoist", "todoist", todoist_sync),
        ("craft", "craft", craft_sync),
    )

    # ONE BUDGET FOR THE WHOLE INVOCATION, NOT ONE PER MIRROR. THE THREE RUN
    # IN SEQUENCE UNDER A SINGLE LOCK, SO WHAT HAS TO BE BOUNDED IS THE RUN -
    # AND `STALE_LOCK_CUTOFF_SECONDS` IS DERIVED FROM EXACTLY THIS NUMBER.
    # PER-MIRROR BUDGETS WOULD PUT THE WORST CASE AT THREE TIMES THE CUTOFF'S
    # OWN BASIS, SO A HEALTHY-BUT-THROTTLED RUN COULD HAVE ITS LOCK STOLEN.
    budget = http_retry.RunBudget()

    failures = []
    abandoned = False
    for mirror, settingsKey, engine in engines:
        if not (settings.get(settingsKey) or {}).get("enabled"):
            continue
        try:
            engine(
                log=log, dbConn=dbConn, settings=settings, budget=budget, announce=announce,
            ).get()
        except Exception as error:  # noqa: BLE001 - one mirror's failure must not stop the others
            failureClass = classify_failure(error)
            # GATED ON THE EXCEPTION TYPE ALONE. THIS FLAG IS WHAT PREVENTS THE
            # DETACHED RATE-LIMIT HOT LOOP, SO IT MUST NOT DEPEND ON HOW
            # `classify_failure` HAPPENS TO CATEGORISE THINGS TODAY.
            if isinstance(error, http_retry.BackoffBudgetExhausted):
                abandoned = True
            log.warning("%s sync failed (%s): %s", mirror, failureClass, error)
            db.record_sync_failure(dbConn, mirror, str(error), failureClass)
            failures.append((mirror, str(error), failureClass))
        else:
            db.record_sync_success(dbConn, mirror)

    return failures, abandoned


def run_sync(log, dbConn, settings, rootPath, announce=None, now=None):
    """
    *hold the lock, run the mirrors, and go round again if a mutation arrived meanwhile*

    Returns without syncing if another run holds the lock, setting the
    pending flag so that run picks the work up on completion.

    **Key Arguments:**

    - ``log`` -- logger
    - ``dbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    - ``rootPath`` -- the aardvark system root, locating the lock and pending flag
    - ``announce`` -- optional callable for retry messages. Default `None`.
    - ``now`` -- the current epoch time, for tests. Default `None`.

    **Return:**

    - ``failures`` -- the last completed pass's failures, or `[]` if the lock was busy
    """
    try:
        pathToLock = acquire_lock(rootPath, now=now)
    except SyncBusy as busy:
        log.info("%s - flagging the work as pending", busy)
        set_pending(rootPath)
        return []

    try:
        while True:
            failures, abandoned = run_mirrors(log, dbConn, settings, announce=announce)
            if abandoned:
                # AN ABANDONED RUN MUST NOT LOOP - SEE `clear_pending`.
                clear_pending(rootPath)
                return failures
            if not take_pending(rootPath):
                return failures
            log.info("a mutation arrived during the sync - repeating the whole-tree repair")
    finally:
        release_lock(pathToLock)
