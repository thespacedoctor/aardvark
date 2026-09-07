#!/bin/zsh --no-rcs
#
# `set_emoji`, step 4: rename the folder to carry the new emoji, and repoint the index.
#

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_create_error "aardvark could not be found - run \`${AARDVARK_INSTALL_COMMAND}\` in a terminal"
fi

result="$("$aardvarkBinary" set_emoji "${ref:-}" "${emoji:-}" --json 2>/dev/null)"

if [ -z "$result" ]; then
    aardvark_emit_create_error "aardvark returned nothing"
fi

print -r -- "$result"
