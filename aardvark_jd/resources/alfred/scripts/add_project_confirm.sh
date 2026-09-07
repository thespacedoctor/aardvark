#!/bin/zsh --no-rcs
#
# `add_project`, step 4: the confirmation screen.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/add_project_confirm.py" "${1:-}"
