# lacuna-stats-worker

Handles stats events sent from [lacuna](https://github.com/dyyniorg/lacuna) over HTTP POST by storing them into SQLite and rendering a PNG chart with matplotlib.

## Endpoints

- `POST /lacuna/stats` accepts one event
    - Requires `Authorization: Bearer <token>`
    - De-duplicates retried pushes based on `event_id`
- `GET /lacuna/chart.png` returns the rendered chart
- `GET /lacuna/healthz` returns `ok`

## Environment variables

| Variable | Required | Default | Description |
| - | - | - | - |
| `STATS_TOKEN` | yes | none | Bearer token for POST requests, min. 16 chars |
| `DATA_DIR` | no | `/data` | Directory for `stats.db` and `chart.png` |
| `PORT` | no | `8000` | HTTP listen port (for host) |
| `MAX_BODY_BYTES` | no | `1024` | Max. accepted request body size |
| `RENDER_CHECK_SECONDS` | no | `3600` (1h) | How often the render thread checks for work |
| `RENDER_MIN_INTERVAL_SECONDS` | no | `86400` (24h) | Min. time between data renders |

## Usage

```shell
lacuna --osm-user <USER> \
    --stats-url https://<DOMAIN>/lacuna/stats \
    --stats-token <STATS_TOKEN>
```

In addition to automated renders, a chart render can be forced with `podman compose exec lacuna-stats-worker python3 render.py --force`.

SQLite's backup API can be accessed with the following command:

```shell
podman compose exec lacuna-stats-worker python3 -c \
    "import sqlite3; src = sqlite3.connect('/data/stats.db'); dst = sqlite3.connect('/data/stats_bkp.db'); src.backup(dst)"
podman compose cp lacuna-stats-worker:/data/stats_bkp.db ./stats_bkp.db
```

