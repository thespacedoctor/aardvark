# The aardvark workflow: build specification

This document is the buildable specification for the Alfred 5 workflow that drives the `aardvark` CLI from the keyboard. It is the output of the wayfinder map at `.scratch/alfred-workflow/map.md` and is written to be handed to a test-first implementation session.

Every decision below was settled by a ticket on that map. Where a statement is load-bearing, the ticket that settled it is cited so a reader can find the evidence rather than the conclusion. Nothing here is a fresh opinion.

Vocabulary follows `CONTEXT.md`, in particular **handoff**, **reveal**, **surface**, **confirmation screen**, **binary pointer**, **error row**, **the contract** and **index payload**. Alfred's own terms — Workflow, Script Filter, Modifier, Keyword, Configuration variable — carry Alfred's meanings.

## Contents

- [Scope](#scope)
- [The command inventory](#the-command-inventory)
- [The CLI changes](#the-cli-changes)
- [The workflow's file layout](#the-workflows-file-layout)
- [The module layout inside the package](#the-module-layout-inside-the-package)
- [The build order](#the-build-order)
- [The test plan](#the-test-plan)
- [The documentation changes](#the-documentation-changes)
- [Known open questions](#known-open-questions)

## Scope

Thirteen commands are in scope. The map's charting bullet lists them, and `commands.py` confirms there is no `dropbox_sync`; the phrase "fifteen in-scope commands" in the map's ticket 13 was a miscount and is corrected here.

**Read and navigate:** `fd`, `open`, `cd`.

**Mutating:** `add_area`, `add_category`, `add_id`, `add_project`, `archive`, `set_emoji`.

**Sync and maintenance:** `craft_sync`, `todoist_sync`, `gdrive_sync`, `repair_emoji`.

Out of scope, and why:

- **The setup commands** (`init`, `connect_craft`, `connect_todoist`, `connect_dropbox`, `connect_gdrive`, `completion`, `shell_init`). One-time, browser-interactive OAuth flows and one-off token pastes. They are no worse in a terminal, and an Alfred surface for them would be built once and never used. `install_alfred` is the deliberate exception: it is a setup command whose purpose is to build the surface, so it exists in the CLI's advanced group and the workflow never offers it as a row of its own.
- **Cross-machine sync of the workflow directory.** The `install_alfred` symlink is an authoring-machine convenience.
- **End-to-end tests that drive Alfred itself.** See [The test plan](#the-test-plan).
- **A stable, public `--json` API.** The contract is internal and unstable.

## The command inventory

### The single keyword and the one item list

One Alfred Keyword, `av`, backed by one Script Filter in **Alfred Filters Results** mode with match mode **Word matching — Any order** (`alfredfiltersresultsmatchmode: 2`). `av` is free across the user's installed workflows; `fd` and `open` are both taken, which is what ruled out a keyword per command.

Because Alfred does the filtering, **the script runs once with an empty query** and Alfred filters client-side from then on. There is no branching on what the user typed. The consequence is structural: command rows and entity rows are emitted **together, in one list**.

The list is:

1. **Command rows**, emitted first, one per mutating and maintenance command: `add_area`, `add_category`, `add_id`, `add_project`, `archive`, `set_emoji`, `craft_sync`, `todoist_sync`, `gdrive_sync`, `repair_emoji`. Ten rows.
2. **Entity rows**, one per entity in the index payload, in `fd --json` index order.

`fd`, `open` and `cd` get no command rows of their own. They are not things the user picks; they are what an entity row's Enter and modifiers already do.

A command row's `match` string is the command's words only — `add id`, not `add` — so a single typed word never lifts a command row above the entities. Collision with a real title is possible and accepted; the alternatives were a sigil (`av >add id`), which taxes every mutating command with an extra keystroke, and a second keyword, which reopens the one-keyword decision the charting settled.

### The entity row

Built from the contract's entity record. One item per entity:

| Item field | Value |
| --- | --- |
| `uid` | `entity.id`, the `"<domain>:<code>"` string |
| `title` | `<emoji> <code> <title>`, with the workflow's own fallback when `emoji` is `""` |
| `subtitle` | `folder_path` relative to `system.root_path` |
| `match` | `<code> <title> <path segments below root> <description>` |
| `arg` | `folder_path` |
| `variables.urls` | the record's whole `urls` object, as a JSON string |
| `variables.entity_id` | `entity.id` |
| `skipknowledge` | `true`, always |
| `icon` | the folder icon |

**`skipknowledge: true` is permanent, not a placeholder.** Alfred's learning is keyed on the `uid` string, and `archive` is documented as retiring an entity "freeing its number", so code reuse is a designed-in event. A recycled `A11.10` would inherit its predecessor's rank and surface it confidently. State this reason in a comment beside it so a future reader does not "fix" it.

The payload shape is **lean**: one `variables.urls` object per item, and no `mods` carrying duplicate URLs. Alfred gives a mod's `variables` no inheritance — they replace the item's wholesale — so the fat shape repeats the discriminator in every mod block and costs roughly 50 per cent more bytes. Since Alfred holds the whole index in memory, a modifier resolving a URL from `variables.urls` is a cache read, not a re-invocation of the CLI.

Including the description in `match` costs about 7 per cent of payload and is worth it: description search is genuinely wanted, and the loosened matching it brings is acceptable. Revisit only if false matches prove annoying in use.

### What Enter and the modifiers do

| Key | Action |
| --- | --- |
| Enter | Open every synced mirror at once, matching what `aardvark open` does today |
| ⌘ | **Reveal** the folder in Finder (`urls.finder`) |
| ⌥ | **Handoff**: open a new terminal tab at `folder_path` |
| ⌃ | Show the **destinations sub-list**: Craft, Todoist, Google Drive, Dropbox as four rows |

⇧ is left alone — Alfred binds it to Quick Look.

The two daily actions get single modifiers. The four individual mirrors go to a sub-list rather than to chords (⌘⌥, ⌘⌃ and so on) because a sub-list can *show* which mirrors are unsynced: a row whose URL is `null` renders as "not synced to Craft" and, on Enter, runs the relevant sync rather than failing silently. An unbound chord cannot do that.

Enter on an entity synced to nothing is not an error. `open --json` returns the record with every URL `null` except `finder`, and the workflow shows a "sync now" row.

### The handoff

One line, in a Run Script object:

```bash
open -a "$TERMINAL_APP" "$path"
```

No AppleScript. Against a running iTerm this opens a new tab in the existing window, which is the wanted behaviour, and it never builds a shell string, so it has none of the quoting holes the AppleScript alternative has — including the newline-in-a-folder-name case that submits the line early.

`TERMINAL_APP` resolves from the `AARDVARK_TERMINAL_APP` configuration variable when set; unset, it is iTerm when `/Applications/iTerm.app` exists and `Terminal.app` otherwise. Every Mac has Terminal, so the chain always terminates. `open -a` exits non-zero on a missing app, which becomes an error row whose Enter opens the workflow configuration.

Shell integration does not load in the new tab on the authoring machine — `av cd` there prints a path instead of moving. This is pre-existing, reproduces in `/bin/bash -lic`, was traced into the dotfiles rather than this repo, and is ruled out of scope. It costs the workflow nothing: the handoff sets the directory itself and never uses the shell wrapper.

### The mutating flow

Command row Enter starts a flow. Every mutating flow has the same skeleton:

```
reference pick  →  argument entry  →  [emoji]  →  confirmation screen  →  run  →  success surface
```

**Reference pick.** A Script Filter listing the valid parents for that command — categories for `add_id`, areas for `add_category`, domain letters for `add_area`, project categories for `add_project`, any entity for `archive` and `set_emoji`.

**Argument entry.** One free-text field taking `title, description`, split on the **first comma only**; everything after it is the description. Comma beat `::`, `/`, `—`, ` - ` and `>` against real titles: it needs no shift key and, unlike the hyphen, does not collide with the hyphens that appear in real titles ("Insurance - buildings and contents"). A title containing a comma loses the fragment after the first one to the description; the confirmation screen catches that before anything is written.

The step shows the parse and nothing else — two lines, `title = «…»` and `description = «…»`. No JD code (showing it next to the title field invites the user to type the code into the title) and no folder path.

A **first row returns to the reference pick**. Not a key: Alfred's Escape discards the run rather than stepping back, and a chord hint in the subtitle would compete with the parse the same subtitle is showing. A row is visible without being read and costs nothing when unused.

**Accepted divergence, recorded during slice 2:** the back row leads *only while the field is empty*. Taken unconditionally, "first row" makes Return discard what the user has just typed, which is a worse trap than the one the row exists to avoid. Once anything is typed the parse takes the top row and the back row sits below it — still visible without being read, which is the property the decision rested on.

**Emoji.** Only for `add_area`, `add_category` and `set_emoji`. IDs are never emoji-suffixed, so `add_id` and `add_project` have no emoji step.

The step shows `emoji_picker.pick_emoji`'s offline result as the default and lets the user accept it or enter one manually, via Alfred's own emoji picker or a free-text search over the emoji index. There is no network call and nothing to fail: the Claude suggester was removed from the CLI entirely ([ADR 0002](adr/0002-drop-the-claude-emoji-suggester.md)).

Make the manual path prominent. `pick_emoji` returns the bare `📁` fallback for most area- and category-style titles ("Photography", "Cycling", "Genealogy", "Mortgage"), so the default will often be `📁` and manual entry carries the real load.

**Confirmation screen.** The final Return of the argument step does **not** commit. An explicit confirmation screen shows exactly what will be created; Return there commits, Escape backs out. A preview row is not enough of a confirmation.

Its rows, in order:

1. **"Create as typed"** — first and default, always present.
2. **One correction row per suspect token**, when the contract's `suggestions` array is non-empty. Each is accepted independently, and accepting one **re-renders the confirmation** rather than committing, so Return always means create.

The correction rows are the whole of the spell-check surface. There is no spell-check step. On 141 real human-typed titles the checker fires on about 4.3 per cent of them after ticket 16's tuning lands — roughly one title in twenty-three — which is far too rare to justify a step, while the check itself costs 0.002 ms, so a shape that costs no keystrokes is free.

**Teaching the learned vocabulary needs its own explicit modifier** on a correction row. This is a deliberate divergence from the CLI, which teaches a word when the user declines a suggestion. Under this shape declining is the default path, so the CLI's rule would teach a word on every reflexive Return. Record the divergence in the spell-check section of the docs rather than treating it as an inconsistency to fix.

**Run.** The command is invoked with `--json` and its suppressing flags (`-e`, `-t`, `-y`), never interactively. Sync stays backgrounded: Alfred fires, posts a notification immediately, and lets the existing drift markers catch mirror failures later.

**Success surface.** Required for every mutating flow, and not optional decoration — it is the whole of the recall story. It is built from the `entity` record the contract's mutating result already returns, and offers reveal, handoff and the mirrors directly. This is also what covers the accepted one-invocation cache lag: the new entity is reachable immediately from the result even though the cached index has not caught up.

### Per-command inventory

| Command | Reference pick | Argument entry | Emoji | Confirmation | Notes |
| --- | --- | --- | --- | --- | --- |
| `fd` | — | — | — | — | No surface of its own. It *is* the entity list. |
| `open` | — | — | — | — | No surface. Enter and the ⌃ sub-list on an entity row. |
| `cd` | — | — | — | — | No surface. ⌥ on an entity row, as the handoff. |
| `add_area` | domain letter (A/R/P) | `title, description` | yes | yes | |
| `add_category` | area | `title, description` | yes | yes | |
| `add_id` | category | `title, description` | no | yes | The flow ticket 06 prototyped |
| `add_project` | project category | **title only** | no | yes | Template pick as a list step before the title. See the note below. |
| `archive` | any entity | — | — | yes | Invoked with `-y`; the confirmation screen replaces the CLI prompt |
| `set_emoji` | any entity | — | yes | yes | Reference pick plus the emoji step |
| `craft_sync` | — | — | — | no | Command row, fires, notifies |
| `todoist_sync` | — | — | — | no | Command row, fires, notifies |
| `gdrive_sync` | — | — | — | no | Command row, fires, notifies |
| `repair_emoji` | — | — | — | **yes** | Command row, then a confirmation |

**`add_project` takes no description.** Its docopt line is `add_project <category> <projectTitle> [-t <templateName>]` — one positional after the category. Ticket 06's handoff described it as "`title, description` plus a template step", which is wrong against the CLI. Its argument step is a plain title field with no comma split.

**`repair_emoji` gets a confirmation and the three syncs do not.** A sync is idempotent and repairable; `repair_emoji` renames folders on disk, and it is the one command here where a mis-fire is expensive. This also keeps the confirmation screen a consistent signal: it appears exactly when something on disk changes.

### Error rows

A Script Filter cannot raise, so every failure returns as a single row carrying the diagnosis. Where a fix is obvious, Enter on that row performs it. The inventory:

| Condition | Row | Enter does |
| --- | --- | --- |
| No binary pointer file | "aardvark has not been set up on this Mac" | Copies `aardvark install_alfred` to the clipboard |
| Pointer file present, path not executable | "aardvark is not at `<the dead path>`" — the path is shown | Copies `aardvark install_alfred` to the clipboard |
| `aardvark_json` version unrecognised | "This workflow is out of step with the installed aardvark" | Copies `aardvark install_alfred` to the clipboard |
| `info.plist` version ≠ `system` package version | Warning row, never a blocker | Dismisses |
| Contract `error.kind` = `no_system` | The CLI's message | Nothing |
| Contract `error.kind` = `not_found` | The CLI's message | Nothing |
| Contract `error.kind` = `not_synced` | "Not yet synced to `<mirror>`" | Runs that mirror's sync |
| Every other `error.kind` | The CLI's `message` | Nothing |
| `open -a` non-zero (terminal app missing) | "Terminal app `<name>` was not found" | Opens the workflow configuration |

The failure rows copy the command rather than pre-typing it into a terminal, which would resurrect the AppleScript the handoff decision removed. `install_alfred` is `ADVANCED` and therefore absent from `-h`; that is acceptable **only** because these rows hand over the exact string, so discoverability never routes through the help screen.

### Caching

The Script Filter sets `cache` to `{"seconds": 3600, "loosereload": true}`. The second invocation is then instant at any scale, and `loosereload` shows the stale cache immediately while refreshing in the background.

The index changes underneath the cache whenever a mutating command runs, and the CLI has no scriptable way to flush an Alfred Script Filter's cache. The accepted behaviour is to **rely on `loosereload`'s background self-heal**: a folder created by `add_id` appears in the surface one invocation late at worst. The success surface covers the gap at the moment it matters. If tighter freshness is ever wanted, first verify whether touching the Script Filter's script file invalidates the cache — a note, not a blocker.

### Scale

Ship the whole index unconditionally. The plausible lifetime ceiling for a one-person PARA + JD system is about 5,000 entities; at that size the surface is instant cold, filter latency stays under 0.5 s, and Alfred's parse costs 67 ms. Lag first becomes noticeable at about 15,000, which is near-full JD population. The hybrid fallback — Alfred filters a capped set, `aardvark fd` keyword search on a modifier — is **not built now**. The workflow can notice it has crossed the line by reading the entity count in the payload it just fetched.

## The CLI changes

Both are written here as behaviour to test, not as code.

### The contract: a per-command `--json` flag

`--json` is added to the `Usage:` lines of the thirteen in-scope commands minus `cd`, which already prints a bare absolute path that the handoff consumes verbatim. A global flag is impossible: the usage block is a docopt spec, so a token is only recognised on the lines it appears on. A pre-docopt intercept is rejected because the mutating and sync commands must run the full stack the fast path deliberately skips.

`--json` implies non-interactivity — it never prompts. It does **not** silently imply `-w`; sync stays backgrounded.

**Envelope.** Always an object, never a bare array, always carrying an integer `aardvark_json` version.

```json
{
  "aardvark_json": 1,
  "system": { "name": "My Life", "root_path": "/Users/Dave/My Life", "generated_at": "2026-09-03T12:00:00Z" },
  "entities": [ ]
}
```

**Entity record.** Every field is verified against the live schema.

```json
{
  "id": "areas:A11.10",
  "row_key": "42",
  "type": "id",
  "domain": "areas",
  "code": "A11.10",
  "title": "Cardiologist",
  "description": "",
  "emoji": "🩺",
  "folder_path": "/Users/Dave/My Life/03_AREAS🧭/A10-19_health🏥/A11_doctors🩺/A11.10_cardiologist",
  "archived": false,
  "urls": { "finder": null, "craft": null, "todoist": null, "drive": null, "dropbox": null }
}
```

Behaviour to test:

- `id` is `"<domain>:<code>"`, stable across rename, emoji change and a from-scratch reindex; **not** stable across archive-and-reuse of a Johnny Decimal number, which is correct — a reused number is a different entity.
- `row_key` is the stringified autoincrement primary key, exposed for mirror-link correlation and debugging, never for identity.
- `type` is one of `area`, `category`, `id`; `domain` is one of `areas`, `resources`, `projects`.
- `emoji` is `""` for IDs and for a blank stored emoji. The contract does **not** substitute `labels.FALLBACK_EMOJI`; the workflow chooses its own fallback.
- Any absent URL is `null`. `urls.todoist` is populated only for the types `todoist_sync` mirrors. `urls.finder` is `null` off macOS and is computed at emit time from `folder_path`, not stored.
- `archived` is always `false` inside `entities`. `fd --json --archived` adds a sibling `"archived": [ … ]` array built from `archived_entities`, each carrying that table's own URL snapshot and no live `finder` link.
- `entities` is **flat**, never nested, for the whole-index call, a `<ref>` subtree and a keyword search alike. Hierarchy is derivable from `code` and `domain`.
- Whole-index and subtree calls emit in index order: domain (`areas`, `resources`, `projects`), then Johnny Decimal number ascending, an area immediately before its categories before their IDs. Keyword searches stay in `bm25` rank order. There is no ordering parameter and no ranking hook.

**Errors.** A `CLEAR_ERRORS` failure is written to **stdout** as `{"aardvark_json": 1, "error": {"kind": "…", "message": "…"}}` with a non-zero exit. Alfred reads stdout regardless of exit code, so the object always arrives; the exit code is a secondary signal for shell use. stderr continues to carry human prose. `kind` is a stable machine token, at least: `no_system`, `not_found`, `not_synced`, `value_error`, `domain_exhausted`, `category_exhausted`, `id_exhausted`. Both `cl_utils.main`'s `except CLEAR_ERRORS` branch and the "no aardvark system found" early exit fork on `--json`.

**`open --json`** suppresses the opening entirely and returns `{"result": {"label": …, "entity": { … }}}`. An entity synced to nothing is not an error under `--json`, unlike today's `open`.

**Mutating result**, one uniform shape across all seven mutating commands:

```json
{
  "aardvark_json": 1,
  "result": {
    "action": "add_id",
    "entity": { },
    "emoji_source": "offline",
    "corrections": [ { "from": "cardilogist", "to": "cardiologist" } ],
    "suggestions": [ { "token": "cardilogist", "index": 1, "suggested": "cardiologist" } ],
    "sync": "backgrounded",
    "template_used": "blank",
    "warnings": []
  }
}
```

- `emoji_source` is `offline`, `chosen` or `deferred`. It no longer has a `claude` value. Present only for `add_area`, `add_category`, `set_emoji`.
- `corrections` is the substitutions **applied** by the CLI path, `[]` when none were made or the check was skipped.
- `suggestions` is the field this specification adds, and it is not a synonym for `corrections`. It carries suggestions **offered and not yet accepted**, which is what the confirmation screen renders. `index` is the token position from `spell_check.tokenise`, so a row can substitute without re-parsing the title. Because `--json` never prompts and headless `add_*` skips the check, **`--json` must run suspect-token detection anyway** — otherwise `corrections` would be `[]` in exactly the case Alfred needs filled.
- `sync` is `backgrounded`, `waited` or `none`.
- `template_used` is `add_project` only.
- `warnings` is always present, `[]` when empty.
- `repair_emoji` returns `"entities": [ … ]` in place of `entity`, since it repairs many folders at once.
- For `archive`, `entity` describes the archived entity with `"archived": true` and its `archived_entities` URL snapshot.

**Sync result:** `{"result": {"action": "craft_sync", "summary": { … }, "drift": [ … ]}}`, where `summary` is the dict the command's `.get()` already returns, passed through unchanged, and `drift` is `db.drifted_mirrors(dbConn)` rendered so the workflow can report a failed mirror without a second call.

**Two implementation notes carried forward from ticket 03:**

1. Mirror URLs must be fetched in a **single read-only pass** — a new `db.entities_with_links(dbConn)` doing `LEFT JOIN`s across `areas`/`categories`/`ids`, the three `*_links` tables and `dropbox_links`. The per-entity `db.get_*_link` calls `open_craft` uses today would be N×4 queries per dump.
2. `emoji_source`, `corrections` and `suggestions` are information the `add_*` and `set_emoji` worker classes currently compute internally and discard; their `.get()` methods return only `(code, folderPath)` and friends. Those returns must widen, either as a longer tuple or as an attribute on the worker.

### `aardvark install_alfred`

Two separable jobs. Separating them is the decision the rest falls out of.

1. **Write the binary pointer.** Unconditional, every run, every machine — including a machine that installed the workflow by double-clicking an exported bundle. This is why the command is not author-only.
2. **Deploy the workflow.** Symlink `workflows/aardvark-jd` to the resolved `aardvark_jd/resources/alfred`, unless a workflow is already installed by another route.

**Symlink only. There is no `--copy`.** The package is installed editable on the authoring machine, so `importlib.resources.files("aardvark_jd")` points at the repo working tree here and at site-packages for a package user, through one code path with no branch. The author gets live editing; a package user gets a workflow that `pip install --upgrade` refreshes for free. A copy mode would exist only to go stale.

Re-run behaviour, by target state:

| State at `workflows/aardvark-jd` | Action |
| --- | --- |
| Nothing | Create the symlink, write the pointer, report both |
| Symlink already correct | Rewrite the pointer anyway; report the symlink unchanged |
| Symlink pointing elsewhere | Replace it — it is a link, nothing is lost |
| A real directory (imported bundle) | **Do not touch it.** Write the pointer, report that a copy-installed workflow is present and will not auto-update |

The pointer is rewritten every run because it is the thing most likely to be wrong and it costs nothing.

**Finding Alfred.** Read `~/Library/Application Support/Alfred/prefs.json` and take the `current` key. **Never fall back to a default path**: `~/Library/Application Support/Alfred/Alfred.alfredpreferences` exists on this machine but is vestigial, so a fallback would write where Alfred never looks and appear to succeed. Two distinguishable hard failures, both non-zero exit, neither a traceback:

1. No Alfred at all — no `Alfred.app`, no `prefs.json`. "Alfred is not installed."
2. Alfred present, but `prefs.json` is missing, unreadable, or lacks `current`. A real anomaly, reported differently and naming the file it tried.

**`--uninstall`** removes the symlink and the binary pointer, and touches nothing inside the repo. It is documented as *the* removal route — not because Alfred's own Delete Workflow is dangerous (it is not; it unlinks, leaving the target's inode and contents intact, and the item it puts in the Trash is itself still a symlink), but because it is the only route that also removes the pointer.

**Where it appears:** `commands.py` as `ADVANCED`, with a `Usage:` line and completers. `test_command_table_matches_docopt_usage` fails otherwise.

### Binary resolution

Three steps, in order, with nothing between them:

1. The **`AARDVARK_BINARY` workflow configuration variable** — a manual override, and it syncs with the preferences folder.
2. The **binary pointer** at `~/.config/aardvark/alfred-binary-path`.
3. **Hard failure**, as an error row.

Two steps are excluded on purpose. A **`PATH` probe** is out because Alfred's `PATH` under `/bin/zsh --no-rcs` is six documented entries carrying no conda, venv, pipx or uv binary — and the rare success is the dangerous one, silently running a different aardvark. Any **plausible-default fallback** is out for the same reason. `/usr/local/bin` is on Alfred's `PATH` but is `root:wheel 755` and verified not writable without sudo, so the symlink escape does not exist either.

The pointer file holds **one line: the absolute path to the `aardvark` console script**. Not `sys.executable` — there is no `__main__.py`, so the interpreter alone cannot launch anything, whereas the console script's shebang resolves its own interpreter with no environment activation. `install_alfred` derives it as `Path(sys.executable).parent / "aardvark"`.

It is plain text, not a YAML key, because reading YAML needs the interpreter the file exists to find. `~/.config/aardvark/` is fixed and literal, expanded per machine by the shell, created unconditionally on first run, and outside Dropbox — so it introduces no second discovery problem.

Three states, distinguished by `[ -x "$path" ]`: no file (never installed here), dead path (**shown in the row**, because a recorded-but-wrong path is the silent failure this design keeps guarding against), executable (proceed).

## The workflow's file layout

```
aardvark_jd/resources/alfred/
├── info.plist                  committed; Alfred's visual editor is the tool that edits it
├── prefs.plist                 gitignored; user configuration overrides only
└── scripts/
    ├── index.sh                the Script Filter entry point
    ├── handoff.sh              open -a "$TERMINAL_APP" "$path"
    └── …                       one file per Alfred script object
```

**Why inside the package.** A top-level `alfred/` would ship in neither the sdist nor the wheel: `MANIFEST.in` excludes everything outside `aardvark_jd/`, and `[tool.setuptools.package-data]` declares only `aardvark_jd = ["resources/**/*"]`. It also would not be importable, so locating it at runtime would fall back to `__file__` arithmetic that differs between a checkout and a wheel. Under `resources/` it ships free under the existing glob with no packaging changes, alongside `completions/`, `templates_src/` and `wordlists/`.

**`info.plist` is committed and is the source. Nothing is generated.** The evidence is one-sided: Alfred's own team commits `Workflow/info.plist` verbatim; opening a workflow in Alfred's editor writes nothing at all; the import-time configuration sheet writes to `prefs.plist`, not `info.plist`; and edit-time churn is confined to `uidata` canvas coordinates and `objects` array order, with no formatting noise and no injected absolute path.

**Every script object is an External Script (`type: 8`) referencing a real file. No body is ever inlined.** This is what makes committing the plist reviewable rather than committing a blob, and it makes the scripts diffable, lintable and — for the Python ones — importable from `aardvark_jd/alfred/` where pytest reaches them.

**Containing Alfred's rewrites.** `uidata` is left exactly as Alfred writes it: stripping it would make Alfred re-lay out the canvas and destroy the visual editor this decision is keeping. The `objects` array is sorted by `uid` by a pure normaliser, exposed as a **`make alfred-normalise` target run manually** — not a git hook, because this repo's hooks live unversioned in `.git/hooks/` and are invisible to anyone else, and because an automatic rewrite firing while Alfred holds the workflow open is a way to lose an edit. A `plutil -convert xml1` step would be a no-op: Alfred's output is already XML plist, tab-indented, keys strictly alphabetical.

**The editing loop, and there is no round trip:** Alfred follows the symlink completely and writes *through* it into the repo working tree, so there is no second copy. Edit in Alfred's editor → Alfred writes `info.plist` in the repo → `make alfred-normalise` → read `git diff` → commit. Scripts never enter that loop; they are edited in a normal editor and Alfred picks up changes on the next run.

The accepted constraint: **the visual editor is authoring-machine-only**. Anyone installing from PyPI or conda gets a read-only `info.plist` and editable script files.

**Configuration variables** live in the two-layer scheme Alfred documents: defaults in `info.plist`'s `userconfigurationconfig`, user overrides in the gitignored `prefs.plist`. Two are defined: `AARDVARK_TERMINAL_APP` (default empty) and `AARDVARK_BINARY` (default empty).

**Add to `.gitignore`:** `aardvark_jd/resources/alfred/prefs.plist`.

## The module layout inside the package

The rule, from the charting: the real logic lives where pytest reaches it, and the Alfred-invoked entry points stay a few lines each.

```
aardvark_jd/
├── json_output.py          the contract — a CLI feature, not a workflow one
└── alfred/
    ├── __init__.py
    ├── items.py            entity record → Alfred item dict; the lean payload shape
    ├── parse.py            "title, description" split; template and reference parsing
    ├── binary.py           the three-step binary resolution, pure over a path and an env
    ├── rows.py             suggestion → correction row; error kind → error row
    └── normalise.py        the info.plist `objects` sorter
```

`json_output.py` is **not** in `alfred/`. The contract is a CLI feature the workflow happens to consume; `alfred/` is for workflow-specific logic. It sits beside `doc_links.py` and `labels.py` as another shared renderer and holds `entity_record(row, links)`, `read_envelope(system, entities, archived=None)`, `result_envelope(action, …)`, `error_envelope(exc)` and the `kind`-token mapping — all pure functions over dicts and rows, no I/O.

**Spell-check detection stays in `aardvark_jd/spell_check.py`.** `tokenise` and `suggest` are already pure, already unit-tested and already reachable. What belongs in `alfred/rows.py` is only the code that turns a suggestion into rows.

**The entry points.** Each Alfred script object's file is a shell or Python stub of a few lines: resolve the binary, shell out, hand stdout to a pure function, print. No logic. `handoff.sh` is one line and has nothing to unit-test.

## The build order

Slices land in this order. Each is a test-first slice on its own branch under Gitflow.

**Slice 0 — the CLI foundation.** Invisible; no Alfred.

- `db.entities_with_links` bulk read.
- `aardvark_jd/json_output.py`: the envelope, the entity record, the error envelope, the `kind` mapping.
- `--json` on `fd` and `open`, including `fd --json --archived`.
- The `cl_utils.main` error forks.

**Slice 1 — the smallest thing worth installing.** This is the answer to "what is a usable workflow on its own", and it is the whole daily-driver half: the read commands are what gets typed twenty times a day, and none of the confirmation-screen machinery is needed to ship them.

- `aardvark_jd/alfred/binary.py` and the pointer file.
- `install_alfred` with its two jobs, four target states, `--uninstall` and two Alfred-absent failures.
- **Hand-verify that `objects` order is non-semantic** — shuffle the array and confirm the workflow still runs — *before* writing `normalise.py`. If order turns out to matter, drop the sort and fall back to a documented reviewer's rule ("ignore `uidata` and `objects` order"), which costs nothing.
- `normalise.py` and the `make alfred-normalise` target.
- `info.plist` with one Script Filter, `items.py` for the lean payload, the cache settings, Enter / ⌘ / ⌥ / ⌃, the destinations sub-list, `handoff.sh`, and the binary and version error rows.

At the end of slice 1 the workflow is installable and used daily. Everything after is judged against it.

**Ticket 16's spell-check tuning** ships here, as its own test-first CLI slice, **before slice 2**: prefer the longest distance-1 candidate rather than the shortest, and move the length floor from 6 to 5. It is a CLI change that alters terminal behaviour too, and doing it first means the correction rows are tuned the first time they are seen rather than retuned under a UI.

**Slice 2 — `add_id`, and the mutating machinery it carries.**

- The worker return widening and the mutating result envelope, including `suggestions`.
- `--json` running suspect-token detection despite never prompting.
- `parse.py`, `rows.py`.
- The reference pick, the argument step with its back row, the confirmation screen with correction rows and the teach modifier, and the success surface.

**Slice 3 — the rest of the mutating set.** `add_area` and `add_category` (plus the emoji step), `add_project` (plus the template pick, title only), `archive`, `set_emoji`.

**Slice 4 — sync and maintenance.** `--json` on `craft_sync`, `todoist_sync`, `gdrive_sync` and `repair_emoji`; their command rows; `repair_emoji`'s confirmation; the `drift` reporting.

## The test plan

Test-first throughout, per the global rules: write the failing test, confirm it fails for the right reason, write the minimal implementation, refactor with tests green.

**What is tested first, per slice.** The pure function before its caller, always. In slice 0 that is `entity_record` against a fixture row before `read_envelope`, and `read_envelope` before the `--json` flag is wired into docopt. In slice 1 it is `binary.py`'s three states before `install_alfred` touches a filesystem. In slice 2 it is `parse.py`'s comma split — including a title containing a comma, an omitted description, and a leading comma — before any Alfred object exists.

**The coverage bar is 80 per cent, applied per module, not only globally.** `json_output.py` and every module under `aardvark_jd/alfred/` each meet it on their own. A global average lets a well-tested `db.py` hide an untested new module, which is exactly what the "real logic lives where pytest reaches it" rule was written to prevent.

**How the exclusions are expressed**, since there is currently no `.coveragerc` and no `--cov` in the `Makefile`:

- `[tool.coverage.run] omit` in `pyproject.toml` for `aardvark_jd/resources/alfred/scripts/*`. Those are not importable modules in any case.
- `# pragma: no cover` on the `print(json.dumps(...))` glue lines in `cl_utils`.
- A **`make test-cov`** target, so the number is reproducible rather than remembered.

**Deliberately untested, each with its reason:**

1. **Alfred itself.** No AppleScript-driven end-to-end tests. They are slow, flaky, and they test Alfred rather than this code. Ruled out of scope by the map.
2. **The shell scripts under `resources/alfred/scripts/`.** A few lines of resolve-and-shell-out glue each; the logic they call is unit-tested.
3. **`info.plist`.** It is data, and Alfred is its parser.
4. **The filesystem effects of `install_alfred`.** Tested against `tmp_path` fakes for all four target states and both Alfred-absent failures — never against the live Alfred preferences folder.
5. **The `open -a` handoff.** Measured by hand against hostile fixtures (apostrophe, backslash, `$HOME`, backticks, `&&`, `|`, `"`, emoji, newline). One line, no logic left to unit-test.

Anything not on that list is expected to have a test.

## The documentation changes

**`README.md`** gains an "Alfred" section covering: what the workflow does, `aardvark install_alfred` to install it, the `av` keyword, the modifier table, the two configuration variables, and `install_alfred --uninstall` as the removal route. It states plainly that removing the workflow through Alfred's own UI is safe — it unlinks rather than deleting through the link — and that `--uninstall` is documented because it also removes the binary pointer.

It also carries the **fresh-machine ordering** paragraph: install the package, run `aardvark install_alfred`, then point the CLI at the tree. This is the last remaining piece of the map's "What happens on a fresh machine" fog. With workflow-directory sync ruled out of scope and binary resolution settled, what was left is an ordering note, not a decision, so it is folded in here rather than becoming a ticket.

**`docs/`** gains a page for the workflow, expanding the README section: the full command inventory, the flows, the error rows, and the configuration variables.

**The contributing notes** gain the edit-in-Alfred, `make alfred-normalise`, diff, commit loop, and state that the visual editor is authoring-machine-only.

**Where the contract's status is stated.** In three places, so a future reader cannot mistake it for API:

1. `json_output.py`'s module docstring — the first thing a maintainer opens.
2. The docs page for the workflow.
3. The `aardvark_json` version field's own documentation, which is the mechanism that makes reshaping it safe.

The wording: the JSON contract is **internal and unstable**. Nothing outside this repo may depend on it, and it may be reshaped without a deprecation cycle. The `aardvark_json` integer is bumped on any breaking change, and the workflow refuses a version it does not recognise with an actionable row.

**No ADR is needed for this specification.** The decisions inside it are recorded on the map with their evidence, and the two that were genuinely hard to reverse and surprising already have theirs: [ADR 0001](adr/0001-mutating-commands-hand-sync-to-a-detached-process.md) and [ADR 0002](adr/0002-drop-the-claude-emoji-suggester.md).

## Known open questions

Three things are deliberately unanswered, and none blocks the build.

- **A direct-keyword layer beside `av`.** Whether one or two daily-driver commands deserve their own top-level keywords, and which. The obvious names are taken, so any answer needs a prefix scheme. The only honest input is a week of real usage.
- **Universal Actions.** Acting on a Finder selection or a selected path from elsewhere in macOS — "file this into aardvark", "which JD code is this folder?". Plausibly the most valuable thing after the basics, but a different input model that cannot be specified until the keyword surface exists.
- **Frecency.** Ruled out for now on four grounds, not on caution: nothing records "recently used"; recording it would turn the read commands into mutating ones; any such signal would be per-machine and unrecoverable; and Alfred's own learning is actively wrong here because archive frees numbers for reuse. Revisit only with a week of real usage as evidence, as a fresh effort rather than a resumption.

One item is a build-time check rather than a question: **verify by hand that `info.plist`'s `objects` order is non-semantic** before writing the normaliser, per slice 1.
