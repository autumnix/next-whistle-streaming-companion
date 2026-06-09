# Next Whistle Streaming Companion

A control service that automates the live-production workflow for roller derby broadcasts — collapsing the dozen manual actions an operator performs every jam (scene switching, instant replay, camera presets, scoreboard overlays) into single-button calls.

Built to run a real multi-camera derby stream: a single operator can keep up with the pace of play instead of fighting OBS, PTZ cameras, and the scoreboard separately.

---

## What it does

During a bout, the operator triggers high-level **workflows** (typically from a Stream Deck) and the service coordinates every downstream system:

- **`save-and-arm`** — saves the OBS replay buffer and arms the most recent clip for playback.
- **`jam-reset`** — consumes the pending replay metadata, cuts back to the primary camera, and returns the PTZ heads to their jam-start presets.
- **`jam-reset-and-play`** — same as above, but rolls the armed replay before resetting.

Around those core workflows it also handles:

- **OBS control** over the obs-websocket protocol — scene switching, replay-buffer capture, timed replay playback with configurable length/padding, and transitions.
- **PTZ camera control** over HTTP — recall presets per camera or across all cameras.
- **Scoreboard integration** — a resilient websocket listener against a CRG scoreboard that tracks live game state (jam number, score, period) used to tag clips and drive overlays.
- **Overlay management** — show / hide / toggle configured OBS overlay groups (e.g. stat lower-thirds).
- **Clip history** — every armed replay is persisted to SQLite with its game context, queryable via the API.
- **Health monitoring** — a background monitor polls each integration so the dashboard can surface connection state at a glance.
- **Web dashboard** — a lightweight status + config UI served by the same process.

---

## Architecture

The service is a single FastAPI application wired together by an explicit app factory (`create_app`), organized into clear layers:

```
src/nwsc/
├── __main__.py          # CLI entry point (python -m nwsc)
├── app.py               # FastAPI app factory + dependency wiring + lifespan
├── config.py            # Pydantic-settings config model, loaded from YAML
├── logging.py           # structlog setup
├── dependencies.py      # FastAPI dependency providers
├── domain/              # Business logic, framework-agnostic
│   ├── bout.py          #   live game state
│   ├── clip.py          #   replay/clip lifecycle
│   ├── jam_cycle.py     #   the multi-step jam workflows
│   └── overlay.py       #   overlay group operations
├── integrations/        # External-system clients (one package each)
│   ├── obs/             #   obs-websocket client
│   ├── ptz/             #   PTZ camera HTTP client
│   └── scoreboard/      #   CRG scoreboard websocket client
├── routers/             # HTTP surface, one router per concern
├── services/            # Cross-cutting services
│   ├── replay_file.py   #   newest-file discovery + write-stabilization
│   └── health_monitor.py
├── db/                  # SQLite engine, models, repository
└── dashboard/           # Static assets + Jinja templates
```

Design notes:

- **Layered separation.** `domain/` holds the orchestration logic and never imports FastAPI; `integrations/` isolates each external protocol behind a small client; `routers/` is a thin HTTP surface. This keeps the jam-cycle logic testable without standing up OBS, cameras, or a scoreboard.
- **Single composition root.** All clients, services, and the database are constructed once in `create_app` and shared via `app.state`, with FastAPI dependencies pulling them in per request.
- **Resilient by default.** The scoreboard listener and health monitor start best-effort and reconnect on their own, so a flaky camera or a scoreboard reboot mid-bout never takes the service down.
- **Replay file stabilization.** New recordings are detected by scanning dated (`YYYY-MM-DD`) folders for the newest file, then polling its size until writes settle — avoiding the classic race of grabbing a clip that OBS is still flushing to disk.

---

## API surface

Selected endpoints (most accept both `GET` and `POST` so they can be bound directly to Stream Deck buttons):

| Method | Path | Purpose |
|--------|------|---------|
| `*` | `/workflow/save-and-arm` | Save replay buffer and arm latest clip |
| `*` | `/workflow/jam-reset` | Reset to cam 1, recall PTZ presets |
| `*` | `/workflow/jam-reset-and-play` | Play armed replay, then reset |
| `*` | `/obs/go-cam1`, `/obs/go-cam2` | Cut to a camera scene |
| `*` | `/highlight/arm-latest` | Arm the newest replay file |
| `GET` | `/highlight/history` | Clip history with game context |
| `*` | `/ptz/cam/{cam_id}/preset/{preset}` | Recall a PTZ preset |
| `*` | `/ptz/all/preset/{preset}` | Recall a preset on all cameras |
| `*` | `/overlay/{group}/toggle` | Show / hide an overlay group |
| `GET` | `/game/current` | Current live game state |
| `GET` | `/health`, `/status` | Integration health + service status |
| `GET` | `/dashboard/` | Status & config web UI |

Interactive API docs are available at `/docs` when the service is running.

---

## Tech stack

Python 3.11+ · FastAPI · Uvicorn · Pydantic v2 / pydantic-settings · SQLite (aiosqlite) · obsws-python · websockets · httpx · Jinja2 · structlog. Tested with pytest / pytest-asyncio; linted with ruff.

---

## Getting started

