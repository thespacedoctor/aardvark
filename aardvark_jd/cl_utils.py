#!/usr/bin/env python
# encoding: utf-8
"""
Documentation for aardvark can be found here: http://aardvark-jd.readthedocs.org

Usage:
    aardvark init <systemName> <parentPath> [-s <pathToSettingsFile>]
    aardvark add_area <domainLetter> <title> <description> [-e <emoji>] [-w] [-s <pathToSettingsFile>]
    aardvark add_category <area> <title> <description> [-e <emoji>] [-w] [-s <pathToSettingsFile>]
    aardvark add_id <category> <title> <description> [--json] [-w] [-s <pathToSettingsFile>]
    aardvark add_project <category> <projectTitle> [-t <templateName>] [-w] [-s <pathToSettingsFile>]
    aardvark archive <ref> [-y] [-w] [-s <pathToSettingsFile>]
    aardvark fd [<term>...] [--json] [--archived] [-s <pathToSettingsFile>]
    aardvark cd <target> [-s <pathToSettingsFile>]
    aardvark open [<path>] [--json] [-s <pathToSettingsFile>]
    aardvark set_emoji <ref> <emoji> [-w] [-s <pathToSettingsFile>]
    aardvark repair_emoji [-w] [-s <pathToSettingsFile>]
    aardvark install_alfred [--uninstall] [-s <pathToSettingsFile>]
    aardvark completion <shell>
    aardvark shell_init <shell>
    aardvark connect_craft <apiUrl> <apiToken> [-s <pathToSettingsFile>]
    aardvark craft_sync [-s <pathToSettingsFile>]
    aardvark connect_todoist <apiToken> [-s <pathToSettingsFile>]
    aardvark todoist_sync [-s <pathToSettingsFile>]
    aardvark connect_dropbox <appKey> <appSecret> [-s <pathToSettingsFile>]
    aardvark connect_gdrive <clientId> <clientSecret> [-s <pathToSettingsFile>]
    aardvark gdrive_sync [-s <pathToSettingsFile>]

Commands:
    init                                   create a new PARA + Johnny Decimal root and index
    add_area                               add a new Johnny Decimal area to `areas`, `resources` or `projects`
    add_category                           add a new Johnny Decimal category to an existing area
    add_id                                 add a new Johnny Decimal ID to an existing category
    add_project                            create a new project (a Johnny Decimal ID) in an existing project category, from a template or blank
    archive                                retire an area, category or ID to the nearest archive folder, freeing its number
    fd                                     browse the index as a tree, or find in it by Johnny Decimal ref, keyword or phrase
    cd                                     change directory into a domain, area, category or ID's folder
    open                                   open the mirrored entities for a path, or pick one interactively
    set_emoji                              change the emoji on an existing folder, moving it and repointing the index
    repair_emoji                           fix drifted folder names/emoji and backfill missing reserved scaffolding
    install_alfred                         install the aardvark workflow into Alfred, and record where aardvark lives on this Mac
    completion                             print the shell completion script for `bash` or `zsh`
    shell_init                             print the shell integration script (`av cd` support plus completion) for `bash` or `zsh`
    connect_craft                          connect a craft.do space and run the initial full mirror
    craft_sync                             re-run the craft.do mirror on demand, to backfill or repair drift
    connect_todoist                        connect a Todoist account and run the initial full mirror
    todoist_sync                           re-run the Todoist mirror on demand, to backfill or repair drift
    connect_dropbox                        connect a Dropbox app and start adding Dropbox share links to synced documents
    connect_gdrive                         connect a Google Drive account and run the initial folder mirror
    gdrive_sync                            re-run the Google Drive folder mirror on demand, to backfill or repair drift

Arguments:
    systemName                             the name of the new system, e.g. "My Life"
    parentPath                             the path in which the system's root folder is created
    domainLetter                           "A" (areas), "R" (resources) or "P" (projects)
    area                                   a domain-prefixed area reference, e.g. "A10" or "A10-19"
    category                               a domain-prefixed category reference, e.g. "A11" or "P11"
    ref                                    what to target: an area ("A10-19"), category ("A11"), ID ("A11.10"), or system folder key ("root.areas")
    templateName                           a category's `04_templates` zip's basename, or "blank"
    projectTitle                           the new project's title
    emoji                                  an emoji character
    title                                  a title
    description                            a description
    term                                   a Johnny Decimal reference, or a search word or phrase
    target                                 a domain letter ("A"), area ("A10-19"), category ("A11") or ID ("A11.10") to change into
    path                                   a filesystem path to resolve to its mirrored entities (default: pick one interactively)
    shell                                  "bash" or "zsh"
    apiUrl                                 a craft.do API connection's unique base URL
    apiToken                               a craft.do or Todoist API connection token
    appKey                                 a Dropbox app's key, from the App Console
    appSecret                              a Dropbox app's secret, from the App Console
    clientId                               a Google Cloud OAuth "Desktop app" client ID
    clientSecret                           a Google Cloud OAuth "Desktop app" client secret

Options:
    -h, --help                             show the everyday commands
    --help-all                             show every command, including setup and maintenance
    -v, --version                          show version
    -e, --emoji <emoji>                    the emoji to use, skipping the suggestion and prompt
    -t, --template <templateName>          the template to use, skipping the interactive picker
    --uninstall                            remove the Alfred workflow symlink and this machine's aardvark pointer
    --json                                 print the machine-readable contract instead of prose (internal and unstable)
    --archived                             include the archived entities, alongside the live ones (`--json` only)
    -y, --yes                              skip the confirmation prompt
    -w, --wait                             wait for the remote mirrors to sync, instead of syncing in the background
    -s, --settings <pathToSettingsFile>    the settings file
"""

