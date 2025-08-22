#!/usr/bin/env bash
set -euo pipefail
# Safe length check (no secret printed)
if [ -z "${ADMIN_TOKEN:-}" ]; then
  echo "ADMIN_TOKEN is unset or empty"
  exit 1
fi
printf %s "$ADMIN_TOKEN" | wc -c
