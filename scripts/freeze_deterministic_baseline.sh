#!/usr/bin/env bash
set -euo pipefail
OUT="${1:-results/acp28_opbias_final}"
FREEZE="$OUT/freeze"
mkdir -p "$FREEZE"
ngspice --version > "$FREEZE/ngspice_version.txt" 2>&1 || true
python --version > "$FREEZE/python_version.txt" 2>&1
python -m pip freeze > "$FREEZE/pip_freeze.txt"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git rev-parse HEAD > "$FREEZE/git_commit.txt" 2>/dev/null || true
  git status --short > "$FREEZE/git_status.txt" 2>/dev/null || true
  git diff > "$FREEZE/code_changes.patch" 2>/dev/null || true
else
  echo "RECONSTRUCTED_ARCHIVE_NO_GIT_HISTORY" > "$FREEZE/git_commit.txt"
fi
find "$OUT" -type f ! -path "$FREEZE/sha256.txt" -print0 | sort -z | xargs -0 sha256sum > "$FREEZE/sha256.txt"
echo "DETERMINISTIC FREEZE COMPLETE: $FREEZE"
