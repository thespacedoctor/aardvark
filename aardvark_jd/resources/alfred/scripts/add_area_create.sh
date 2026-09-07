#!/bin/zsh --no-rcs
#
# `add_area`, step 5: create the area, its system folder and the mirrors.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_create_error "aardvark could not be found - run \`${AARDVARK_INSTALL_COMMAND}\` in a terminal"
fi

if [ -n "${emoji:-}" ]; then
    result="$("$aardvarkBinary" add_area "${domainLetter:-}" "${title:-}" "${description:-}" -e "${emoji}" --json 2>/dev/null)"
else
    result="$("$aardvarkBinary" add_area "${domainLetter:-}" "${title:-}" "${description:-}" --json 2>/dev/null)"
fi

if [ -z "$result" ]; then
    aardvark_emit_create_error "aardvark returned nothing"
fi

print -r -- "$result"
