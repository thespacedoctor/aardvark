#!/bin/zsh --no-rcs
#
# `add_id`, step 2: one free-text field taking `title, description`.
#
# Parse-only. Nothing is written here and nothing is looked up, so this
# step never touches the CLI - it only shows back what it read.

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/add_id_arguments.py" "${1:-}"
