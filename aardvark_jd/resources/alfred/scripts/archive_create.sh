#!/bin/zsh --no-rcs
#
# `archive`, step 3: move the folder to the archive and free its number.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_create_error "aardvark could not be found - run \`${AARDVARK_INSTALL_COMMAND}\` in a terminal"
fi

result="$("$aardvarkBinary" archive "${ref:-}" --json 2>/dev/null)"

if [ -z "$result" ]; then
    aardvark_emit_create_error "aardvark returned nothing"
fi

print -r -- "$result"
