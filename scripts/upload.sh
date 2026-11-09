#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

if [[ $# -ne 1 ]]; then
    echo "[!] error: usage $0 HOST:PATH/"
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "[!] error: .env not found"
    exit 1
fi

rsync -avz \
    .containerignore \
    .env \
    Containerfile \
    compose.yaml \
    pyproject.toml \
    render.py \
    server.py \
    store.py \
    uv.lock \
    "$1"