import contextlib
import json
import os
import re
import sys

from fundamentals import tools, times

from aardvark_jd import (
    background_sync, change_dir, codes, completion, db, dropbox_ignore, folders, help_text,
    json_output, labels, locate, paths, settings_writer,
)
from aardvark_jd.__version__ import __version__
from aardvark_jd.add_area import add_area
from aardvark_jd.add_category import add_category
from aardvark_jd.add_id import add_id
from aardvark_jd.archive import archive
from aardvark_jd.browse import browse
from aardvark_jd.connect_dropbox import connect_dropbox
from aardvark_jd.connect_gdrive import connect_gdrive
from aardvark_jd.connect_todoist import connect_todoist
from aardvark_jd.craft_sync import craft_sync
from aardvark_jd.gdrive_sync import gdrive_sync
from aardvark_jd.initialiser import initialiser
from aardvark_jd.install_alfred import install_alfred
from aardvark_jd.add_project import add_project
from aardvark_jd.open_craft import open_craft
from aardvark_jd.repair_emoji import repair_emoji
from aardvark_jd.search import search, format_result, tree
from aardvark_jd.set_emoji import set_emoji
from aardvark_jd.todoist_sync import todoist_sync

CLEAR_ERRORS = (
    ValueError,
    KeyError,
    folders.DomainExhaustedError,
    folders.CategoryExhaustedError,
    folders.IdExhaustedError,
)


