#!/bin/zsh --no-rcs
#
# `archive`, step 2: confirm - this frees the number and is one-way.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/archive_confirm.py" "${1:-}"
