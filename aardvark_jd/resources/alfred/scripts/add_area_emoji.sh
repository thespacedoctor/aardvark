#!/bin/zsh --no-rcs
#
# `add_area`, step 3: pick the emoji (offline default, or a free-text search).
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/add_area_emoji.py" "${1:-}"