### Requirements

- Python 3.11+
- OBS with the obs-websocket server enabled
- One or more PTZ cameras with an HTTP preset-recall endpoint *(optional)*
- A CRG scoreboard reachable over websocket *(optional)*

### Install

```bash
git clone https://github.com/autumnix/next-whistle-streaming-companion.git
cd next-whistle-streaming-companion
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Configure

```bash
cp config.example.yaml config.yaml
```

`config.yaml` is gitignored and never committed — it stays local. Edit it for your rig:

#### OBS (`obs`)

Enable the obs-websocket server in OBS under **Tools → WebSocket Server Settings**. Check "Enable WebSocket Server", set a port (default `4455`), and set a password. Copy those values into `config.yaml`:

```yaml
obs:
  host: "127.0.0.1"   # OBS is on the same machine as this service
  port: 4455
  password: "your-obs-websocket-password"
```

Update the `scenes` block to match your actual OBS scene names:

```yaml
  scenes:
    cam1: "LIVE - CAM 1"
    cam2: "LIVE - CAM 2"
    replay: "REPLAY"
    safe: "BUMPER"
```

#### PTZ cameras (`ptz`)

Set each camera's hostname or IP. Local DNS names (e.g. `cam1.lan`, `cam2.lan`) are strongly recommended over fixed IPs or DHCP — if you swap a camera or move to a different venue, you can reassign the DNS entry in your router to point to the new host without touching `config.yaml` or any scripts:

```yaml
ptz:
  cameras:
    cam1:
      host: "cam1.lan"
    cam2:
      host: "cam2.lan"
```

#### Scoreboard (`scoreboard`)

Point this at your CRG scoreboard's websocket. Same reasoning applies: use a local DNS name so you can reassign it to a different scoreboard laptop at a new venue without changing any config:

```yaml
scoreboard:
  url: "ws://scoreboard.lan:8000/WS/"
```

See `config.example.yaml` for all available options and their defaults.

### Run

```bash
./run.sh
# or:
python -m nwsc --config config.yaml
# overrides:
python -m nwsc --config config.yaml --host 0.0.0.0 --port 8787
```

Then open the dashboard at `http://localhost:8787/dashboard/`.

---

## Game-day operation

The service is designed to be started once and left running for the whole bout. A typical run:

### Before the bout (one-time setup)

1. **Populate your config.** This service is venue- and rig-specific — every operator needs to fill in `config.yaml` for their own setup before the first run. At minimum set: OBS connection + scene names (`obs`), each camera's host (`ptz.cameras`), and the scoreboard URL (`scoreboard`). Copy `config.example.yaml` to `config.yaml` and edit it; see the [Configure](#configure) section above.
2. **Save the jam-start preset on every camera.** The `jam-reset` workflows recall a single preset on all cameras to return them to the default jam-start framing (typically the wide track shot). Using your camera's controls, frame each camera the way you want it to start every jam and **save that as the jam-start preset on each one**. By default the service recalls preset `0` (configurable via `ptz.jam_start_preset`) — note some camera UIs label this slot "Preset 1", so save to whichever slot maps to the configured number. If you skip this, every other workflow still works; the cameras just won't auto-reframe on jam reset.
3. **Start OBS** with the obs-websocket server enabled, and confirm your scene names match the `obs.scenes` block in your config.

### Starting the service

```bash
./run.sh
```

Leave this running for the duration of the bout. Open `http://localhost:8787/dashboard/` to confirm OBS, the cameras, and the scoreboard all show healthy.

### During the bout

Drive everything from your Stream Deck (or any HTTP caller) using the high-level workflows — you should rarely need to touch OBS directly:

- **End of jam:** `save-and-arm` to capture the replay buffer.
- **Start of next jam:** `jam-reset` (cut back to cam 1 + recall presets) or `jam-reset-and-play` (roll the replay first, then reset).
- Use `go-cam1` / `go-cam2` and the overlay toggles for manual adjustments as needed.

### After the bout

Stop the service with `Ctrl-C`. Clip history is persisted in the SQLite database and remains queryable via `/highlight/history` on the next run.

---

## Testing

```bash
pytest
```

Integration tests spin up the app and exercise the game and health APIs against fixtures, so they run without any live OBS / camera / scoreboard hardware.

---

## Stream Deck

The workflow and OBS endpoints are intentionally `GET`-friendly so a Stream Deck (via the System: Website action or a multi-action) can call them directly over HTTP. A companion Stream Deck profile lives in the [`next-whistle-stream-deck`](https://github.com/autumnix/next-whistle-stream-deck) repo.

---

## Related tools

**[obs-tally](https://github.com/autumnix/obs-tally)** — a tally light system for OBS that draws program/preview borders on fullscreen projectors so operators and talent know which camera is live. This companion is designed to work seamlessly with it: whenever a scene change occurs, the studio mode preview is automatically set to the off-air camera, keeping obs-tally's program and preview signals correct without any extra operator input.

---

## Status

A personal project that runs in production for live roller derby broadcasts. Interfaces are stable enough for daily use; versioning starts at `0.1.0` and the API may still change.

## License

_No license file is currently included — add one (e.g. MIT) before reuse._
