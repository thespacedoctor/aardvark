# The Alfred workflow

This page covers the Alfred 5 workflow that ships with aardvark on macOS: what it puts in front of you, how it is installed, what it can be configured with, and what it does when something is wrong. It is for anyone driving aardvark from the keyboard rather than from a terminal.

The workflow is a **surface**, not a mirror: it reads the index and invokes commands, holds no copy of your tree, and cannot drift.

## What it installs

```bash
aardvark install_alfred
```

Two separate jobs, and the command always does the first:

1. **It records where `aardvark` lives on this Mac**, in a one-line plain-text file at `~/.config/aardvark/alfred-binary-path`. Alfred runs scripts under `/bin/zsh --no-rcs` with a `PATH` of six fixed system entries - none of which carries a conda, venv, pipx or uv binary - so the workflow cannot find aardvark by searching. It has to be told. The file records the `aardvark` console script rather than the Python interpreter, because the console script's shebang resolves its own interpreter with no environment activation.
2. **It links the packaged workflow into Alfred**, as a symlink at `<your Alfred preferences>/workflows/aardvark-jd`. Because it is a link rather than a copy, `pip install --upgrade aardvark-jd` refreshes the workflow for free.

Re-running the command is safe at any time. It rewrites the recorded path every run, replaces a symlink that points somewhere else, and leaves a workflow you installed some other way - by double-clicking an exported `.alfredworkflow` - completely alone.

Alfred's preferences folder can live anywhere the user has put it, so the command reads Alfred's own `prefs.json` for its location and **never falls back to a default path**. A fallback would write where Alfred never looks and appear to have succeeded.

## Using it

Type `av` in Alfred. One Script Filter fetches the whole index and Alfred filters it as you type, matching against each entity's Johnny Decimal code, title, folder-path segments and description, in any word order.

On a result:

| Key | Action |
| --- | --- |
| ↩ | Open every mirror the entity is synced to, the same as `aardvark open` |
| ⌘ | **Reveal** the folder in Finder |
| ⌥ | **Handoff**: open a terminal tab at the folder |
| ⌃ | Show the **destinations sub-list**: Craft, Todoist, Google Drive and Dropbox |

⇧ is left alone, because Alfred binds it to Quick Look.

The four mirrors are a sub-list rather than four more modifier chords for one reason: a sub-list can show you a mirror that is **not** synced yet and offer to run that mirror's sync on ↩. An unbound chord could only do nothing.

## Creating an ID

The same `av` list carries a row per mutating command, below the entities. `add_id` is the first of them. Pressing ↩ on it starts a flow with five steps:

1. **Choose a category.** The categories from the same index, filtered.
2. **Type the title and description** into one field, as `title, description`. The split is on the **first comma only**; everything after it is the description, commas and all. A title that contains a comma loses the fragment after the first one to the description, and step 3 shows you that before anything is written. With no comma, the description is empty.
3. **Confirm.** ↩ here creates the folder; Escape backs out. **Create as typed** is the first row and always what ↩ does.
4. **It is created**, and the mirroring is backgrounded, so Alfred returns immediately.
5. **The success surface** offers the new folder straight away: reveal, handoff, and each mirror. Use it rather than searching for what you just made - the `av` list caches the index for an hour and refreshes in the background, so a brand-new folder shows up there one invocation late at worst.

The argument step's first row goes back to the category pick while the field is empty. Once you have typed something the parse takes the top row, so ↩ always means "carry on"; the way back stays visible below it.

### Spelling corrections

If the title contains a word the spell-checker does not recognise, the confirmation screen grows one extra row per suspect word, below **Create as typed**. Accepting one re-renders the confirmation rather than creating anything, so you can accept several, and ↩ still means create.

**This differs from the terminal on purpose.** At the terminal, declining a suggestion teaches aardvark that the word is real, so it stops asking. Here, declining is what ↩ already does, so that rule would teach a word every time you pressed Return without reading. Teaching therefore needs its own key: **⌘↩ on a correction row** records the word, and it is never flagged again.

## Configuration

Two settings, under Alfred's **Configure Workflow…**:

- `AARDVARK_TERMINAL_APP` - the app the ⌥ handoff opens a tab in. Left empty, the workflow uses iTerm when `/Applications/iTerm.app` exists and `Terminal.app` otherwise, so the chain always terminates.
- `AARDVARK_BINARY` - an explicit path to the `aardvark` command, overriding the recorded one. Left empty, the recorded path is used.

Alfred stores changed values in a `prefs.plist` beside the workflow, which is gitignored; the defaults live in `info.plist`, which is committed. That two-layer split is why re-running `install_alfred` never stamps on a setting you changed.

## When something is wrong

A Script Filter has no error channel, so every failure arrives as a single row carrying the diagnosis. Where the fix is obvious, ↩ on that row does it.

| What you see | What ↩ does |
| --- | --- |
| "aardvark has not been set up on this Mac" | Copies `aardvark install_alfred` to the clipboard |
| "aardvark is not at `<path>`" - the recorded path is shown | Copies `aardvark install_alfred` to the clipboard |
| "This workflow is out of step with the installed aardvark" | Copies `aardvark install_alfred` to the clipboard |
| A version-drift warning naming both versions | Nothing; it is a warning, never a blocker |
| "Not synced to Craft" and its three siblings | Runs that mirror's sync |
| Any other message from the CLI | Nothing; the message is the whole row |

The dead-path row deliberately shows the path it tried. A recorded-but-wrong path is the one silent failure this design guards against throughout.

The failure rows copy the command rather than typing it into a terminal for you. `install_alfred` is an advanced command and does not appear in `aardvark -h`, which is acceptable only because these rows hand you the exact string.

## Removing it

```bash
aardvark install_alfred --uninstall
```

This removes the symlink and the recorded path, and touches nothing inside the package.

Removing the workflow through Alfred's own interface is also safe. Alfred unlinks it, leaving the linked directory's contents untouched, and what it puts in the Trash is the symlink itself. `--uninstall` is documented as *the* route only because it is the one that also removes the recorded path.

## The JSON contract

The workflow talks to the CLI through a `--json` flag on `fd` and `open`, which prints a versioned object instead of prose.

**This contract is internal and unstable.** Nothing outside this repository may depend on it, and it may be reshaped without a deprecation cycle. The `aardvark_json` integer at the top of every response is bumped on any breaking change, and the workflow refuses a version it does not recognise with an actionable row rather than misreading it.

```bash
aardvark fd --json
aardvark fd --json --archived
aardvark open ~/some/folder --json
```

Errors are part of the contract: a failure prints `{"aardvark_json": 1, "error": {"kind": …, "message": …}}` on **stdout** and exits non-zero, because Alfred reads stdout regardless of the exit code. `--archived` only shapes that output, so using it without `--json` is an error rather than a silent no-op.

## Editing the workflow

`info.plist` is committed, and Alfred's own visual editor is the tool that edits it. Alfred follows the symlink and writes straight into the working tree, so there is no second copy and no round trip:

1. Edit the workflow in Alfred.
2. Run `make alfred-normalise`, which sorts the `objects` array by `uid`. Alfred reorders that array on every edit, and sorting it keeps the change out of the diff.
3. Read `git diff` and commit.

Script files are edited in a normal editor; Alfred picks up changes on the next run and they never enter that loop. `uidata` is left exactly as Alfred writes it - stripping the canvas coordinates would make Alfred re-lay out the workflow and destroy the editor this approach is keeping.

The visual editor is authoring-machine-only. Anyone installing from PyPI or conda gets a read-only `info.plist` and editable script files.