def main(arguments=None):
    """
    *The main function used when `cl_utils.py` is run as a single script from the cl, or when installed as a cl command*
    """
    # THE COMPLETION HELPER, `cd`, `shell_init` AND THE HELP SCREENS ARE ALL
    # HANDLED BEFORE `fundamentals.tools` RUNS. `__complete` IS NOT DECLARED
    # IN THE docopt USAGE BLOCK AT ALL (docopt WOULD REJECT IT), AND EVEN IF
    # IT WERE, A TAB-COMPLETION MUST NOT PAY FOR SETTINGS-FILE CREATION,
    # LOGGING SETUP OR A SCHEMA MIGRATION - IT HAS TO BE FAST AND STRICTLY
    # READ-ONLY. `cd` RUNS ON EVERY DIRECTORY JUMP, SO IT NEEDS THE SAME
    # GUARANTEE - SEE `change_dir.py`.
    if arguments is None:
        argv = sys.argv[1:]
        if argv[:1] == [completion.COMPLETION_COMMAND]:
            completion.emit(argv[1:])
            return
        if argv[:1] == ["cd"]:
            sys.exit(change_dir.emit(argv[1:]))
        if argv[:1] == ["completion"]:
            print(completion.script(argv[1] if len(argv) > 1 else ""))
            return
        if argv[:1] == ["shell_init"]:
            print(completion.shell_init_script(argv[1] if len(argv) > 1 else ""))
            return
        if "--help-all" in argv:
            print(help_text.full_help(__doc__))
            return
        if not argv or argv[0] in ("-h", "--help"):
            print(help_text.short_help(__doc__))
            return

    # `fundamentals.tools` copies its default settings file into
    # ~/.config/aardvark/ on first run but never creates that directory
    # first, so pre-create it here to avoid a FileNotFoundError.
    os.makedirs(os.path.expanduser("~/.config/aardvark"), exist_ok=True)

    # ON ITS VERY FIRST RUN `fundamentals.tools` ANNOUNCES THE SETTINGS FILE
    # IT JUST WROTE, ON STDOUT. UNDER `--json` THAT PROSE WOULD LAND IN
    # FRONT OF THE CONTRACT OBJECT AND MAKE THE WHOLE STREAM UNPARSEABLE, SO
    # THE WHOLE OF SET-UP'S STDOUT GOES TO STDERR - WHERE HUMAN PROSE
    # BELONGS ANYWAY. THE ANNOUNCEMENT COMES FROM THE CONSTRUCTOR, NOT FROM
    # `setup()`, SO BOTH SIT INSIDE THE REDIRECT.
    setUpOutput = (
        contextlib.redirect_stdout(sys.stderr)
        if _json_requested(arguments)
        else contextlib.nullcontext()
    )
    with setUpOutput:
        su = tools(
            arguments=arguments,
            docString=__doc__,
            logLevel="WARNING",
            options_first=False,
            projectName="aardvark",
            distributionName="aardvark-jd",
            defaultSettingsFile=True,
        )
        arguments, settings, log, dbConn = su.setup()

    a = {}
    for arg, val in list(arguments.items()):
        if arg[0] == "-":
            varname = arg.replace("-", "") + "Flag"
        else:
            varname = arg.replace("<", "").replace(">", "")
        a[varname] = val
        log.debug("%s = %s" % (varname, val))

    startTime = times.get_now_sql_datetime()
    log.info("--- STARTING TO RUN THE cl_utils.py AT %s" % (startTime,))

    try:
        if a["init"]:
            pathToSettingsFile = arguments.get("settingsFile") or arguments.get("--settings")
            rootPath = initialiser(
                log=log, systemName=a["systemName"], parentPath=a["parentPath"],
                pathToSettingsFile=pathToSettingsFile,
            ).get()
            print(f"aardvark system '{a['systemName']}' initialised at {rootPath}")

        elif a["install_alfred"]:
            # DELIBERATELY ABOVE THE "NO SYSTEM" CHECK BELOW. ON A FRESH
            # MACHINE THE ORDER IS INSTALL THE PACKAGE, RUN THIS, THEN POINT
            # THE CLI AT THE TREE - SO THIS COMMAND CANNOT REQUIRE A SYSTEM
            # THAT DOES NOT EXIST YET.
            for message in install_alfred(log=log, uninstall=a["uninstallFlag"]).get():
                print(message)

        else:
            rootPath = (settings.get("system") or {}).get("root_path")
            if not rootPath:
                # UNDER `--json` EVEN THIS EXIT HAS TO BE A PARSEABLE OBJECT ON
                # STDOUT: THE ALFRED WORKFLOW HAS NO ERROR CHANNEL AND RENDERS
                # WHATEVER IT READS THERE AS A ROW.
                if a.get("jsonFlag"):
                    _print_json(json_output.error_envelope_for_kind(
                        json_output.NO_SYSTEM_KIND,
                        "no aardvark system found - run `aardvark init <systemName> <parentPath>` first",
                    ))
                else:
                    print("no aardvark system found - run `aardvark init <systemName> <parentPath>` first", file=sys.stderr)
                sys.exit(1)

            # RE-ASSERT THE DROPBOX IGNORE ON THE INDEX DIRECTORY BEFORE OPENING
            # THE DATABASE, SO A MACHINE THAT CLONED THE TREE EXCLUDES THE INDEX
            # (AND ANY `-wal`/`-shm` SIDECAR) ON ITS FIRST COMMAND. SELF-HEALING,
            # IDEMPOTENT, NEVER FATAL.
            dropbox_ignore.assert_index_ignored(rootPath, log)

            indexDbConn = db.get_connection(paths.find_db_path(rootPath))
            db.initialise_schema(indexDbConn)
            _warn_about_drift(indexDbConn)

            # THE FOREGROUND-SYNCING COMMANDS TAKE THE SAME LOCK THE DETACHED
            # CARRIER USES, SO AN EXPLICIT `av gdrive_sync` CANNOT WRITE THE
            # MIRRORS CONCURRENTLY WITH A BACKGROUND RUN. `craft_sync` IS ABSENT
            # BECAUSE `run_sync` TAKES THE LOCK ITSELF.
            syncLock = (
                background_sync.held_lock(rootPath, log)
                if any(a[command] for command in (
                    "connect_craft", "connect_dropbox", "connect_gdrive",
                    "connect_todoist", "gdrive_sync", "todoist_sync",
                ))
                else contextlib.nullcontext()
            )
            try:
                with syncLock:
                    if a["connect_craft"]:
                        pathToSettingsFile = arguments.get("--settings") or su.configSettingsPath
                        settings.setdefault("craft", {})
                        settings["craft"]["enabled"] = True
                        settings["craft"]["api_url"] = a["apiUrl"]
                        settings["craft"]["api_token"] = a["apiToken"]
                        settings_writer.write_settings(pathToSettingsFile, settings)
                        _maybe_sync_gdrive(log, indexDbConn, settings)
                        _maybe_sync_todoist(log, indexDbConn, settings)
                        summary = craft_sync(log=log, dbConn=indexDbConn, settings=settings).get()
                        print(
                            f"craft connected - folders created: {summary['folders_created']}, "
                            f"documents created: {summary['documents_created']}, "
                            f"indexes refreshed: {summary['indexes_refreshed']}, "
                            f"link rows written: {summary['link_rows_written']}"
                        )
                    elif a["craft_sync"]:
                        # THIS COMMAND IS ALSO THE CARRIER THE MUTATING COMMANDS SPAWN
                        # DETACHED, SO IT - NOT THEY - HOLDS THE LOCK, RECORDS THE DRIFT
                        # MARKERS AND DRAINS THE PENDING FLAG. THAT DUAL ROLE IS WHY THE
                        # ERROR BELOW FIRES ONLY WHEN *NOTHING* IS CONNECTED: GATING IT
                        # ON CRAFT ALONE WOULD MAKE EVERY BACKGROUND SYNC A SILENT NO-OP
                        # FOR A USER WHO HAS CONNECTED, SAY, ONLY GOOGLE DRIVE.
                        if not any((settings.get(mirror) or {}).get("enabled") for mirror in db.MIRRORS):
                            raise ValueError(
                                "craft is not connected - run `aardvark connect_craft <apiUrl> <apiToken>` first"
                            )
                        if not (settings.get("craft") or {}).get("enabled"):
                            print(
                                "note: craft is not connected - syncing the other mirrors only",
                                file=sys.stderr,
                            )
                        failures = background_sync.run_sync(
                            log, indexDbConn, settings, rootPath, announce=_foreground_announcer(),
                        )
                        _report_sync_outcome(failures)
                    elif a["connect_dropbox"]:
                        pathToSettingsFile = arguments.get("--settings") or su.configSettingsPath
                        connect_dropbox(
                            log=log, appKey=a["appKey"], appSecret=a["appSecret"],
                            pathToSettingsFile=pathToSettingsFile,
                        ).get()
                        settings = settings_writer.read_settings(pathToSettingsFile)
                        _maybe_sync_gdrive(log, indexDbConn, settings)
                        _maybe_sync_todoist(log, indexDbConn, settings)
                        summary = craft_sync(log=log, dbConn=indexDbConn, settings=settings).get()
                        print(
                            f"dropbox connected - link rows written: {summary['link_rows_written']}"
                        )
                    elif a["connect_gdrive"]:
                        pathToSettingsFile = arguments.get("--settings") or su.configSettingsPath
                        connect_gdrive(
                            log=log, clientId=a["clientId"], clientSecret=a["clientSecret"],
                            pathToSettingsFile=pathToSettingsFile,
                        ).get()
                        settings = settings_writer.read_settings(pathToSettingsFile)
                        summary = gdrive_sync(log=log, dbConn=indexDbConn, settings=settings).get()
                        print(
                            f"google drive connected - folders created: {summary['folders_created']}, "
                            f"link rows written: {summary['link_rows_written']}"
                        )
                        _maybe_sync_todoist(log, indexDbConn, settings)
                        _maybe_sync_craft(log, indexDbConn, settings)
                    elif a["gdrive_sync"]:
                        summary = gdrive_sync(log=log, dbConn=indexDbConn, settings=settings).get()
                        print(
                            f"google drive synced - folders created: {summary['folders_created']}, "
                            f"link rows written: {summary['link_rows_written']}"
                        )
                        _maybe_sync_todoist(log, indexDbConn, settings)
                        _maybe_sync_craft(log, indexDbConn, settings)
                    elif a["connect_todoist"]:
                        pathToSettingsFile = arguments.get("--settings") or su.configSettingsPath
                        connect_todoist(
                            log=log, apiToken=a["apiToken"], pathToSettingsFile=pathToSettingsFile,
                        ).get()
                        settings = settings_writer.read_settings(pathToSettingsFile)
                        summary = todoist_sync(log=log, dbConn=indexDbConn, settings=settings).get()
                        print(
                            f"todoist connected - projects created: {summary['projects_created']}, "
                            f"descriptions updated: {summary['descriptions_updated']}"
                        )
                        _maybe_sync_craft(log, indexDbConn, settings)
                    elif a["todoist_sync"]:
                        summary = todoist_sync(log=log, dbConn=indexDbConn, settings=settings).get()
                        print(
                            f"todoist synced - projects created: {summary['projects_created']}, "
                            f"descriptions updated: {summary['descriptions_updated']}"
                        )
                        _maybe_sync_craft(log, indexDbConn, settings)
                    else:
                        _dispatch(a, log, indexDbConn, settings)
            finally:
                indexDbConn.close()

    except CLEAR_ERRORS as error:
        # THE SAME FORK AS THE "NO SYSTEM" EXIT ABOVE, AND FOR THE SAME
        # REASON. THE NON-ZERO EXIT STAYS EITHER WAY: IT IS A SECONDARY
        # SIGNAL FOR SHELL USE, WHILE ALFRED READS STDOUT REGARDLESS.
        if a.get("jsonFlag"):
            _print_json(json_output.error_envelope(error))
        else:
            print(f"error: {error}", file=sys.stderr)
        sys.exit(1)

    endTime = times.get_now_sql_datetime()
    runningTime = times.calculate_time_difference(startTime, endTime)
    log.info(
        "-- FINISHED ATTEMPT TO RUN THE cl_utils.py AT %s (RUNTIME: %s) --"
        % (endTime, runningTime,)
    )

    return


