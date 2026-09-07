#!/bin/zsh --no-rcs
#
# `set_emoji`, step 5: reach the renamed folder and its mirrors.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

print -r -- "${1:-}" | "$aardvarkInterpreter" "${scriptDir}/set_emoji_success.py"
