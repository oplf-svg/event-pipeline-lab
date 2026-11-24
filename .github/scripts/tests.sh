#!/usr/bin/env bash
# Everything that has to pass before something is merged. Needs Python 3.12 or newer and nothing else.
set -euo pipefail
cd "$(dirname "$0")/../.."

mkdir -p build/public
python3 -B tests/test_readme.py --verbose
python3 -B tests/test_reader.py --verbose
python3 -B tests/looks.py | tee build/public/reader.md
[ -z "${GITHUB_STEP_SUMMARY:-}" ] || cat build/public/reader.md >> "$GITHUB_STEP_SUMMARY"
