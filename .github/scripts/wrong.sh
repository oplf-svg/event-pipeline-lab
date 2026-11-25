#!/usr/bin/env bash
# Proves that the tests can fail: one mistake at a time, see tests/wrong.py and tests/wrong_rules.py. "2/4" is the second of four parts.
set -euo pipefail
cd "$(dirname "$0")/../.."

bash .github/scripts/prepare.sh
export EVERY_ENGINE=yes
build/venv/bin/python -B tests/wrong.py "$@"
build/venv/bin/python -B tests/wrong_rules.py "$@"
