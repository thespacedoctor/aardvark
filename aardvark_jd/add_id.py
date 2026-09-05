#!/usr/bin/env python
# encoding: utf-8
"""
*Add a new Johnny Decimal ID (leaf item) to an existing category*

Author
: David Young
"""

from aardvark_jd import codes, db, folders, spell_check


class add_id(object):
    """
    *create a new Johnny Decimal ID within a category, auto-assigning the next available item number*

    ID folders are never emoji-suffixed.

    **Key Arguments:**

    - ``log`` -- logger
    - ``dbConn`` -- an open SQLite connection
    - ``domain`` -- `areas`, `resources` or `projects`
    - ``categoryRef`` -- the parent category reference, e.g. `"A11"`
    - ``title`` -- the ID's title
    - ``description`` -- the ID's description
    - ``settings`` -- the aardvark settings dict. Default `None`.
    - ``interactive`` -- may the spell-check prompt? Default `None`, meaning "ask if stdin is a terminal". `--json` passes `False`.

    **Usage:**

    ```python
    from aardvark_jd.add_id import add_id
    code, folderPath, details = add_id(
        log=log, dbConn=dbConn, domain="areas", categoryRef="A11", title="Cardiologist", description="..."
    ).get()
    ```
    """

    def __init__(self, log, dbConn, domain, categoryRef, title, description, settings=None,
                 interactive=None):
        self.log = log
        self.dbConn = dbConn
        self.domain = codes.validate_domain(domain)
        self.categoryRef = categoryRef
        self.title = title
        self.description = description
        self.settings = settings
        self.interactive = interactive

    def get(self):
        """
        *create the ID's folder and index row*

        **Return:**

        - ``code`` -- the new ID's Johnny Decimal code, e.g. `A.11.01`
        - ``folderPath`` -- the new ID folder's absolute path
        - ``details`` -- what the JSON contract reports about the spell-check: `corrections` applied and `suggestions` still outstanding
        """
        self.log.debug("starting the ``get`` method")

        acNumber = codes.parse_category_ref(self.categoryRef, domain=self.domain)
        category = db.get_category(self.dbConn, self.domain, acNumber)
        if category is None:
            raise ValueError(f"no category '{self.categoryRef}' found in domain '{self.domain}'")

        # SEE `add_area.get` - CHECKED BEFORE ANY WRITE.
        details = spell_check.checked_title_details(
            self.title, self.settings, self.log, interactive=self.interactive,
        )
        title = details["title"]
        itemNumber = folders.next_id_number(self.dbConn, self.domain, category)
        folderName = folders.id_folder_name(self.domain, acNumber, itemNumber, title)
        folderPath = folders.make_folder(category["folder_path"], folderName)

        db.insert_id(
            self.dbConn, category["category_id"], self.domain, acNumber, itemNumber,
            title, self.description, folderName, folderPath,
        )
        code = codes.format_id_code(self.domain, acNumber, itemNumber)

        self.log.debug("completed the ``get`` method")
        # THE WHOLE OUTCOME COMES BACK THROUGH THE RETURN. NOTHING IS LEFT ON
        # THE WORKER TO BE READ AFTERWARDS, WHICH WOULD SPLIT THE CONTRACT IN
        # TWO AND MAKE THE CALL ORDER LOAD-BEARING.
        return code, folderPath, {
            "corrections": details["corrections"],
            "suggestions": details["suggestions"],
        }
