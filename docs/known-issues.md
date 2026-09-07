# Known issues

Deferred defects and limitations that are understood but not yet fixed. Each entry
records what is wrong, why it was left, and what a fix needs.

## Craft sync repair has no cross-run convergence check

**Status:** open. Raised during the security review of the stale-document-ID repair
(branch `feature/craft-sync-id-repair`).

**What is wrong.** `craft_sync` repairs a stale document ID by creating a fresh
replacement document. One run replaces at most `_MAX_DOCUMENT_REPAIRS_PER_RUN`
(10) IDs before it aborts. The cap is per run: each sync builds a new `craft_sync`
instance and the counter resets. If the Craft connection is pointed at the wrong
space but still accepts writes (reads return 404, writes return 200), every run
re-repairs the same entities, creating 10 more empty documents and migrating 10
more `craft_links` rows into the wrong space. Over four runs: 10, 20, 30, 40
documents, with no convergence.

The repair path (`_is_blocks_404`) and `_delete_link_row_block` key only on a
structured 404. They do not apply the auth-first check that
`background_sync.classify_failure` now uses, so a 404 from a revoked or
misdirected connection is treated as ordinary drift.

**Why it was left.** The obvious brake — refuse to repair when the previous run
also failed — breaks legitimate multi-run recovery. If someone deletes 30 index
documents in Craft by hand, three runs of 10 repairs each is the intended
behaviour, and there is no clean sync in between to release the brake.

**What a fix needs.** Per-entity repair state, so a replacement that 404s again on
the next run can be distinguished from an entity that is simply next in a long
backlog. That is a schema change (a repair-generation column on `craft_links` or a
separate table) plus a migration. Telling "genuinely stale, keep going" from
"writes are not sticking, stop" is the core of it.

**Interim mitigation.** The abort is loud: it raises, records drift, and prints
`warning: craft sync failed` on every sync. A wrong-space connection surfaces
within one manual sync. The junk documents are empty and reversible.

## Remote error bodies are logged and persisted unsanitised

**Status:** open. Pre-existing; noted during the same review.

**What is wrong.** `CraftClient` builds its `CraftApiError` message from
`response.text` verbatim. `background_sync` logs that message and persists it whole
into `sync_drift.last_failure_reason` with no length cap and no control-character
stripping. A gateway that echoes the request could persist a `Bearer` token to
disk. `cl_utils` prints some sync failures to stderr without the `_printable`
sanitiser that `_report_sync_outcome` uses, so control characters in a remote body
can reach a real terminal.

**What a fix needs.** Truncate and sanitise the failure reason at the boundary,
preferring the structured `method` / `path` / `statusCode` fields now on
`CraftApiError` over the raw body. Route every stderr sync-failure print through
`_printable`. Add a length cap to anything derived from `responseText`.
