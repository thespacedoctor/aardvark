#!/bin/zsh --no-rcs
#
# `add_category`, step 4: the confirmation screen.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/add_category_confirm.py" "${1:-}"
