#!/usr/bin/env python
# encoding: utf-8
"""
*Change the emoji on an existing area, category, project or system folder*

Author
: David Young
"""

import os

from aardvark_jd import codes, db, emoji_picker, folders, paths

SYSTEM_DOMAIN = "system"


def rename_folder_and_reindex(dbConn, oldFolderPath, newFolderName, updateRow):
    """
    *rename a folder on disk and repoint the index at it, atomically*

    The database write is committed **before** the physical rename, not
    after. `00_INDEX` is itself one of the folders this function can rename,
    and it's the folder the open SQLite connection's file lives in - a
    rollback-journal commit has to `unlink()` its journal file by path, and
    if the parent directory has already been renamed away that path no
    longer resolves, so the commit fails with `sqlite3.OperationalError:
    disk I/O error` even though every write up to that point succeeded.
    Committing first means the transaction finalises while `oldFolderPath`
    is still valid; only the plain filesystem rename happens afterwards. If
    that rename then fails, the index briefly points at a path that doesn't
    exist yet - the old values are written back and committed again before
    re-raising, so the index and the filesystem never end up disagreeing for
    longer than it takes to run the compensating write. Renaming a folder
    invalidates the stored `folder_path` of everything nested inside it, so
    descendants are rewritten in the same transaction as the target row
    itself.

    **Key Arguments:**

    - ``dbConn`` -- an open SQLite connection
    - ``oldFolderPath`` -- the folder's current absolute path
    - ``newFolderName`` -- the folder's new on-disk name
    - ``updateRow`` -- a callable taking `(newFolderName, newFolderPath)` that writes the target row, without committing

    **Return:**

    - ``newFolderPath`` -- the folder's new absolute path

    **Usage:**

    ```python
    from aardvark_jd.set_emoji import rename_folder_and_reindex
    newPath = rename_folder_and_reindex(
        dbConn, oldPath, "A.10_19_health🏥",
        lambda name, path: db.update_area_emoji(dbConn, areaId, "🏥", name, path),
    )
    ```
    """
    parentPath = os.path.dirname(oldFolderPath.rstrip("/"))
    return folders.move_folder_and_reindex(
        dbConn, oldFolderPath, f"{parentPath}/{newFolderName}", updateRow,
    )


class set_emoji(object):
    """
    *change the emoji on an existing area, category, project or static system folder*

    **Key Arguments:**

    - ``log`` -- logger
    - ``dbConn`` -- an open SQLite connection
    - ``ref`` -- an area ref (`"A10-19"`), category ref (`"A11"`), or system folder key (`"root.areas"`)
    - ``newEmoji`` -- the emoji to use

    The target's domain comes from the ref itself: anything carrying a
    Johnny Decimal domain letter belongs to that domain, and anything else is
    taken to be a system folder key.

    **Usage:**

    ```python
    from aardvark_jd.set_emoji import set_emoji
    label, folderPath, _ = set_emoji(
        log=log, dbConn=dbConn, ref="A10-19", newEmoji="🏥"
    ).get()
    ```
    """

    def __init__(self, log, dbConn, ref, newEmoji):
        self.log = log
        self.dbConn = dbConn
        self.ref = ref
        self.domain = self._resolve_domain(ref)
        self.newEmoji = emoji_picker.validate_chosen_emoji(newEmoji)

    def get(self):
        """
        *rename the target folder to carry the new emoji, and repoint the index*

        **Return:**

        - ``label`` -- a human-readable label for what was retargeted
        - ``folderPath`` -- the target folder's new absolute path
        - ``details`` -- what the JSON contract reports: the `emoji_source`, always `chosen` here because `set_emoji` takes the emoji as a positional
        """
        self.log.debug("starting the ``get`` method")

        if self.domain == SYSTEM_DOMAIN:
            label, folderPath = self._set_system_folder_emoji()
        elif codes.parse_area_ref_is_area(self.ref):
            label, folderPath = self._set_area_emoji()
        else:
            label, folderPath = self._set_category_emoji()

        self.log.debug("completed the ``get`` method")
        # `set_emoji <ref> <emoji>` HAS NO SUGGESTER PATH: THE EMOJI IS ALWAYS
        # EXPLICIT, WHETHER TYPED AT A TERMINAL OR SETTLED BY ALFRED'S EMOJI
        # STEP. THE FIELD IS REPORTED ANYWAY SO EVERY MUTATING RESULT ALFRED
        # RENDERS HAS THE SAME SHAPE.
        return label, folderPath, {"emoji_source": "chosen"}

    def _resolve_domain(self, ref):
        """
        *work out which domain a ref targets, from its domain letter*

        A ref that parses as a Johnny Decimal area or category code belongs to
        the domain its letter names; anything else is treated as a system
        folder key, and is validated by `paths.skeleton_entry` when the rename
        runs.

        **Key Arguments:**

        - ``ref`` -- the ref supplied on the command-line

        **Return:**

        - ``domain`` -- `areas`, `resources`, `projects` or `system`
        """
        if not codes.is_jd_ref(ref):
            return SYSTEM_DOMAIN
        return codes.domain_from_ref(ref)

    def _set_area_emoji(self):
        """
        *retarget an area folder*

        **Return:**

        - ``label`` -- the area's Johnny Decimal code
        - ``folderPath`` -- the area folder's new absolute path
        """
        decadeStart = codes.parse_area_ref(self.ref)
        area = db.get_area(self.dbConn, self.domain, decadeStart)
        if area is None:
            raise ValueError(f"no area '{self.ref}' found in domain '{self.domain}'")

        newFolderName = folders.area_folder_name(
            self.domain, area["decade_start"], area["decade_end"], area["title"], self.newEmoji
        )
        folderPath = rename_folder_and_reindex(
            self.dbConn, area["folder_path"], newFolderName,
            lambda name, path: db.update_area_emoji(
                self.dbConn, area["area_id"], self.newEmoji, name, path
            ),
        )
        label = codes.format_area_code(self.domain, area["decade_start"], area["decade_end"])
        return label, folderPath

    def _set_category_emoji(self):
        """
        *retarget a category folder*

        **Return:**

        - ``label`` -- the category's Johnny Decimal code
        - ``folderPath`` -- the category folder's new absolute path
        """
        acNumber = codes.parse_category_ref(self.ref)
        category = db.get_category(self.dbConn, self.domain, acNumber)
        if category is None:
            raise ValueError(f"no category '{self.ref}' found in domain '{self.domain}'")

        newFolderName = folders.category_folder_name(
            self.domain, category["ac_number"], category["title"], self.newEmoji
        )
        folderPath = rename_folder_and_reindex(
            self.dbConn, category["folder_path"], newFolderName,
            lambda name, path: db.update_category_emoji(
                self.dbConn, category["category_id"], self.newEmoji, name, path
            ),
        )
        label = codes.format_category_code(self.domain, category["ac_number"])
        return label, folderPath

    def _set_system_folder_emoji(self):
        """
        *retarget a static system folder*

        **Return:**

        - ``label`` -- the folder's logical key
        - ``folderPath`` -- the folder's new absolute path
        """
        skeletonEntry = paths.skeleton_entry(self.ref)
        baseName = skeletonEntry[2]

        row = db.get_system_folder(self.dbConn, self.ref)
        if row is None:
            raise KeyError(f"no system folder is recorded for key '{self.ref}'")

        newFolderName = folders.system_folder_name(baseName, self.newEmoji)
        folderPath = rename_folder_and_reindex(
            self.dbConn, row["folder_path"], newFolderName,
            lambda name, path: db.update_system_folder(self.dbConn, self.ref, name, path),
        )
        return self.ref, folderPath
