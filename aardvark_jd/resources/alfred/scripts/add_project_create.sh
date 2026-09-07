#!/bin/zsh --no-rcs
#
# `add_project`, step 5: create the project folder from the template, and the mirrors.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_create_error "aardvark could not be found - run \`${AARDVARK_INSTALL_COMMAND}\` in a terminal"
fi

result="$("$aardvarkBinary" add_project "${category:-}" "${title:-}" -t "${templateName:-blank}" --json 2>/dev/null)"

if [ -z "$result" ]; then
    aardvark_emit_create_error "aardvark returned nothing"
fi

print -r -- "$result"
