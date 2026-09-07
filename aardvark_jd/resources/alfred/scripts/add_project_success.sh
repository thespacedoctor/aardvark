#!/bin/zsh --no-rcs
#
# `add_project`, step 6: what to do with the new project.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

print -r -- "${1:-}" | "$aardvarkInterpreter" "${scriptDir}/add_project_success.py"
