#!/bin/zsh --no-rcs
#
# `add_category`, step 2: `title, description`, split on the first comma.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/add_category_arguments.py" "${1:-}"
