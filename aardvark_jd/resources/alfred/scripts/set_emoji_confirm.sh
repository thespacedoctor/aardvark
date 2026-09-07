#!/bin/zsh --no-rcs
#
# `set_emoji`, step 3: confirm the rename.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/set_emoji_confirm.py" "${1:-}"
