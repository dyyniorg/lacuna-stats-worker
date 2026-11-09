#!/usr/bin/env bash

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

status=0

uv run basedpyright *.py || status=1
uv run black *.py || status=1
uv run pytest || status=1

exit "$status"

