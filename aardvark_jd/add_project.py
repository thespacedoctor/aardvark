#!/usr/bin/env python
# encoding: utf-8
"""
*Create a new project (Johnny Decimal ID) in an existing project category, from a template zip or blank*

Author
: David Young
"""

import glob
import os
import shutil
import sys
import zipfile

from aardvark_jd import codes, db, folders, paths, spell_check

BLANK_CHOICE = "blank"


class add_project(object):
    """
    *create a new project ID within a `projects` category, either from that category's own `04_templates` zip or a blank scaffold*

    Projects are Johnny Decimal coded like Areas/Resources - a project is a
    plain ID (no emoji) created inside an existing project category.
    Templates are read from the category's own reserved `04_templates`
    system ID, not a shared domain-level pool - each project category
    curates its own template set.

    **Key Arguments:**

    - ``log`` -- logger
    - ``dbConn`` -- an open SQLite connection
    - ``categoryRef`` -- the parent project category reference, e.g. `"P11"`
    - ``projectTitle`` -- the new project's title
    - ``templateName`` -- the template zip's basename (with or without `.zip`), or `"blank"`. If `None`, prompts interactively (or defaults to blank in a non-interactive session). Default `None`.
    - ``settings`` -- the aardvark settings dict. Default `None`.

    **Usage:**

    ```python
    from aardvark_jd.add_project import add_project
    code, title, folderPath, templateUsed, details = add_project(
        log=log, dbConn=dbConn, categoryRef="P11", projectTitle="My Project",
    ).get()
    ```
    """

    def __init__(self, log, dbConn, categoryRef, projectTitle, templateName=None, settings=None,
                 interactive=None):
        self.log = log
        self.dbConn = dbConn
        self.categoryRef = categoryRef
        self.projectTitle = projectTitle
        self.templateName = templateName
        self.settings = settings
        self.interactive = interactive

    def get(self):
        """
        *resolve the category, template choice and title, then create the project ID*

        **Return:**

        - ``code`` -- the new project's Johnny Decimal code, e.g. `P11.01`
        - ``title`` -- the new project's title
        - ``folderPath`` -- the new project folder's absolute path
        - ``templateUsed`` -- `"blank"` or the template zip's basename
        - ``details`` -- what the JSON contract reports about the title spell-check: `corrections` applied and `suggestions` still outstanding
        """
        self.log.debug("starting the ``get`` method")

        acNumber = codes.parse_category_ref(self.categoryRef, domain="projects")
        category = db.get_category(self.dbConn, "projects", acNumber)
        if category is None:
            raise ValueError(f"no category '{self.categoryRef}' found in domain 'projects'")

        try:
            templatesFolder = paths.resolve(self.dbConn, f"projects.{acNumber}.04_templates")
            templateZips = sorted(glob.glob(f"{templatesFolder}/*.zip"))
        except KeyError:
            # NO RESERVED `04_templates` SYSTEM ID YET (A CATEGORY CREATED BEFORE
            # THAT SCAFFOLDING EXISTED, NOT YET `repair_emoji`'D) - TREAT AS "NO
            # TEMPLATES" RATHER THAN FAILING add_project OUTRIGHT.
            templateZips = []

        templateChoice = self._resolve_template_choice(templateZips)
        # SEE `add_area.get` - CHECKED BEFORE ANY WRITE.
        details = spell_check.checked_title_details(
            self.projectTitle, self.settings, self.log, interactive=self.interactive,
        )
        title = details["title"]

        itemNumber = folders.next_id_number(self.dbConn, "projects", category)
        folderName = folders.id_folder_name("projects", acNumber, itemNumber, title)
        folderPath = folders.make_folder(category["folder_path"], folderName)

        if templateChoice == BLANK_CHOICE:
            self._build_blank_scaffold(folderPath)
            templateUsed = BLANK_CHOICE
        else:
            with zipfile.ZipFile(templateChoice) as zipHandle:
                zipHandle.extractall(folderPath)
            templateUsed = os.path.basename(templateChoice)

        db.insert_id(
            self.dbConn, category["category_id"], "projects", acNumber, itemNumber,
            title, "", folderName, folderPath,
        )
        code = codes.format_id_code("projects", acNumber, itemNumber)

        self.log.debug("completed the ``get`` method")
        # SEE `add_id.get`.
        return code, title, folderPath, templateUsed, {
            "corrections": details["corrections"],
            "suggestions": details["suggestions"],
        }

    def _resolve_template_choice(self, templateZips):
        """
        *resolve which template to use, from the constructor arg or an interactive prompt*

        **Key Arguments:**

        - ``templateZips`` -- the available template zip paths

        **Return:**

        - ``choice`` -- `"blank"` or the chosen zip's path
        """
        if self.templateName is not None:
            if self.templateName == BLANK_CHOICE:
                return BLANK_CHOICE
            for zipPath in templateZips:
                basename = os.path.basename(zipPath)
                if self.templateName in (basename, basename[: -len(".zip")]):
                    return zipPath
            raise ValueError(f"no template named '{self.templateName}' found in '04_templates'")

        if not sys.stdin.isatty():
            self.log.warning("non-interactive session with no <templateName> given - defaulting to blank")
            return BLANK_CHOICE

        print("Available project templates:")
        print("  0) New blank project (README.md, input/, output/)")
        for index, zipPath in enumerate(templateZips, start=1):
            print(f"  {index}) {os.path.basename(zipPath)}")

        while True:
            choice = input("Select a template [0]: ").strip() or "0"
            if choice.isdigit() and 0 <= int(choice) <= len(templateZips):
                break
            print("Invalid choice, try again.")

        return BLANK_CHOICE if choice == "0" else templateZips[int(choice) - 1]

    def _build_blank_scaffold(self, folderPath):
        """
        *populate a project folder with the bundled blank scaffold (README.md, input/, output/)*

        **Key Arguments:**

        - ``folderPath`` -- the new project folder's absolute path
        """
        sourceDirectory = os.path.dirname(__file__) + "/resources/templates_src/blank_starter"
        for entry in os.listdir(sourceDirectory):
            sourcePath = os.path.join(sourceDirectory, entry)
            destinationPath = os.path.join(folderPath, entry)
            if os.path.isdir(sourcePath):
                shutil.copytree(sourcePath, destinationPath)
            else:
                shutil.copy2(sourcePath, destinationPath)
