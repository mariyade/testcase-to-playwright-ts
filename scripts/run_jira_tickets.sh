#!/usr/bin/env bash
set -euo pipefail

TICKETS_FILE="${1:-test_specs/jira/tickets.txt}"
JIRA_BASE_URL="${JIRA_BASE_URL:-}"

if [[ $# -gt 0 && -f "$1" ]]; then
  shift
else
  TICKETS_FILE="test_specs/jira/tickets.txt"
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  ticket="${line%%#*}"
  ticket="$(echo "$ticket" | xargs)"

  if [[ -z "$ticket" ]]; then
    continue
  fi

  if [[ "$ticket" == http://* || "$ticket" == https://* || -f "$ticket" ]]; then
    jira_source="$ticket"
  else
    if [[ -z "$JIRA_BASE_URL" ]]; then
      echo "JIRA_BASE_URL is required for Jira keys like $ticket"
      echo "Example: export JIRA_BASE_URL=https://your-domain.atlassian.net/rest/api/3/issue"
      exit 1
    fi
    jira_source="${JIRA_BASE_URL%/}/$ticket"
  fi

  filename="$(basename "$ticket")"
  filename="${filename%.json}"
  filename="${filename//[^A-Za-z0-9_-]/_}"

  echo "Running Jira ticket: $ticket"
  .venv/bin/python -m agent.cli \
    --jira "$jira_source" \
    --save-spec "artifacts/stage1/${filename}_spec.json" \
    "$@"
done < "$TICKETS_FILE"
