#!/bin/zsh --no-rcs
#
# `add_id`, step 1: pick the category the new ID hangs off.
#
# The same `fd --json` envelope the main list is built from, filtered to
# the entity type that can be a parent. One shell-out, no new contract.

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

print -r -- "$payload" | "$aardvarkInterpreter" "${scriptDir}/add_id_reference.py"
