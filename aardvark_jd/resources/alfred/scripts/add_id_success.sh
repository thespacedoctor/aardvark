#!/bin/zsh --no-rcs
#
# `add_id`, step 5: what to do with the thing that was just created.
#
# Not decoration - this is the whole recall story. The Script Filter's
# cached index is one invocation behind at this point, and this surface
# reaches the new entity without waiting for it.

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

print -r -- "${1:-}" | "$aardvarkInterpreter" "${scriptDir}/add_id_success.py"
