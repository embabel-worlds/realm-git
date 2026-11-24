#!/bin/sh
# Ground truth for realm-git: every view, asked BY NAME of the appliance, reconciled to the row
# against git itself, run over a bare clone of a pinned commit of this very repository (the
# commit is immutable, so the figures cannot drift under the battery).
#
#   APPLIANCE=http://127.0.0.1:11043 AUTH=user:pass sh tests/verify.sh
#
# No keys: the repository is public. The appliance must be able to clone from github.com.
# The last line on success is exactly `ALL CHECKS PASS`; any drift exits nonzero.
set -e
cd "$(dirname "$0")/.."
exec python3 tests/verify.py "$@"
