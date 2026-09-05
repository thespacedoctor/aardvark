#!/bin/zsh --no-rcs
#
# Teach the learned vocabulary a word the spell-checker flagged wrongly.
#
# Its own explicit modifier rather than arriving free with a decline. On
# the terminal, declining a suggestion teaches the word; here declining is
# the default path, so that rule would teach a word on every reflexive
# Return. A deliberate divergence - see `docs/source/alfred.md`.

set -u

scriptDir="${0:A:h}"
source "${scriptDir}/_resolve.sh"

if ! aardvark_resolve; then
    print -r -- "aardvark could not be found - run \`${AARDVARK_INSTALL_COMMAND}\` in a terminal"
    exit 1
fi

"$aardvarkInterpreter" "${scriptDir}/teach.py" "${1:-}"