def _foreground_announcer():
    """
    *an announcer that prints retry messages, or `None` when nobody is watching*

    Someone who can see why they are waiting will wait; someone watching a
    silent terminal interrupts at about twenty seconds and concludes the
    tool is broken. But `http_retry` routes each message to the announcer
    **or** the log, never both - so handing it an announcer whose `stderr`
    is `/dev/null`, which is exactly the detached carrier's situation,
    would throw the retry detail away entirely. Returning `None` when
    `stderr` is not a terminal keeps those messages in the log, where the
    background run needs them.

    **Return:**

    - ``announce`` -- a callable taking one message, or `None`
    """
    if not sys.stderr.isatty():
        return None

    def announce(message):
        print(f"note: {message}", file=sys.stderr)

    return announce


def _printable(text):
    """
    *strip control characters from text that came back from a remote API*

    A failure reason is ultimately an exception message carrying a
    craft.do / Google / Todoist response body, and under `--wait` it is
    printed straight to a real terminal. Escape sequences in that body
    would otherwise reach the terminal and could move the cursor, rewrite
    the title, or hide what actually failed.

    **Key Arguments:**

    - ``text`` -- the untrusted text

    **Return:**

    - ``printable`` -- the text with C0/C1 control characters removed
    """
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", str(text))


def _report_sync_outcome(failures):
    """
    *print what a foreground sync did, one line per drifted mirror*

    **Key Arguments:**

    - ``failures`` -- `(mirror, reason, failureClass)` triples from `background_sync.run_sync`
    """
    if not failures:
        print("mirrors synced")
        return
    for mirror, reason, failureClass in failures:
        print(
            f"warning: {mirror} sync failed ({failureClass}): {_printable(reason)}",
            file=sys.stderr,
        )


