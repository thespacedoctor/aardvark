#!/bin/zsh --no-rcs
#
# The `av` Script Filter's entry point.
#
# Three jobs, in order: resolve the `aardvark` console script, fetch the
# whole index as JSON, and render it as Alfred items. Every failure is
# emitted as a single Alfred item carrying the diagnosis, because a Script
# Filter has no error channel - see `docs/alfred-workflow-spec.md`.

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

payload="$("$aardvarkBinary" fd --json 2>/dev/null)"

if [ -z "$payload" ]; then
    aardvark_emit_row "aardvark returned nothing" \
        "\`${aardvarkBinary} fd --json\` produced no output" "" "false"
fi

print -r -- "$payload" | "$aardvarkInterpreter" "${scriptDir}/index.py"
