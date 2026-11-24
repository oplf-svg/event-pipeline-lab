#!/usr/bin/env bash
# Proves that the tests can fail: one mistake at a time, see tests/wrong.py. "2/4" is the second of four parts.
set -euo pipefail
cd "$(dirname "$0")/../.."

python3 -B tests/wrong.py "$@"
