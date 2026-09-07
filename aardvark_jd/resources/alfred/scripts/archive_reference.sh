#!/bin/zsh --no-rcs
#
# `archive`, step 1: pick the area, category or ID to retire.
#

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

print -r -- "$payload" | "$aardvarkInterpreter" "${scriptDir}/archive_reference.py"