def _warn_about_drift(indexDbConn):
    """
    *print one line if any mirror's last sync failed*

    Sync now happens in a process with no terminal, so a failure has
    nowhere to report to at the time. Surfacing it on the *next* command
    is what stops a failed sync staying invisible until the user happens
    to run `browse`.

    **Key Arguments:**

    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    """
    drifted = db.drifted_mirrors(indexDbConn)
    if not drifted:
        return
    names = ", ".join(row["mirror"] for row in drifted)
    print(
        f"warning: last sync failed for {names} - run `aardvark craft_sync --wait` to retry",
        file=sys.stderr,
    )


def _hand_off_sync(a, log, indexDbConn, settings):
    """
    *give the remote mirroring to a detached process, or run it in the foreground under `--wait`*

    The default is to spawn `av craft_sync` (which already runs
    `gdrive -> todoist -> craft` in the mandated order) and return, so the
    command's own cost is its local work plus a handoff rather than four
    sequential services' round trips. `--wait` forces the foreground path,
    which is what a script chaining onto a mirror URL needs.

    **`--wait` exits non-zero if any mirror failed.** That does not mean
    the command failed: the folder, the index row and the Johnny Decimal
    code all exist. It means the entity was created and a mirror did not
    sync.

    **Key Arguments:**

    - ``a`` -- the friendly-named docopt arguments dict
    - ``log`` -- logger
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict

    **Return:**

    - ``sync`` -- what became of the mirroring: `backgrounded`, `waited` or `none`. The JSON contract reports it; the prose path ignores it.
    """
    if not any((settings.get(mirror) or {}).get("enabled") for mirror in db.MIRRORS):
        return "none"

    rootPath = (settings.get("system") or {}).get("root_path")

    if a.get("waitFlag"):
        failures = background_sync.run_sync(
            log, indexDbConn, settings, rootPath, announce=_foreground_announcer(),
        )
        _report_sync_outcome(failures)
        if failures:
            sys.exit(1)
        return "waited"

    background_sync.spawn_detached(
        pathToSettingsFile=a.get("settingsFlag"), log=log,
    )
    return "backgrounded"


def _maybe_sync_gdrive(log, indexDbConn, settings):
    """
    *push a Google Drive sync after a mutating command, when Drive is connected*

    Must run **first** of the three at every call site. Both the Todoist
    project description and the Craft link row now carry the entity's
    Google Drive URL (see `doc_links.todoist_description_markdown` and
    `doc_links.link_row_markdown`), so the Drive folder has to exist, and
    its link row be written, before either of the others is built. The
    resulting order is gdrive -> todoist -> craft.

    A Drive failure here is reported as a warning rather than raised,
    matching the other two - the filesystem + SQLite mutation that
    triggered it has already succeeded and remains the source of truth.

    **Key Arguments:**

    - ``log`` -- logger
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    """
    if not (settings.get("gdrive") or {}).get("enabled"):
        return
    try:
        gdrive_sync(log=log, dbConn=indexDbConn, settings=settings).get()
    except Exception as error:
        print(f"warning: google drive sync failed: {error}", file=sys.stderr)


def _maybe_sync_todoist(log, indexDbConn, settings):
    """
    *push a Todoist sync after a mutating command, when Todoist is connected*

    Must run after `_maybe_sync_gdrive` and before `_maybe_sync_craft` at
    every call site: the Todoist description embeds the entity's Drive URL,
    and the Craft link row embeds the entity's Todoist URL (see
    `craft_sync._write_link_row`), so Todoist's own project has to exist
    before Craft's sync can link to it. A Todoist failure here is
    reported as a warning rather than raised, matching `_maybe_sync_craft`
    - the filesystem + SQLite mutation that triggered it has already
    succeeded and remains the source of truth.

    **Key Arguments:**

    - ``log`` -- logger
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    """
    if not (settings.get("todoist") or {}).get("enabled"):
        return
    try:
        todoist_sync(log=log, dbConn=indexDbConn, settings=settings).get()
    except Exception as error:
        print(f"warning: todoist sync failed: {error}", file=sys.stderr)


