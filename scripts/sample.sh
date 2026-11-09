#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

SAMPLE_FILE="${SAMPLE_FILE:-tests/sample.jsonl}"
SAMPLE_CHART="${SAMPLE_CHART:-data/sample/chart.png}"
SAMPLE_TOKEN="${SAMPLE_TOKEN:-sample-token-123456}"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ ! -f "$SAMPLE_FILE" ]]; then
    echo "[!] error: sample data not found $SAMPLE_FILE"
    exit 1
fi

DATA_DIR="$TMP_DIR" STATS_TOKEN="$SAMPLE_TOKEN" uv run python - "$SAMPLE_FILE" <<'PY'
import sys
from pathlib import Path

import store

settings = store.Settings.from_env()
store.initialize_database(settings)

count = 0
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.strip():
        store.insert_event(settings, store.validate_event(line.encode("utf-8")))
        count += 1

print(f"[+] loaded {count} sample events")
PY

DATA_DIR="$TMP_DIR" STATS_TOKEN="$SAMPLE_TOKEN" uv run python render.py --force

mkdir -p "$(dirname "$SAMPLE_CHART")"
cp "$TMP_DIR/chart.png" "$SAMPLE_CHART"
echo "[+] sample chart: $SAMPLE_CHART"

