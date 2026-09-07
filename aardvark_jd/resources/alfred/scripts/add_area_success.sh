#!/bin/zsh --no-rcs
#
# `add_area`, step 6: what to do with the area that was just created.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

print -r -- "${1:-}" | "$aardvarkInterpreter" "${scriptDir}/add_area_success.py"
