#!/usr/bin/env python
# encoding: utf-8
"""
*SQLite schema, connection and row-mapping helpers for the aardvark index*

Author
: David Young
"""

import sqlite3

_BASE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_folders (
    folder_key   TEXT PRIMARY KEY,
    folder_name  TEXT NOT NULL,
    folder_path  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS areas (
    area_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    domain        TEXT NOT NULL CHECK (domain IN ('areas','resources','projects')),
    decade_start  INTEGER NOT NULL,
    decade_end    INTEGER NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    emoji         TEXT NOT NULL DEFAULT '📁',
    folder_name   TEXT NOT NULL,
    folder_path   TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    UNIQUE (domain, decade_start)
);

CREATE TABLE IF NOT EXISTS categories (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id       INTEGER NOT NULL REFERENCES areas(area_id) ON DELETE CASCADE,
    domain        TEXT NOT NULL CHECK (domain IN ('areas','resources','projects')),
    ac_number     INTEGER NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    emoji         TEXT NOT NULL DEFAULT '📁',
    folder_name   TEXT NOT NULL,
    folder_path   TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    UNIQUE (domain, ac_number)
);

CREATE TABLE IF NOT EXISTS ids (
    id_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id   INTEGER NOT NULL REFERENCES categories(category_id) ON DELETE CASCADE,
    domain        TEXT NOT NULL CHECK (domain IN ('areas','resources','projects')),
    ac_number     INTEGER NOT NULL,
    item_number   INTEGER NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    folder_name   TEXT NOT NULL,
    folder_path   TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    UNIQUE (domain, ac_number, item_number)
);

CREATE TABLE IF NOT EXISTS craft_links (
    entity_type        TEXT NOT NULL,
    entity_key         TEXT NOT NULL,
    craft_folder_id     TEXT,
    craft_document_id   TEXT,
    craft_block_id       TEXT,
    craft_url           TEXT,
    links_markdown       TEXT,
    synced_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    PRIMARY KEY (entity_type, entity_key)
);

CREATE TABLE IF NOT EXISTS dropbox_links (
    folder_path  TEXT PRIMARY KEY,
    dropbox_url  TEXT NOT NULL,
    synced_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS todoist_links (
    entity_type          TEXT NOT NULL,
    entity_key           TEXT NOT NULL,
    todoist_project_id   TEXT,
    todoist_url          TEXT,
    description          TEXT,
    synced_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    PRIMARY KEY (entity_type, entity_key)
);

CREATE TABLE IF NOT EXISTS gdrive_links (
    entity_type      TEXT NOT NULL,
    entity_key       TEXT NOT NULL,
    gdrive_folder_id TEXT,
    gdrive_url       TEXT,
    synced_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now')),
    PRIMARY KEY (entity_type, entity_key)
);

-- AN ARCHIVED AREA/CATEGORY/ID LEAVES `areas`/`categories`/`ids` ENTIRELY AND
-- LANDS HERE. THAT IS WHAT FREES ITS JOHNNY DECIMAL NUMBER FOR REUSE - THE
-- LIVE TABLES CARRY `UNIQUE (domain, ac_number[, item_number])`, SO THE ROW
-- CANNOT BOTH STAY PUT AND SURRENDER ITS NUMBER. KEEPING ARCHIVED ROWS OUT
-- OF THE LIVE TABLES ALSO MEANS EVERY EXISTING WALK (`list_areas`,
-- `list_categories`, `list_ids`, AND THE THREE SYNC ENGINES BUILT ON THEM)
-- SKIPS THEM WITHOUT NEEDING AN `archived` FILTER ADDED - AND SINCE ALL
-- THREE SYNCS ADOPT-OR-CREATE *BY NAME*, A SINGLE MISSED FILTER WOULD HAVE
-- SILENTLY RECREATED ARCHIVED STRUCTURE ON THE NEXT SYNC.
CREATE TABLE IF NOT EXISTS archived_entities (
    archive_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type   TEXT NOT NULL CHECK (entity_type IN ('area','category','id')),
    entity_key    TEXT NOT NULL,
    domain        TEXT NOT NULL CHECK (domain IN ('areas','resources','projects')),
    code          TEXT NOT NULL,
    decade_start  INTEGER,
    ac_number     INTEGER,
    item_number   INTEGER,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    emoji         TEXT NOT NULL DEFAULT '',
    folder_name   TEXT NOT NULL,
    original_path TEXT NOT NULL,
    archived_path TEXT NOT NULL,
    craft_url     TEXT,
    todoist_url   TEXT,
    gdrive_url    TEXT,
    dropbox_url   TEXT,
    archived_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now'))
);
CREATE INDEX IF NOT EXISTS idx_archived_entities_path ON archived_entities(archived_path);
CREATE INDEX IF NOT EXISTS idx_archived_entities_code ON archived_entities(domain, code);

-- ONE ROW PER MIRROR, RECORDING WHETHER ITS LAST SYNC SUCCEEDED. SYNC NOW
-- RUNS IN A DETACHED PROCESS NOBODY IS WATCHING (SEE `background_sync` AND
-- `docs/adr/0001-...`), SO A FAILURE HAS NO TERMINAL TO REPORT TO AND MUST
-- BE RECORDED INSTEAD. PER-MIRROR RATHER THAN PER-SYSTEM BECAUSE PARTIAL
-- FAILURE IS REAL - THE THREE RUN IN SEQUENCE, SO DRIVE CAN SUCCEED WHILE
-- CRAFT IS RATE-LIMITED. NOT PER-ENTITY: THE CARRIER IS A WHOLE-TREE RUN
-- THAT EITHER COMPLETES OR DOES NOT, SO PER-ENTITY MARKERS WOULD BE FICTION.
CREATE TABLE IF NOT EXISTS sync_drift (
    mirror              TEXT PRIMARY KEY CHECK (mirror IN ('gdrive','todoist','craft')),
    last_success_at     TEXT,
    last_failure_at     TEXT,
    last_failure_reason TEXT,
    last_failure_class  TEXT
);
"""

# `CREATE TRIGGER IF NOT EXISTS` NEVER UPDATES AN EXISTING TRIGGER'S BODY, SO
# AN EXISTING DATABASE WOULD SILENTLY KEEP THE OLD CODE-STRING FORMAT FOREVER
# UNLESS EVERY TRIGGER IS EXPLICITLY DROPPED FIRST ON EACH SCHEMA INIT.
_DROP_SEARCH_TRIGGERS = """
DROP TRIGGER IF EXISTS areas_ai;
DROP TRIGGER IF EXISTS areas_au;
DROP TRIGGER IF EXISTS areas_ad;
DROP TRIGGER IF EXISTS categories_ai;
DROP TRIGGER IF EXISTS categories_au;
DROP TRIGGER IF EXISTS categories_ad;
DROP TRIGGER IF EXISTS ids_ai;
DROP TRIGGER IF EXISTS ids_au;
DROP TRIGGER IF EXISTS ids_ad;
"""

_SEARCH_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS areas_ai AFTER INSERT ON areas BEGIN
    INSERT OR REPLACE INTO search_index(rowid, entity_type, code, title, description, path)
    VALUES (
        100000000000 + NEW.area_id, 'area',
        (CASE NEW.domain WHEN 'areas' THEN 'A' WHEN 'projects' THEN 'P' ELSE 'R' END) ||
            printf('%02d', NEW.decade_start) || '-' || printf('%02d', NEW.decade_start + 9),
        NEW.title, NEW.description, NEW.folder_path
    );
END;

CREATE TRIGGER IF NOT EXISTS areas_au AFTER UPDATE ON areas BEGIN
    INSERT OR REPLACE INTO search_index(rowid, entity_type, code, title, description, path)
    VALUES (
        100000000000 + NEW.area_id, 'area',
        (CASE NEW.domain WHEN 'areas' THEN 'A' WHEN 'projects' THEN 'P' ELSE 'R' END) ||
            printf('%02d', NEW.decade_start) || '-' || printf('%02d', NEW.decade_start + 9),
        NEW.title, NEW.description, NEW.folder_path
    );
END;

CREATE TRIGGER IF NOT EXISTS areas_ad AFTER DELETE ON areas BEGIN
    DELETE FROM search_index WHERE rowid = 100000000000 + OLD.area_id;
END;

CREATE TRIGGER IF NOT EXISTS categories_ai AFTER INSERT ON categories BEGIN
    INSERT OR REPLACE INTO search_index(rowid, entity_type, code, title, description, path)
    VALUES (
        200000000000 + NEW.category_id, 'category',
        (CASE NEW.domain WHEN 'areas' THEN 'A' WHEN 'projects' THEN 'P' ELSE 'R' END) || printf('%02d', NEW.ac_number),
        NEW.title, NEW.description, NEW.folder_path
    );
END;

CREATE TRIGGER IF NOT EXISTS categories_au AFTER UPDATE ON categories BEGIN
    INSERT OR REPLACE INTO search_index(rowid, entity_type, code, title, description, path)
    VALUES (
        200000000000 + NEW.category_id, 'category',
        (CASE NEW.domain WHEN 'areas' THEN 'A' WHEN 'projects' THEN 'P' ELSE 'R' END) || printf('%02d', NEW.ac_number),
        NEW.title, NEW.description, NEW.folder_path
    );
END;

CREATE TRIGGER IF NOT EXISTS categories_ad AFTER DELETE ON categories BEGIN
    DELETE FROM search_index WHERE rowid = 200000000000 + OLD.category_id;
END;

CREATE TRIGGER IF NOT EXISTS ids_ai AFTER INSERT ON ids BEGIN
    INSERT OR REPLACE INTO search_index(rowid, entity_type, code, title, description, path)
    VALUES (
        300000000000 + NEW.id_id, 'id',
        (CASE NEW.domain WHEN 'areas' THEN 'A' WHEN 'projects' THEN 'P' ELSE 'R' END) ||
            printf('%02d', NEW.ac_number) || '.' || printf('%02d', NEW.item_number),
        NEW.title, NEW.description, NEW.folder_path
    );
END;

CREATE TRIGGER IF NOT EXISTS ids_au AFTER UPDATE ON ids BEGIN
    INSERT OR REPLACE INTO search_index(rowid, entity_type, code, title, description, path)
    VALUES (
        300000000000 + NEW.id_id, 'id',
        (CASE NEW.domain WHEN 'areas' THEN 'A' WHEN 'projects' THEN 'P' ELSE 'R' END) ||
            printf('%02d', NEW.ac_number) || '.' || printf('%02d', NEW.item_number),
        NEW.title, NEW.description, NEW.folder_path
    );
END;

CREATE TRIGGER IF NOT EXISTS ids_ad AFTER DELETE ON ids BEGIN
    DELETE FROM search_index WHERE rowid = 300000000000 + OLD.id_id;
END;
"""

_FTS5_SEARCH_INDEX = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    entity_type UNINDEXED,
    code        UNINDEXED,
    title,
    description,
    path        UNINDEXED,
    tokenize = 'porter unicode61'
);
"""

_FALLBACK_SEARCH_INDEX = """
CREATE TABLE IF NOT EXISTS search_index (
    rowid       INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    code        TEXT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    path        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_index_title ON search_index(title);
"""

# BUMP WHEN `_BASE_SCHEMA` CHANGES IN A WAY THAT AN ALREADY-INITIALISED
# DATABASE CAN'T PICK UP VIA THE `IF NOT EXISTS` DDL ALONE (E.G. A WIDENED
# `CHECK` CONSTRAINT), AND ADD THE ONE-OFF REBUILD TO `_migrate_schema`.
_SCHEMA_VERSION = "6"


def _migrate_schema(dbConn):
    """
    *step an already-initialised database up through each versioned migration to the current schema*

    Each step below is gated on the `meta['schema_version']` value stored
    *before* this call, so an already-current database runs nothing and a
    database several versions behind runs every step it hasn't seen yet,
    in order. A brand-new database (no `areas` table yet, so already
    current against `_BASE_SCHEMA`) just stamps the version and skips
    every step.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    """
    priorVersion = get_meta(dbConn, "schema_version")
    if priorVersion == _SCHEMA_VERSION:
        return

    areasTableExists = dbConn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'areas'"
    ).fetchone()
    if areasTableExists is None:
        set_meta(dbConn, "schema_version", _SCHEMA_VERSION)
        return

    # WALK THE LADDER FROM WHEREVER THIS DATABASE IS UP TO CURRENT. A
    # DATABASE WITH NO RECORDED VERSION PREDATES THE `meta` STAMP AND SO
    # NEEDS EVERY STEP.
    startedAt = (
        _MIGRATION_VERSIONS.index(priorVersion) + 1
        if priorVersion in _MIGRATION_VERSIONS
        else 0
    )
    for _version, migration in _MIGRATIONS[startedAt:]:
        migration(dbConn)

    dbConn.commit()
    set_meta(dbConn, "schema_version", _SCHEMA_VERSION)


def _migrate_to_v3(dbConn):
    """
    *rebuild `areas`/`categories`/`ids` onto the widened domain `CHECK` constraint, drop the legacy flat `projects` table, and add the `craft_links.links_markdown` column*

    SQLite cannot alter a `CHECK` constraint in place, so an
    already-initialised database - whose `areas`/`categories`/`ids` tables
    are still `CHECK`-constrained to `('areas','resources')` from before
    Projects became a Johnny Decimal domain - is rebuilt: the three tables
    are renamed aside, recreated via `_BASE_SCHEMA` (which now carries the
    widened `('areas','resources','projects')` constraint), their rows
    copied across, then the renamed-aside tables and the legacy `projects`
    table are dropped. `craft_links.links_markdown` (added for the Finder/
    Dropbox link row - see `craft_sync._write_link_row`) is a plain `ALTER
    TABLE ADD COLUMN`, since it isn't `CHECK`-constrained and needs no
    rebuild.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    """
    dbConn.execute("PRAGMA foreign_keys = OFF")
    dbConn.execute("ALTER TABLE areas RENAME TO areas_old")
    dbConn.execute("ALTER TABLE categories RENAME TO categories_old")
    dbConn.execute("ALTER TABLE ids RENAME TO ids_old")
    dbConn.executescript(_BASE_SCHEMA)
    dbConn.execute("INSERT INTO areas SELECT * FROM areas_old")
    dbConn.execute("INSERT INTO categories SELECT * FROM categories_old")
    dbConn.execute("INSERT INTO ids SELECT * FROM ids_old")
    dbConn.execute("DROP TABLE areas_old")
    dbConn.execute("DROP TABLE categories_old")
    dbConn.execute("DROP TABLE ids_old")
    dbConn.execute("DROP TABLE IF EXISTS projects")
    dbConn.execute("PRAGMA foreign_keys = ON")

    craftLinksColumns = {row["name"] for row in dbConn.execute("PRAGMA table_info(craft_links)")}
    if craftLinksColumns and "links_markdown" not in craftLinksColumns:
        dbConn.execute("ALTER TABLE craft_links ADD COLUMN links_markdown TEXT")


def _migrate_to_v4(dbConn):
    """
    *clear stale `entity_type = 'id'` craft links, now that an ID mirrors as a folder rather than a document*

    An earlier version's `craft_links` rows of type `id` carry a
    `craft_document_id` and no `craft_folder_id`, pointing at the old
    top-level ID document rather than the new `id` folder / `id:index`
    document pair `craft_sync` now creates. Deleting them here rather than
    trying to migrate them in place means the next `craft_sync` just
    creates the new shape from scratch, exactly as it would for a
    never-synced ID - the old orphaned Craft documents themselves are
    left behind and must be cleaned up by hand in the Craft app, since
    the API cannot delete or convert them.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    """
    dbConn.execute("DELETE FROM craft_links WHERE entity_type = 'id'")


def _migrate_to_v5(dbConn):
    """
    *pick up the `gdrive_links` and `archived_entities` tables*

    Both are additive, and both are declared in `_BASE_SCHEMA` with
    `CREATE TABLE IF NOT EXISTS`, which `initialise_schema` runs on every
    call - so an existing database has already grown them by the time this
    step is reached. Nothing to do here but exist, so the version ladder
    has a rung to step onto and the bump is recorded deliberately rather
    than by omission.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    """
    pass


def _migrate_to_v6(dbConn):
    """
    *pick up the `sync_drift` table*

    Additive, and declared in `_BASE_SCHEMA` with `CREATE TABLE IF NOT
    EXISTS`, which `initialise_schema` runs on every call - so an existing
    database has already grown it by the time this step is reached. Same
    shape as `_migrate_to_v5`: nothing to do but exist, so the ladder has
    a rung and the bump is recorded deliberately rather than by omission.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    """
    pass


# ORDERED LADDER OF ONE-OFF MIGRATIONS. A DATABASE STAMPED WITH VERSION `N`
# RUNS EVERY ENTRY AFTER `N`, IN ORDER. ADD NEW STEPS TO THE END AND BUMP
# `_SCHEMA_VERSION` TO MATCH.
_MIGRATIONS = (
    ("3", _migrate_to_v3),
    ("4", _migrate_to_v4),
    ("5", _migrate_to_v5),
    ("6", _migrate_to_v6),
)
_MIGRATION_VERSIONS = [version for version, _migration in _MIGRATIONS]


def get_connection(pathToDb):
    """
    *open a SQLite connection to the aardvark index, with row access by column name*

    **Key Arguments:**

    - ``pathToDb`` -- path to the `aardvark.db` file

    **Return:**

    - ``dbConn`` -- the open SQLite connection
    """
    dbConn = sqlite3.connect(pathToDb)
    dbConn.row_factory = sqlite3.Row
    dbConn.execute("PRAGMA foreign_keys = ON")
    # WAIT OUT A CONCURRENT WRITE LOCK RATHER THAN CRASHING WITH `SQLITE_BUSY`:
    # TWO `aardvark` COMMANDS, OR A COMMAND AND A SHELL-COMPLETION READER, CAN
    # OVERLAP. THE PYTHON 3.14 STDLIB ALREADY DEFAULTS THIS TO 5 s, BUT AARDVARK
    # DEPENDS ON IT (TICKET 08's CONCURRENCY CONTRACT), SO IT IS SET EXPLICITLY
    # HERE AND ON THE `mode=ro` COMPLETION PATH. WAL IS DELIBERATELY NOT ENABLED.
    dbConn.execute("PRAGMA busy_timeout = 5000")
    return dbConn


def initialise_schema(dbConn):
    """
    *create the aardvark schema if it does not already exist*

    Probes for FTS5 support once, falling back to a plain indexed table
    for `search_index` if the SQLite build lacks the FTS5 module, and
    records the outcome in `meta['fts5_enabled']`. The search triggers are
    dropped and recreated on every call, since `CREATE TRIGGER IF NOT
    EXISTS` would otherwise leave an existing database's older trigger
    bodies in place forever. Runs `_migrate_schema` first so an
    already-initialised database is upgraded onto the current schema
    before `_BASE_SCHEMA`'s `IF NOT EXISTS` DDL runs.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    """
    dbConn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    dbConn.commit()
    _migrate_schema(dbConn)

    dbConn.executescript(_BASE_SCHEMA)

    fts5Enabled = get_meta(dbConn, "fts5_enabled")
    if fts5Enabled is None:
        try:
            dbConn.executescript(_FTS5_SEARCH_INDEX)
            fts5Enabled = "1"
        except sqlite3.OperationalError:
            dbConn.executescript(_FALLBACK_SEARCH_INDEX)
            fts5Enabled = "0"
        set_meta(dbConn, "fts5_enabled", fts5Enabled)
    elif fts5Enabled == "1":
        dbConn.executescript(_FTS5_SEARCH_INDEX)
    else:
        dbConn.executescript(_FALLBACK_SEARCH_INDEX)

    dbConn.executescript(_DROP_SEARCH_TRIGGERS)
    dbConn.executescript(_SEARCH_TRIGGERS)
    dbConn.commit()


def get_meta(dbConn, key):
    """
    *read a value from the `meta` table*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``key`` -- the meta key to read

    **Return:**

    - ``value`` -- the stored value, or `None` if not set
    """
    row = dbConn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(dbConn, key, value):
    """
    *write a value into the `meta` table*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``key`` -- the meta key to write
    - ``value`` -- the value to store
    """
    dbConn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    dbConn.commit()


def fts5_enabled(dbConn):
    """
    *check whether the FTS5 search index is in use for this database*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection

    **Return:**

    - ``enabled`` -- `True` if FTS5 is in use, `False` if the LIKE fallback is
    """
    return get_meta(dbConn, "fts5_enabled") == "1"


def insert_system_folder(dbConn, folderKey, folderName, folderPath):
    """
    *record the exact name/path of a static scaffold folder*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``folderKey`` -- the logical key for this folder, e.g. `"root.areas"`
    - ``folderName`` -- the folder's exact on-disk name (including emoji)
    - ``folderPath`` -- the folder's absolute path
    """
    dbConn.execute(
        "INSERT INTO system_folders(folder_key, folder_name, folder_path) VALUES (?, ?, ?) "
        "ON CONFLICT(folder_key) DO UPDATE SET folder_name = excluded.folder_name, "
        "folder_path = excluded.folder_path",
        (folderKey, folderName, folderPath),
    )
    dbConn.commit()


def get_system_folder(dbConn, folderKey):
    """
    *look up a static scaffold folder's exact name/path*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``folderKey`` -- the logical key for this folder, e.g. `"root.areas"`

    **Return:**

    - ``row`` -- the `system_folders` row, or `None` if not found
    """
    return dbConn.execute(
        "SELECT * FROM system_folders WHERE folder_key = ?", (folderKey,)
    ).fetchone()


def insert_area(dbConn, domain, decadeStart, decadeEnd, title, description, emoji, folderName, folderPath):
    """
    *insert a new Johnny Decimal area row*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas` or `resources`
    - ``decadeStart`` -- the area's decade-start number
    - ``decadeEnd`` -- the area's decade-end number
    - ``title`` -- the area's title
    - ``description`` -- the area's description
    - ``emoji`` -- the emoji appended to the area's folder name
    - ``folderName`` -- the area's exact on-disk folder name
    - ``folderPath`` -- the area's absolute folder path

    **Return:**

    - ``areaId`` -- the new row's primary key
    """
    cursor = dbConn.execute(
        "INSERT INTO areas(domain, decade_start, decade_end, title, description, emoji, folder_name, folder_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (domain, decadeStart, decadeEnd, title, description, emoji, folderName, folderPath),
    )
    dbConn.commit()
    return cursor.lastrowid


def get_area(dbConn, domain, decadeStart):
    """
    *look up a Johnny Decimal area by domain and decade-start number*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas` or `resources`
    - ``decadeStart`` -- the area's decade-start number

    **Return:**

    - ``row`` -- the `areas` row, or `None` if not found
    """
    return dbConn.execute(
        "SELECT * FROM areas WHERE domain = ? AND decade_start = ?", (domain, decadeStart)
    ).fetchone()


def list_areas(dbConn, domain):
    """
    *list all Johnny Decimal areas for a domain, ordered by decade*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas` or `resources`

    **Return:**

    - ``rows`` -- the matching `areas` rows
    """
    return dbConn.execute(
        "SELECT * FROM areas WHERE domain = ? ORDER BY decade_start", (domain,)
    ).fetchall()


def insert_category(dbConn, areaId, domain, acNumber, title, description, emoji, folderName, folderPath):
    """
    *insert a new Johnny Decimal category row*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``areaId`` -- the parent area's primary key
    - ``domain`` -- `areas` or `resources`
    - ``acNumber`` -- the category's 2-digit AC number
    - ``title`` -- the category's title
    - ``description`` -- the category's description
    - ``emoji`` -- the emoji appended to the category's folder name
    - ``folderName`` -- the category's exact on-disk folder name
    - ``folderPath`` -- the category's absolute folder path

    **Return:**

    - ``categoryId`` -- the new row's primary key
    """
    cursor = dbConn.execute(
        "INSERT INTO categories(area_id, domain, ac_number, title, description, emoji, folder_name, folder_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (areaId, domain, acNumber, title, description, emoji, folderName, folderPath),
    )
    dbConn.commit()
    return cursor.lastrowid


def get_category(dbConn, domain, acNumber):
    """
    *look up a Johnny Decimal category by domain and AC number*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas` or `resources`
    - ``acNumber`` -- the category's 2-digit AC number

    **Return:**

    - ``row`` -- the `categories` row, or `None` if not found
    """
    return dbConn.execute(
        "SELECT * FROM categories WHERE domain = ? AND ac_number = ?", (domain, acNumber)
    ).fetchone()


def list_categories(dbConn, domain, areaId=None):
    """
    *list Johnny Decimal categories for a domain, optionally within one area*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas` or `resources`
    - ``areaId`` -- restrict to this area's primary key. Default `None`.

    **Return:**

    - ``rows`` -- the matching `categories` rows
    """
    if areaId is None:
        return dbConn.execute(
            "SELECT * FROM categories WHERE domain = ? ORDER BY ac_number", (domain,)
        ).fetchall()
    return dbConn.execute(
        "SELECT * FROM categories WHERE domain = ? AND area_id = ? ORDER BY ac_number",
        (domain, areaId),
    ).fetchall()


def insert_id(dbConn, categoryId, domain, acNumber, itemNumber, title, description, folderName, folderPath):
    """
    *insert a new Johnny Decimal ID row*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``categoryId`` -- the parent category's primary key
    - ``domain`` -- `areas` or `resources`
    - ``acNumber`` -- the parent category's 2-digit AC number
    - ``itemNumber`` -- the ID's 2-digit item number
    - ``title`` -- the ID's title
    - ``description`` -- the ID's description
    - ``folderName`` -- the ID's exact on-disk folder name (no emoji)
    - ``folderPath`` -- the ID's absolute folder path

    **Return:**

    - ``idId`` -- the new row's primary key
    """
    cursor = dbConn.execute(
        "INSERT INTO ids(category_id, domain, ac_number, item_number, title, description, folder_name, folder_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (categoryId, domain, acNumber, itemNumber, title, description, folderName, folderPath),
    )
    dbConn.commit()
    return cursor.lastrowid


def list_ids(dbConn, domain, categoryId):
    """
    *list Johnny Decimal IDs within a category*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas` or `resources`
    - ``categoryId`` -- the parent category's primary key

    **Return:**

    - ``rows`` -- the matching `ids` rows
    """
    return dbConn.execute(
        "SELECT * FROM ids WHERE domain = ? AND category_id = ? ORDER BY item_number",
        (domain, categoryId),
    ).fetchall()


# EVERY TABLE THAT PERSISTS AN ABSOLUTE `folder_path`, AND SO HAS TO BE
# REWRITTEN WHEN AN ANCESTOR FOLDER IS RENAMED.
_PATH_BEARING_TABLES = ("system_folders", "areas", "categories", "ids")


def rewrite_folder_path_prefix(dbConn, oldPrefix, newPrefix):
    """
    *repoint every descendant row from an old ancestor folder path to a new one*

    Renaming a folder silently invalidates the stored `folder_path` of
    everything nested inside it - categories and IDs under an area, IDs
    under a category, and the whole domain under a section folder - so
    this rewrites all of them in one pass.

    Matching is done with `substr` rather than `LIKE` because aardvark
    folder names are full of underscores (`00_INDEX`), which `LIKE` would
    treat as single-character wildcards.

    Does **not** commit - the caller owns the transaction so the rename and
    the rewrite land together.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``oldPrefix`` -- the ancestor folder's old absolute path
    - ``newPrefix`` -- the ancestor folder's new absolute path

    **Return:**

    - ``rewritten`` -- the total number of descendant rows repointed
    """
    oldParent = oldPrefix.rstrip("/") + "/"
    newParent = newPrefix.rstrip("/") + "/"
    prefixLength = len(oldParent)

    rewritten = 0
    for tableName in _PATH_BEARING_TABLES:
        cursor = dbConn.execute(
            f"UPDATE {tableName} SET folder_path = ? || substr(folder_path, ?) "
            f"WHERE substr(folder_path, 1, ?) = ?",
            (newParent, prefixLength + 1, prefixLength, oldParent),
        )
        rewritten += cursor.rowcount
    return rewritten


def update_area_emoji(dbConn, areaId, emoji, folderName, folderPath):
    """
    *update an area's emoji, folder name and folder path (without committing)*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``areaId`` -- the area's primary key
    - ``emoji`` -- the new emoji
    - ``folderName`` -- the area's new on-disk folder name
    - ``folderPath`` -- the area's new absolute folder path
    """
    dbConn.execute(
        "UPDATE areas SET emoji = ?, folder_name = ?, folder_path = ?, "
        "updated_at = strftime('%Y-%m-%d %H:%M:%S','now') WHERE area_id = ?",
        (emoji, folderName, folderPath, areaId),
    )


def update_category_emoji(dbConn, categoryId, emoji, folderName, folderPath):
    """
    *update a category's emoji, folder name and folder path (without committing)*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``categoryId`` -- the category's primary key
    - ``emoji`` -- the new emoji
    - ``folderName`` -- the category's new on-disk folder name
    - ``folderPath`` -- the category's new absolute folder path
    """
    dbConn.execute(
        "UPDATE categories SET emoji = ?, folder_name = ?, folder_path = ?, "
        "updated_at = strftime('%Y-%m-%d %H:%M:%S','now') WHERE category_id = ?",
        (emoji, folderName, folderPath, categoryId),
    )


def update_id_name(dbConn, idId, folderName, folderPath):
    """
    *update an ID's folder name and folder path (without committing)*

    IDs carry no `emoji` column, unlike areas/categories/projects, so
    there's nothing to pass alongside the name/path.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``idId`` -- the ID's primary key
    - ``folderName`` -- the ID's new on-disk folder name
    - ``folderPath`` -- the ID's new absolute folder path
    """
    dbConn.execute(
        "UPDATE ids SET folder_name = ?, folder_path = ?, "
        "updated_at = strftime('%Y-%m-%d %H:%M:%S','now') WHERE id_id = ?",
        (folderName, folderPath, idId),
    )


def update_system_folder(dbConn, folderKey, folderName, folderPath):
    """
    *update a static system folder's name and path (without committing)*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``folderKey`` -- the logical folder key, e.g. `"root.areas"`
    - ``folderName`` -- the folder's new on-disk name
    - ``folderPath`` -- the folder's new absolute path
    """
    dbConn.execute(
        "UPDATE system_folders SET folder_name = ?, folder_path = ? WHERE folder_key = ?",
        (folderName, folderPath, folderKey),
    )


def list_system_folders(dbConn):
    """
    *list every recorded static system folder*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection

    **Return:**

    - ``rows`` -- the `system_folders` rows
    """
    return dbConn.execute("SELECT * FROM system_folders ORDER BY folder_key").fetchall()


def upsert_craft_link(
    dbConn, entityType, entityKey, craftFolderId=None, craftDocumentId=None, craftBlockId=None, craftUrl=None,
    linksMarkdown=None, clearBlockId=False, clearLinksMarkdown=False,
):
    """
    *record or refresh an entity's linked Craft folder/document/block*

    Fields left as `None` keep whatever was already stored, rather than
    being wiped - an index document's `craftBlockId` is only known after a
    later `add_block` call, so it's set in a second upsert that must not
    clobber the `craftDocumentId` written by the first. `craftBlockId` and
    `linksMarkdown` track the Finder/Dropbox link row `craft_sync` writes
    into each entity's document - see `craft_sync._write_link_row`.
    `clearBlockId` bypasses the usual keep-if-`None` behaviour to actually
    null out `craft_block_id`, for the one case that needs it: the row's
    old block was deleted (e.g. a `.00_index` content rewrite) and no
    replacement has been inserted yet. `clearLinksMarkdown` does the same
    for `links_markdown`, for when every link source has become
    unavailable and the row can no longer be written at all.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- `'system_folder'`, `'area'`, `'category'` or `'id'`
    - ``entityKey`` -- the entity's key: a `system_folders.folder_key`, or an
      `area_id`/`category_id`/`id_id`/`project_id` cast to text
    - ``craftFolderId`` -- the linked Craft folder's id, if any. Default `None`.
    - ``craftDocumentId`` -- the linked Craft document's id, if any. Default `None`.
    - ``craftBlockId`` -- the linked Craft link-row block's id, if any. Default `None`.
    - ``craftUrl`` -- the linked Craft folder/document's shareable URL, if any. Default `None`.
    - ``linksMarkdown`` -- the link row's last-written markdown, if any. Default `None`.
    - ``clearBlockId`` -- if `True`, null out `craft_block_id` regardless of the `craftBlockId` argument. Default `False`.
    - ``clearLinksMarkdown`` -- if `True`, null out `links_markdown` regardless of the `linksMarkdown` argument. Default `False`.
    """
    # `excluded.craft_block_id` ALREADY CARRIES `blockIdValue` VIA THE INSERT
    # ROW BELOW - NO SEPARATE BINDING IS NEEDED FOR THE UPDATE CLAUSE.
    blockIdValue = None if clearBlockId else craftBlockId
    blockIdSql = "excluded.craft_block_id" if clearBlockId else "COALESCE(excluded.craft_block_id, craft_links.craft_block_id)"
    linksMarkdownValue = None if clearLinksMarkdown else linksMarkdown
    linksMarkdownSql = (
        "excluded.links_markdown" if clearLinksMarkdown
        else "COALESCE(excluded.links_markdown, craft_links.links_markdown)"
    )

    dbConn.execute(
        "INSERT INTO craft_links(entity_type, entity_key, craft_folder_id, craft_document_id, craft_block_id, craft_url, links_markdown) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(entity_type, entity_key) DO UPDATE SET "
        "craft_folder_id = COALESCE(excluded.craft_folder_id, craft_links.craft_folder_id), "
        "craft_document_id = COALESCE(excluded.craft_document_id, craft_links.craft_document_id), "
        f"craft_block_id = {blockIdSql}, "
        "craft_url = COALESCE(excluded.craft_url, craft_links.craft_url), "
        f"links_markdown = {linksMarkdownSql}, "
        "synced_at = strftime('%Y-%m-%d %H:%M:%S','now')",
        (entityType, entityKey, craftFolderId, craftDocumentId, blockIdValue, craftUrl, linksMarkdownValue),
    )
    dbConn.commit()


def get_craft_link(dbConn, entityType, entityKey):
    """
    *look up an entity's linked Craft folder/document, if any*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- `'system_folder'`, `'area'`, `'category'` or `'id'`
    - ``entityKey`` -- the entity's key, as passed to `upsert_craft_link`

    **Return:**

    - ``row`` -- the `craft_links` row, or `None` if not yet synced
    """
    return dbConn.execute(
        "SELECT * FROM craft_links WHERE entity_type = ? AND entity_key = ?", (entityType, entityKey)
    ).fetchone()


def upsert_todoist_link(dbConn, entityType, entityKey, todoistProjectId=None, todoistUrl=None, description=None):
    """
    *record or refresh an entity's linked Todoist project*

    Fields left as `None` keep whatever was already stored, rather than
    being wiped, matching `upsert_craft_link`'s behaviour. `description`
    tracks the last-written Craft/Finder/Dropbox link row set on the
    Todoist project - see `todoist_sync.todoist_sync`.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- `'area'` or `'category'` (under `03 AREAS`), or `'id'` (under `02 PROJECTS`)
    - ``entityKey`` -- the entity's key: an `area_id`/`category_id`/`id_id` cast to text
    - ``todoistProjectId`` -- the linked Todoist project's id, if any. Default `None`.
    - ``todoistUrl`` -- the linked Todoist project's shareable URL, if any. Default `None`.
    - ``description`` -- the project's last-written description, if any. Default `None`.
    """
    dbConn.execute(
        "INSERT INTO todoist_links(entity_type, entity_key, todoist_project_id, todoist_url, description) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(entity_type, entity_key) DO UPDATE SET "
        "todoist_project_id = COALESCE(excluded.todoist_project_id, todoist_links.todoist_project_id), "
        "todoist_url = COALESCE(excluded.todoist_url, todoist_links.todoist_url), "
        "description = COALESCE(excluded.description, todoist_links.description), "
        "synced_at = strftime('%Y-%m-%d %H:%M:%S','now')",
        (entityType, entityKey, todoistProjectId, todoistUrl, description),
    )
    dbConn.commit()


def get_todoist_link(dbConn, entityType, entityKey):
    """
    *look up an entity's linked Todoist project, if any*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- `'area'`, `'category'` or `'id'`
    - ``entityKey`` -- the entity's key, as passed to `upsert_todoist_link`

    **Return:**

    - ``row`` -- the `todoist_links` row, or `None` if not yet synced
    """
    return dbConn.execute(
        "SELECT * FROM todoist_links WHERE entity_type = ? AND entity_key = ?", (entityType, entityKey)
    ).fetchone()


# THE `(entityType, folderPathColumn, keyColumn)` EVERY `locate.entity_for_path`
# CANDIDATE TABLE IS QUERIED WITH - KEYS MUST MATCH THE `entityType`/`entityKey`
# SHAPE `craft_sync.py` WRITES INTO `craft_links` FOR THAT TABLE.
_LOCATABLE_TABLES = (
    ("id", "ids", "id_id"),
    ("category", "categories", "category_id"),
    ("area", "areas", "area_id"),
    ("system_folder", "system_folders", "folder_key"),
)


def entity_rows_for_path_prefix(dbConn):
    """
    *fetch every `(entityType, entityKey, folderPath)` candidate for a path-prefix match*

    One flat list across `ids`, `categories`, `areas` and `system_folders`,
    for `locate.entity_for_path` to compare against a normalised input path
    and pick the longest matching prefix. Read as one pass per call rather
    than four separate queries per lookup, since `entity_for_path` needs
    the whole set anyway to find the deepest match.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection

    **Return:**

    - ``rows`` -- a list of `(entityType, entityKey, folderPath)` tuples
    """
    rows = []
    for entityType, tableName, keyColumn in _LOCATABLE_TABLES:
        for row in dbConn.execute(f"SELECT {keyColumn} AS key, folder_path FROM {tableName}"):
            rows.append((entityType, str(row["key"]), row["folder_path"]))
    return rows


_ENTITIES_WITH_LINKS_SQL = """
WITH entities AS (
    SELECT
        'area' AS entity_type, CAST(area_id AS TEXT) AS row_key,
        domain, title, description, emoji, folder_path,
        decade_start, decade_end, NULL AS ac_number, NULL AS item_number,
        decade_start AS group_number, 0 AS type_rank
    FROM areas
    UNION ALL
    SELECT
        'category', CAST(category_id AS TEXT),
        domain, title, description, emoji, folder_path,
        NULL, NULL, ac_number, NULL,
        ac_number, 1
    FROM categories
    UNION ALL
    SELECT
        'id', CAST(id_id AS TEXT),
        domain, title, description, '' AS emoji, folder_path,
        NULL, NULL, ac_number, item_number,
        ac_number, 2
    FROM ids
)
SELECT
    entities.entity_type, entities.row_key, entities.domain,
    entities.title, entities.description, entities.emoji,
    entities.folder_path, entities.decade_start, entities.decade_end,
    entities.ac_number, entities.item_number,
    craft_links.craft_url, todoist_links.todoist_url,
    gdrive_links.gdrive_url, dropbox_links.dropbox_url
FROM entities
LEFT JOIN craft_links
    ON craft_links.entity_type = entities.entity_type
    AND craft_links.entity_key = entities.row_key
LEFT JOIN todoist_links
    ON todoist_links.entity_type = entities.entity_type
    AND todoist_links.entity_key = entities.row_key
LEFT JOIN gdrive_links
    ON gdrive_links.entity_type = entities.entity_type
    AND gdrive_links.entity_key = entities.row_key
LEFT JOIN dropbox_links
    ON dropbox_links.folder_path = entities.folder_path
WHERE (:entityType IS NULL OR entities.entity_type = :entityType)
    AND (:rowKey IS NULL OR entities.row_key = :rowKey)
ORDER BY
    CASE entities.domain
        WHEN 'areas' THEN 0
        WHEN 'resources' THEN 1
        WHEN 'projects' THEN 2
    END,
    entities.group_number,
    entities.type_rank,
    entities.item_number
"""


def entities_with_links(dbConn: sqlite3.Connection, entityType=None, rowKey=None) -> list[sqlite3.Row]:
    """
    *fetch live entities and their mirror URLs in index order with one read-only query*

    Unfiltered, this is the whole-index dump the Alfred surface ships. The
    optional filter narrows it to a single entity, so a caller wanting one
    record does not pay for a four-way join across the whole index.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- restrict to `area`, `category` or `id`. Default `None`, meaning all three.
    - ``rowKey`` -- restrict to one row's stringified primary key. Default `None`, meaning all rows.

    **Return:**

    - ``rows`` -- the live area, category and ID rows with joined mirror URLs

    **Usage:**

    ```python
    from aardvark_jd import db
    rows = db.entities_with_links(dbConn)
    ```
    """
    return dbConn.execute(
        _ENTITIES_WITH_LINKS_SQL,
        {"entityType": entityType, "rowKey": None if rowKey is None else str(rowKey)},
    ).fetchall()


def get_dropbox_link(dbConn, folderPath):
    """
    *look up a folder's cached Dropbox share link, if any*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``folderPath`` -- the folder's absolute path, as passed to `upsert_dropbox_link`

    **Return:**

    - ``row`` -- the `dropbox_links` row, or `None` if not yet minted
    """
    return dbConn.execute(
        "SELECT * FROM dropbox_links WHERE folder_path = ?", (folderPath,)
    ).fetchone()


def upsert_dropbox_link(dbConn, folderPath, dropboxUrl):
    """
    *record or refresh a folder's cached Dropbox share link*

    Sharing a folder that already has a link just returns the existing
    one (see `DropboxClient.shared_link`), so this is safe to call every
    sync without minting duplicates.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``folderPath`` -- the folder's absolute path
    - ``dropboxUrl`` -- the folder's Dropbox share URL
    """
    dbConn.execute(
        "INSERT INTO dropbox_links(folder_path, dropbox_url) VALUES (?, ?) "
        "ON CONFLICT(folder_path) DO UPDATE SET dropbox_url = excluded.dropbox_url, "
        "synced_at = strftime('%Y-%m-%d %H:%M:%S','now')",
        (folderPath, dropboxUrl),
    )
    dbConn.commit()


def get_id(dbConn, domain, acNumber, itemNumber):
    """
    *look up a single ID row by its Johnny Decimal numbers*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas`, `resources` or `projects`
    - ``acNumber`` -- the containing category's AC number
    - ``itemNumber`` -- the ID's item number

    **Return:**

    - ``row`` -- the `ids` row, or `None` if there is no such ID

    **Usage:**

    ```python
    from aardvark_jd import db
    row = db.get_id(dbConn, "areas", 11, 10)
    ```
    """
    return dbConn.execute(
        "SELECT * FROM ids WHERE domain = ? AND ac_number = ? AND item_number = ?",
        (domain, acNumber, itemNumber),
    ).fetchone()


def get_gdrive_link(dbConn, entityType, entityKey):
    """
    *look up an entity's mirrored Google Drive folder*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- the entity's type, e.g. `"area"`
    - ``entityKey`` -- the entity's key, unique within its type

    **Return:**

    - ``row`` -- the `gdrive_links` row, or `None` if the entity has never been mirrored
    """
    return dbConn.execute(
        "SELECT * FROM gdrive_links WHERE entity_type = ? AND entity_key = ?",
        (entityType, entityKey),
    ).fetchone()


def upsert_gdrive_link(dbConn, entityType, entityKey, gdriveFolderId=None, gdriveUrl=None):
    """
    *record (or refresh) an entity's mirrored Google Drive folder*

    A `None` argument leaves any already-stored value alone, matching
    `upsert_craft_link`'s COALESCE behaviour.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- the entity's type, e.g. `"area"`
    - ``entityKey`` -- the entity's key, unique within its type
    - ``gdriveFolderId`` -- the Drive folder id. Default *None*.
    - ``gdriveUrl`` -- the Drive folder's web URL. Default *None*.
    """
    dbConn.execute(
        """
        INSERT INTO gdrive_links (entity_type, entity_key, gdrive_folder_id, gdrive_url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (entity_type, entity_key) DO UPDATE SET
            gdrive_folder_id = COALESCE(excluded.gdrive_folder_id, gdrive_links.gdrive_folder_id),
            gdrive_url       = COALESCE(excluded.gdrive_url, gdrive_links.gdrive_url),
            synced_at        = strftime('%Y-%m-%d %H:%M:%S','now')
        """,
        (entityType, entityKey, gdriveFolderId, gdriveUrl),
    )
    dbConn.commit()


def insert_archived_entity(
    dbConn, entityType, entityKey, domain, code, title, folderName, originalPath, archivedPath,
    decadeStart=None, acNumber=None, itemNumber=None, description="", emoji="",
    craftUrl=None, todoistUrl=None, gdriveUrl=None, dropboxUrl=None,
):
    """
    *record an area, category or ID as archived, preserving everything needed to find it again*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- `"area"`, `"category"` or `"id"`
    - ``entityKey`` -- the original `area_id`/`category_id`/`id_id`, as text
    - ``domain`` -- `areas`, `resources` or `projects`
    - ``code`` -- the entity's Johnny Decimal code at the time of archiving, e.g. `"A11.10"`
    - ``title`` -- the entity's title
    - ``folderName`` -- the entity's on-disk folder name before the move
    - ``originalPath`` -- where the folder lived before archiving
    - ``archivedPath`` -- where the folder lives now
    - ``decadeStart`` -- the area's decade start, for an area. Default *None*.
    - ``acNumber`` -- the AC number, for a category or ID. Default *None*.
    - ``itemNumber`` -- the item number, for an ID. Default *None*.
    - ``description`` -- the entity's description. Default *""*.
    - ``emoji`` -- the entity's emoji. Default *""*.
    - ``craftUrl`` -- its last known Craft URL. Default *None*.
    - ``todoistUrl`` -- its last known Todoist URL. Default *None*.
    - ``gdriveUrl`` -- its last known Google Drive URL. Default *None*.
    - ``dropboxUrl`` -- its last known Dropbox URL. Default *None*.

    **Return:**

    - ``archiveId`` -- the new `archived_entities` row's id
    """
    cursor = dbConn.execute(
        """
        INSERT INTO archived_entities (
            entity_type, entity_key, domain, code, decade_start, ac_number, item_number,
            title, description, emoji, folder_name, original_path, archived_path,
            craft_url, todoist_url, gdrive_url, dropbox_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entityType, str(entityKey), domain, code, decadeStart, acNumber, itemNumber,
            title, description or "", emoji or "", folderName, originalPath, archivedPath,
            craftUrl, todoistUrl, gdriveUrl, dropboxUrl,
        ),
    )
    return cursor.lastrowid


def list_archived_entities(dbConn, domain=None):
    """
    *every archived entity, most recently archived first*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- restrict to one domain. Default *None*, meaning all three.

    **Return:**

    - ``rows`` -- the matching `archived_entities` rows
    """
    if domain:
        return dbConn.execute(
            "SELECT * FROM archived_entities WHERE domain = ? ORDER BY archived_at DESC, archive_id DESC",
            (domain,),
        ).fetchall()
    return dbConn.execute(
        "SELECT * FROM archived_entities ORDER BY archived_at DESC, archive_id DESC"
    ).fetchall()


def get_archived_entity_by_path(dbConn, archivedPath):
    """
    *the `archived_entities` row for a folder's datestamped archive path*

    `archive` datestamps every archived folder name, so the path stays
    unique even after a Johnny Decimal number is reused and the new entity
    archived into the same folder later. Used by the `--json` contract to
    describe what `archive` just did.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``archivedPath`` -- the folder's absolute path after archiving

    **Return:**

    - ``row`` -- the `archived_entities` row, or `None` if there is no such path
    """
    return dbConn.execute(
        "SELECT * FROM archived_entities WHERE archived_path = ? ORDER BY archive_id DESC LIMIT 1",
        (archivedPath,),
    ).fetchone()


def delete_area(dbConn, areaId):
    """
    *remove an area from the live index, cascading to its categories and IDs*

    Does not commit - the caller owns the transaction, since archiving has
    to write the `archived_entities` rows in the same one.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``areaId`` -- the area's id
    """
    dbConn.execute("DELETE FROM areas WHERE area_id = ?", (areaId,))


def delete_category(dbConn, categoryId):
    """
    *remove a category from the live index, cascading to its IDs*

    Does not commit - see `delete_area`.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``categoryId`` -- the category's id
    """
    dbConn.execute("DELETE FROM categories WHERE category_id = ?", (categoryId,))


def delete_id(dbConn, idId):
    """
    *remove an ID from the live index*

    Does not commit - see `delete_area`.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``idId`` -- the ID's id
    """
    dbConn.execute("DELETE FROM ids WHERE id_id = ?", (idId,))


def delete_system_folders_with_prefix(dbConn, keyPrefix):
    """
    *forget every `system_folders` row whose key starts with `keyPrefix`*

    Archiving a category or area takes its reserved `.00`-`.09` scaffolding
    with it physically, but those rows must not survive: `folders.create_reserved_system_ids`
    early-returns on an already-recorded key, so a future category handed
    the same AC number would silently get no scaffolding of its own and
    inherit paths pointing inside the archive.

    Does not commit - see `delete_area`.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``keyPrefix`` -- the folder-key prefix, e.g. `"areas.11."`

    **Return:**

    - ``deleted`` -- how many rows were removed
    """
    cursor = dbConn.execute(
        "DELETE FROM system_folders WHERE folder_key LIKE ? || '%'", (keyPrefix,)
    )
    return cursor.rowcount


def delete_entity_links(dbConn, entityType, entityKey):
    """
    *forget an entity's Craft, Todoist and Google Drive links*

    Called on archive so the next sync neither refreshes nor re-links the
    entity. Craft link rows are keyed by several entity types for the one
    entity (`id` for its folder, `id:index` for its index document), so the
    `:index` variant is cleared alongside.

    Does not commit - see `delete_area`.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``entityType`` -- the entity's type, e.g. `"id"`
    - ``entityKey`` -- the entity's key, unique within its type
    """
    for table in ("craft_links", "todoist_links", "gdrive_links"):
        dbConn.execute(
            f"DELETE FROM {table} WHERE entity_type IN (?, ?) AND entity_key = ?",
            (entityType, f"{entityType}:index", str(entityKey)),
        )


def delete_dropbox_links_with_prefix(dbConn, pathPrefix):
    """
    *forget every cached Dropbox share link at or below a folder path*

    The folder has moved, so its old share links no longer describe it -
    dropping them means fresh ones are minted at the new path on the next
    sync.

    Does not commit - see `delete_area`.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``pathPrefix`` -- the old absolute folder path

    **Return:**

    - ``deleted`` -- how many rows were removed
    """
    cursor = dbConn.execute(
        "DELETE FROM dropbox_links WHERE folder_path = ? OR folder_path LIKE ? || '/%'",
        (pathPrefix, pathPrefix),
    )
    return cursor.rowcount


# ---------------------------------------------------------------------- #
# sync drift markers - see `background_sync` and `docs/adr/0001-...`
# ---------------------------------------------------------------------- #

MIRRORS = ("gdrive", "todoist", "craft")


def record_sync_success(dbConn, mirror):
    """
    *mark a mirror as having synced cleanly, clearing any recorded failure*

    A success clears the failure fields outright rather than leaving them
    for history: the marker answers "is this mirror currently drifted?",
    and a stale failure alongside a newer success would make every reader
    compare timestamps to find out.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``mirror`` -- one of `MIRRORS`
    """
    dbConn.execute(
        "INSERT INTO sync_drift(mirror, last_success_at, last_failure_at, last_failure_reason, last_failure_class) "
        "VALUES (?, strftime('%Y-%m-%d %H:%M:%S','now'), NULL, NULL, NULL) "
        "ON CONFLICT(mirror) DO UPDATE SET "
        "last_success_at = strftime('%Y-%m-%d %H:%M:%S','now'), "
        "last_failure_at = NULL, last_failure_reason = NULL, last_failure_class = NULL",
        (mirror,),
    )
    dbConn.commit()


def record_sync_failure(dbConn, mirror, reason, failureClass):
    """
    *mark a mirror as drifted, keeping whatever last success it already had*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``mirror`` -- one of `MIRRORS`
    - ``reason`` -- the failure message, as shown to the user
    - ``failureClass`` -- a `background_sync` reason class: `rate-limited`, `auth`, `network` or `unknown`
    """
    dbConn.execute(
        "INSERT INTO sync_drift(mirror, last_failure_at, last_failure_reason, last_failure_class) "
        "VALUES (?, strftime('%Y-%m-%d %H:%M:%S','now'), ?, ?) "
        "ON CONFLICT(mirror) DO UPDATE SET "
        "last_failure_at = strftime('%Y-%m-%d %H:%M:%S','now'), "
        "last_failure_reason = excluded.last_failure_reason, "
        "last_failure_class = excluded.last_failure_class",
        (mirror, reason, failureClass),
    )
    dbConn.commit()


def drifted_mirrors(dbConn):
    """
    *every mirror whose last sync failed and has not since succeeded*

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection

    **Return:**

    - ``drifted`` -- a list of `sqlite3.Row`, one per drifted mirror, ordered as `MIRRORS`
    """
    rows = dbConn.execute(
        "SELECT * FROM sync_drift WHERE last_failure_at IS NOT NULL"
    ).fetchall()
    byMirror = {row["mirror"]: row for row in rows}
    return [byMirror[mirror] for mirror in MIRRORS if mirror in byMirror]
