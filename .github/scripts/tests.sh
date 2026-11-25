#!/usr/bin/env bash
# Everything that has to pass before something is merged. Needs Python 3.12.
set -euo pipefail
cd "$(dirname "$0")/../.."

bash .github/scripts/prepare.sh
# Here no engine may be missing, and the list of clock rules has to be the pinned one.
export EVERY_ENGINE=yes
mkdir -p build/public
for test in readme told hold reader line days rules rows raw storm; do
  build/venv/bin/python -B "tests/test_$test.py" --verbose
done
build/venv/bin/python -B tests/looks.py | tee build/public/reader.md
[ -z "${GITHUB_STEP_SUMMARY:-}" ] || cat build/public/reader.md >> "$GITHUB_STEP_SUMMARY"

# A branch that must not be merged yet has this file: one line that says why, and until when. It comes last, so that everything
# else is seen. A link is not followed, because the log is public.
if [ -f HOLD ] && [ ! -L HOLD ]; then
  echo "Not to be merged yet: $(head -n 1 HOLD)"
  exit 1
elif [ -e HOLD ] || [ -L HOLD ]; then
  echo "Not to be merged yet: HOLD is not a plain file."
  exit 1
fi
