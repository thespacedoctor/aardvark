```bash
    
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
    
```
