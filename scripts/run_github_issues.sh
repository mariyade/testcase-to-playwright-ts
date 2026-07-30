#!/usr/bin/env bash
set -euo pipefail

ISSUES_FILE="${1:-test_specs/github/issues.txt}"

if [[ $# -gt 0 && -f "$1" ]]; then
  shift
else
  ISSUES_FILE="test_specs/github/issues.txt"
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  issue="${line%%#*}"
  issue="$(echo "$issue" | xargs)"

  if [[ -z "$issue" ]]; then
    continue
  fi

  filename="$(basename "$issue")"
  filename="${filename%.json}"
  filename="${filename//[^A-Za-z0-9_-]/_}"

  echo "Running GitHub issue: $issue"
  .venv/bin/python -m agent.cli \
    --github "$issue" \
    --save-spec "artifacts/stage1/${filename}_spec.json" \
    "$@"
done < "$ISSUES_FILE"
