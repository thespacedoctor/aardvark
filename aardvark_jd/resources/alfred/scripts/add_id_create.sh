#!/bin/zsh --no-rcs
#
# `add_id`, step 4: create the folder, the index row and the mirrors.
#
# Headless throughout: `--json` for the contract and `-w` left off so the
# mirroring is backgrounded, which is what makes Alfred faster than the
# terminal. Alfred exports `category`, `title` and `description`.

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    aardvark_emit_create_error "aardvark could not be found - run \`${AARDVARK_INSTALL_COMMAND}\` in a terminal"
fi

# THE `--json` FAILURE OBJECT ARRIVES ON STDOUT WITH A NON-ZERO EXIT, SO
# IT IS PASSED ON RATHER THAN TREATED AS "NOTHING CAME BACK".
result="$("$aardvarkBinary" add_id "${category:-}" "${title:-}" "${description:-}" --json 2>/dev/null)"

if [ -z "$result" ]; then
    aardvark_emit_create_error "aardvark returned nothing"
fi

print -r -- "$result"
