#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

podman-compose down
podman-compose up -d --build

