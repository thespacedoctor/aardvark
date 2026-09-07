#!/bin/zsh --no-rcs
#
# `add_category`, step 1: pick the parent area.
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

print -r -- "$payload" | "$aardvarkInterpreter" "${scriptDir}/add_category_reference.py"
