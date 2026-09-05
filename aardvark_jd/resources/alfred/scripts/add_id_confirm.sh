#!/bin/zsh --no-rcs
#
# `add_id`, step 3: the confirmation screen.
#
# The final Return of the argument step does not commit; this screen does.
# Accepting a correction row re-renders this same screen rather than
# committing, so Return always means create.
#
# Alfred exports the originating item's variables into this script's
# environment, so `title`, `description` and `root_path` arrive populated.

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_resolution_failure
fi

"$aardvarkInterpreter" "${scriptDir}/add_id_confirm.py"