def _maybe_sync_craft(log, indexDbConn, settings):
    """
    *push a craft.do sync after a mutating command, when craft is connected*

    A craft.do failure here is reported as a warning rather than raised,
    since the filesystem + SQLite mutation that triggered it has already
    succeeded and remains the source of truth.

    **Key Arguments:**

    - ``log`` -- logger
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    """
    if not (settings.get("craft") or {}).get("enabled"):
        return
    try:
        craft_sync(log=log, dbConn=indexDbConn, settings=settings).get()
    except Exception as error:
        print(f"warning: craft sync failed: {error}", file=sys.stderr)


def _dispatch(a, log, indexDbConn, settings):
    """
    *dispatch to the relevant worker class for the parsed command, and print its result*

    **Key Arguments:**

    - ``a`` -- the friendly-named docopt arguments dict
    - ``log`` -- logger
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    """
    if a["add_project"]:
        code, title, folderPath, templateUsed = add_project(
            log=log, dbConn=indexDbConn, categoryRef=a["category"], templateName=a["templateFlag"],
            projectTitle=a["projectTitle"], settings=settings,
        ).get()
        print(f"{code}  {title}  {folderPath} (template: {templateUsed})")
        _hand_off_sync(a, log, indexDbConn, settings)

    elif a["add_area"]:
        code, folderPath = add_area(
            log=log, dbConn=indexDbConn, domain=codes.domain_from_letter(a["domainLetter"]),
            title=a["title"], description=a["description"],
            chosenEmoji=a["emojiFlag"], settings=settings,
        ).get()
        print(f"{code}  {folderPath}")
        _hand_off_sync(a, log, indexDbConn, settings)

    elif a["add_category"]:
        domain, _ = codes.split_area_ref(a["area"])
        code, folderPath = add_category(
            log=log, dbConn=indexDbConn, domain=domain, areaRef=a["area"],
            title=a["title"], description=a["description"],
            chosenEmoji=a["emojiFlag"], settings=settings,
        ).get()
        print(f"{code}  {folderPath}")
        _hand_off_sync(a, log, indexDbConn, settings)

    elif a["set_emoji"]:
        label, folderPath = set_emoji(
            log=log, dbConn=indexDbConn, ref=a["ref"], newEmoji=a["emoji"],
        ).get()
        print(f"{label}  {folderPath}")
        _hand_off_sync(a, log, indexDbConn, settings)

    elif a["repair_emoji"]:
        repaired = repair_emoji(log=log, dbConn=indexDbConn).get()
        if not repaired:
            print("every folder already matches the current naming convention")
        for folderKey, folderPath in repaired:
            print(f"{folderKey}  {folderPath}")
        _hand_off_sync(a, log, indexDbConn, settings)

    elif a["add_id"]:
        domain, _ = codes.split_category_ref(a["category"])
        jsonRequested = a.get("jsonFlag")
        code, folderPath, details = add_id(
            log=log, dbConn=indexDbConn, domain=domain, categoryRef=a["category"],
            title=a["title"], description=a["description"], settings=settings,
            # `--json` PROMISES IT NEVER PROMPTS. THAT PROMISE IS THIS FLAG'S
            # TO MAKE, NOT THE TERMINAL'S TO IMPLY - RUN FROM A REAL SHELL,
            # AN INFERRED `isatty` WOULD BLOCK ON A PROMPT NOBODY IS READING.
            interactive=False if jsonRequested else None,
        ).get()
        if not jsonRequested:
            print(f"{code}  {folderPath}")
        sync = _hand_off_sync(a, log, indexDbConn, settings)
        if jsonRequested:
            _mutating_json(
                "add_id", details, folderPath, indexDbConn, settings, sync,
            )

    elif a["fd"]:
        if a.get("jsonFlag"):
            _fd_json(a, log, indexDbConn, settings)
        else:
            if a.get("archivedFlag"):
                raise ValueError(
                    "`--archived` is only meaningful with `--json` - run `aardvark fd --json --archived`"
                )
            _search(a, log, indexDbConn)

    elif a["archive"]:
        if not a["yesFlag"] and sys.stdin.isatty():
            answer = input(f"archive '{a['ref']}' and free its number? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("nothing archived")
                return
        code, archivedPath, warnings = archive(
            log=log, dbConn=indexDbConn, ref=a["ref"], settings=settings,
        ).get()
        print(f"archived {code}  {archivedPath}")
        for warning in warnings:
            print(f"note: {warning}", file=sys.stderr)
        # `archive` MOVES FOLDERS THE MIRRORS ADOPT BY NAME, SO IT NEEDS THE
        # SAME WHOLE-TREE REPAIR AS THE OTHER SIX MUTATING COMMANDS. ITS OWN
        # PER-MIRROR ARCHIVING ABOVE HANDLES THE MOVED ENTITY; THIS RECONCILES
        # THE INDEX DOCUMENTS THAT LISTED IT.
        _hand_off_sync(a, log, indexDbConn, settings)

    elif a["open"]:
        if a.get("jsonFlag"):
            _open_json(a, indexDbConn, settings)
            return

        targetPath = a["path"]
        if not targetPath and sys.stdin.isatty():
            targetPath = browse(log=log, dbConn=indexDbConn, settings=settings).get()
            if not targetPath:
                print("nothing selected")
                return
        label, openedUrls = open_craft(
            log=log, dbConn=indexDbConn, path=targetPath, settings=settings,
        ).get()
        for serviceLabel, url in openedUrls:
            print(f"opened {label}  {serviceLabel}  {url}")


def _json_requested(arguments):
    """
    *decide whether this run has to keep stdout free for the contract*

    Asked **before** docopt has run, so it reads the raw arguments: either
    the dict a caller passed in, or the command line itself.

    **Key Arguments:**

    - ``arguments`` -- the docopt arguments dict, or `None` when reading `sys.argv`

    **Return:**

    - ``jsonRequested`` -- `True` if `--json` was asked for
    """
    if arguments is None:
        return "--json" in sys.argv[1:]
    return bool(arguments.get("--json"))


def _print_json(payload):
    """
    *write one contract object to stdout*

    The only glue between the pure renderers in `json_output` and the
    terminal, which is why it is the one place excluded from coverage.

    **Key Arguments:**

    - ``payload`` -- the JSON-ready dict to print
    """
    print(json.dumps(payload, ensure_ascii=False))  # pragma: no cover


def _codes_under_ref(ref, records):
    """
    *narrow a whole-index dump to one Johnny Decimal subtree, without a second query*

    A domain letter takes its whole domain; an area takes its own decade;
    a category takes itself and its IDs; an ID takes itself. The dump is
    already in index order, so filtering it preserves that order.

    **Key Arguments:**

    - ``ref`` -- an upper-cased domain letter, area, category or ID reference
    - ``records`` -- the whole index's entity records

    **Return:**

    - ``records`` -- the subtree's records, in index order
    """
    if ref in codes.LETTER_DOMAIN:
        domain = codes.LETTER_DOMAIN[ref]
        return [record for record in records if record["domain"] == domain]

    if codes.is_id_ref(ref):
        return [record for record in records if record["code"] == ref]

    if codes.parse_area_ref_is_area(ref):
        domain, decadeStart = codes.split_area_ref(ref)
        # AN AREA OWNS THE CATEGORIES WHOSE NUMBER FALLS IN ITS DECADE, AND
        # THEIR IDS. THE CODE STRING CARRIES ENOUGH TO SAY SO WITHOUT
        # RE-READING THE INDEX.
        return [
            record for record in records
            if record["domain"] == domain
            and _decade_of(record) == decadeStart
        ]

    domain, acNumber = codes.split_category_ref(ref)
    categoryCode = codes.format_category_code(domain, acNumber)
    return [
        record for record in records
        if record["code"] == categoryCode or record["code"].startswith(f"{categoryCode}.")
    ]


def _decade_of(record):
    """
    *the decade an entity's Johnny Decimal code belongs to*

    **Key Arguments:**

    - ``record`` -- one entity record

    **Return:**

    - ``decadeStart`` -- the decade-start number, e.g. `10` for `A11.10`
    """
    number = int(record["code"][1:3])
    return number - (number % 10)


def _fd_json(a, log, indexDbConn, settings):
    """
    *print the index, a subtree, or a keyword search, as the JSON contract*

    One bulk read serves every shape: the whole index, a Johnny Decimal
    subtree and a keyword search alike, because the per-entity mirror
    lookups `open` uses would otherwise cost four queries per entity.

    **Key Arguments:**

    - ``a`` -- the friendly-named docopt arguments dict
    - ``log`` -- logger
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    """
    records = json_output.entity_records(db.entities_with_links(indexDbConn))
    terms = a["term"] or []

    if len(terms) == 1:
        ref = terms[0].upper()
        try:
            if codes.is_jd_ref(ref) or codes.is_id_ref(ref) or ref in codes.LETTER_DOMAIN:
                records = _codes_under_ref(ref, records)
                terms = []
        except (ValueError, KeyError):
            # NOT A RESOLVABLE REF AFTER ALL - FALL THROUGH TO KEYWORD SEARCH,
            # EXACTLY AS THE HUMAN-READABLE PATH DOES.
            pass

    if terms:
        # KEYWORD MATCHES KEEP `bm25` RANK ORDER RATHER THAN INDEX ORDER.
        byCode = {(record["type"], record["code"]): record for record in records}
        records = [
            byCode[(row["entity_type"], row["code"])]
            for row in search(log=log, dbConn=indexDbConn, terms=terms).get()
            if (row["entity_type"], row["code"]) in byCode
        ]

    archived = None
    if a.get("archivedFlag"):
        archived = [
            json_output.archived_record(row)
            for row in db.list_archived_entities(indexDbConn)
        ]

    system = json_output.system_block(settings, __version__)
    _print_json(json_output.read_envelope(system, records, archived=archived))


def _open_json(a, indexDbConn, settings):
    """
    *resolve a path to its entity record, opening nothing*

    `--json` implies non-interactivity, so there is no picker fallback
    here, and an entity synced to nothing is not an error - the record
    simply carries `null` for every mirror it has not reached yet.

    **Key Arguments:**

    - ``a`` -- the friendly-named docopt arguments dict
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    """
    rootPath = (settings.get("system") or {}).get("root_path")
    targetPath = a["path"] or os.getcwd()
    entityType, entityKey, _folderPath, label = locate.entity_for_path(
        indexDbConn, targetPath, rootPath=rootPath,
    )

    # ONE ROW, NOT THE WHOLE INDEX: THE BULK READ IS THERE TO MAKE A WHOLE
    # DUMP CHEAP, NOT TO MAKE A SINGLE LOOKUP EXPENSIVE.
    matches = json_output.entity_records(
        db.entities_with_links(indexDbConn, entityType=entityType, rowKey=entityKey)
    )
    if not matches:
        # A `system_folder` OR THE SPACE ROOT ITSELF: REAL, MIRRORED, AND
        # DELIBERATELY ABSENT FROM THE CONTRACT, WHICH DESCRIBES AREAS,
        # CATEGORIES AND IDS ONLY.
        raise ValueError(
            f"'{label}' is a system folder, so it is not found in the index - "
            f"`--json` covers areas, categories and IDs"
        )

    _print_json(json_output.result_envelope("open", entity=matches[0], label=label))


def _mutating_json(action, details, folderPath, indexDbConn, settings, sync):
    """
    *print the uniform mutating result for a command that has just written something*

    One shape across every mutating command, so the workflow renders
    them all the same way. `corrections` and `suggestions` come straight
    off the worker and stay strictly apart: the first is what was
    applied, the second what was offered and not accepted.

    The entity is resolved from the folder the command just created,
    which is the same single-row read `open --json` does - the record it
    returns is what the success surface is built from.

    **Key Arguments:**

    - ``action`` -- the command's action token, e.g. `add_id`
    - ``details`` -- the `{"corrections", "suggestions"}` dict the worker returned
    - ``folderPath`` -- the folder the command created
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``settings`` -- the aardvark settings dict
    - ``sync`` -- `_hand_off_sync`'s label for what became of the mirroring
    """
    rootPath = (settings.get("system") or {}).get("root_path")
    entityType, entityKey, _folderPath, _label = locate.entity_for_path(
        indexDbConn, folderPath, rootPath=rootPath,
    )
    records = json_output.entity_records(
        db.entities_with_links(indexDbConn, entityType=entityType, rowKey=entityKey)
    )
    if not records:
        # THE ROW WAS JUST WRITTEN ON THIS CONNECTION, SO THIS CANNOT HAPPEN
        # TODAY. IT IS CHECKED ANYWAY BECAUSE EVERYTHING ELSE ON THIS PATH IS
        # WRITTEN SO THAT ALFRED NEVER SEES A TRACEBACK.
        raise ValueError(f"'{folderPath}' was created but is not in the index")

    _print_json(json_output.result_envelope(
        action,
        entity=records[0],
        corrections=details["corrections"],
        suggestions=details["suggestions"],
        sync=sync,
    ))


def _id_row_for_ref(indexDbConn, ref):
    """
    *the `ids` row a Johnny Decimal ID reference points at, or None if it isn't one*

    An ID reference carries a second period, before its item number
    (`A11.10`); an area or category reference never does.

    **Key Arguments:**

    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    - ``ref`` -- the reference to test, already upper-cased

    **Return:**

    - ``row`` -- the `ids` row, or `None` if `ref` is not an ID reference or matches nothing
    """
    if not codes.is_id_ref(ref):
        return None
    domain, acNumber, itemNumber = codes.split_id_ref(ref)
    return db.get_id(indexDbConn, domain, acNumber, itemNumber)


def _search(a, log, indexDbConn):
    """
    *print the index as a tree, a Johnny Decimal subtree, or keyword search results*

    With no term at all the whole index is rendered as a tree. A single
    term that looks like a Johnny Decimal reference **and resolves** is
    treated as one: a domain letter, area or category prints its subtree,
    and an ID prints its path line. Anything else - including a ref-shaped
    term that matches nothing - falls through to the existing keyword
    search, so `fd A` can still find the word "A" if that is genuinely
    what the user meant.

    **Key Arguments:**

    - ``a`` -- the friendly-named docopt arguments dict
    - ``log`` -- logger
    - ``indexDbConn`` -- an open SQLite connection to the active system's index
    """
    terms = a["term"] or []

    if not terms:
        for line in tree(log=log, dbConn=indexDbConn).get():
            print(line)
        return

    if len(terms) == 1:
        ref = terms[0]
        try:
            if codes.is_jd_ref(ref) or codes.is_id_ref(ref) or ref.upper() in codes.LETTER_DOMAIN:
                normalised = ref.upper()
                idRow = _id_row_for_ref(indexDbConn, normalised)
                if idRow is not None:
                    print(f"{labels.id_label(idRow['domain'], idRow)}  {idRow['folder_path']}")
                    return
                for line in tree(log=log, dbConn=indexDbConn, ref=normalised).get():
                    print(line)
                return
        except (ValueError, KeyError):
            # NOT A RESOLVABLE REF AFTER ALL - FALL THROUGH TO KEYWORD SEARCH.
            pass

    results = search(log=log, dbConn=indexDbConn, terms=terms).get()
    if not results:
        print("no matches found")
    for row in results:
        print(format_result(row))


if __name__ == "__main__":
    main()
