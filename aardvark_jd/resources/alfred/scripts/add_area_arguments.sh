#!/bin/zsh --no-rcs
#
# `add_area`, step 2: `title, description`, split on the first comma.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/add_area_arguments.py" "${1:-}"
