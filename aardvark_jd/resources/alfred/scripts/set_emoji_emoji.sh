#!/bin/zsh --no-rcs
#
# `set_emoji`, step 2: pick the new emoji.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/set_emoji_emoji.py" "${1:-}"
