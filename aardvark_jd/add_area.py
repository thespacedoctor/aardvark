#!/usr/bin/env python
# encoding: utf-8
"""
*Add a new Johnny Decimal area to the Areas or Resources domain*

Author
: David Young
"""

from aardvark_jd import codes, db, emoji_picker, folders, paths, spell_check


class add_area(object):
    """
    *create a new Johnny Decimal area, auto-assigning the next available decade*

    **Key Arguments:**

    - ``log`` -- logger
    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas`, `resources` or `projects`
    - ``title`` -- the area's title
    - ``description`` -- the area's description
    - ``chosenEmoji`` -- an emoji supplied on the command-line, bypassing the suggester. Default `None`.
    - ``settings`` -- the aardvark settings dict. Default `None`.
    - ``interactive`` -- may the spell-check prompt? Default `None`, meaning "ask if stdin is a terminal". `--json` passes `False`.

    **Usage:**

    ```python
    from aardvark_jd.add_area import add_area
    code, folderPath, details = add_area(
        log=log, dbConn=dbConn, domain="areas", title="Health", description="..."
    ).get()
    ```
    """

    def __init__(self, log, dbConn, domain, title, description, chosenEmoji=None, settings=None,
                 interactive=None):
        self.log = log
        self.dbConn = dbConn
        self.domain = codes.validate_domain(domain)
        self.title = title
        self.description = description
        self.chosenEmoji = chosenEmoji
        self.settings = settings
        self.interactive = interactive

    def get(self):
        """
        *create the area's folder and index row, plus its reserved system folder*

        **Return:**

        - ``code`` -- the new area's Johnny Decimal code, e.g. `A.10-19`
        - ``folderPath`` -- the new area folder's absolute path
        - ``details`` -- what the JSON contract reports: `corrections` applied, `suggestions` still outstanding, and the `emoji_source`
        """
        self.log.debug("starting the ``get`` method")

        decadeStart, decadeEnd = folders.next_area_decade(self.dbConn, self.domain)
        # BEFORE THE EMOJI PROMPT: ACCEPTING A CORRECTION CHANGES THE TITLE THE
        # EMOJI IS DERIVED FROM, AND BEFORE ANY WRITE, SO THE CORRECTED TITLE IS
        # THE ONE VALUE THE FOLDER, THE INDEX ROW AND EVERY MIRROR ARE BUILT FROM.
        details = spell_check.checked_title_details(
            self.title, self.settings, self.log, interactive=self.interactive,
        )
        title = details["title"]
        pickedEmoji, emojiSource = emoji_picker.resolve_emoji_with_source(
            title, self.description, chosenEmoji=self.chosenEmoji,
        )
        folderName = folders.area_folder_name(self.domain, decadeStart, decadeEnd, title, pickedEmoji)
        parentPath = paths.resolve(self.dbConn, f"root.{self.domain}")
        folderPath = folders.make_folder(parentPath, folderName)

        db.insert_area(
            self.dbConn, self.domain, decadeStart, decadeEnd, title, self.description,
            pickedEmoji, folderName, folderPath,
        )
        code = codes.format_area_code(self.domain, decadeStart, decadeEnd)

        self._create_area_system_folder(decadeStart, folderPath)

        self.log.debug("completed the ``get`` method")
        # SEE `add_id.get` - THE WHOLE OUTCOME COMES BACK THROUGH THE RETURN,
        # NOTHING IS LEFT ON THE WORKER TO BE READ AFTERWARDS.
        return code, folderPath, {
            "corrections": details["corrections"],
            "suggestions": details["suggestions"],
            "emoji_source": emojiSource,
        }

    def _create_area_system_folder(self, decadeStart, areaFolderPath):
        """
        *create the area's reserved `<X>.<D0>_system` folder (with its own ten reserved IDs), occupying the reserved X0 category slot*

        **Key Arguments:**

        - ``decadeStart`` -- the area's decade-start number, also its reserved X0 category number
        - ``areaFolderPath`` -- the area folder's absolute path, the parent for this folder
        """
        systemFolderName = folders.category_folder_name(
            self.domain, decadeStart, "system", paths.SYSTEM_FOLDER_EMOJI
        )
        systemFolderPath = folders.make_folder(areaFolderPath, systemFolderName)
        db.insert_system_folder(
            self.dbConn, f"{self.domain}.{decadeStart}.system", systemFolderName, systemFolderPath
        )
        folders.create_reserved_system_ids(self.dbConn, self.domain, decadeStart, systemFolderPath)
