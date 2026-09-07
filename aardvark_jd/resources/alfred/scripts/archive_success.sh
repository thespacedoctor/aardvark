#!/bin/zsh --no-rcs
#
# `archive`, step 4: reach the archived folder and its mirrors.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

print -r -- "${1:-}" | "$aardvarkInterpreter" "${scriptDir}/archive_success.py"
