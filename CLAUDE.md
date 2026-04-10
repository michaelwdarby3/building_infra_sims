# CLAUDE.md

Building infrastructure protocol simulators — BACnet/IP and Modbus TCP device emulation for integration testing with Skycentrics Super Skybox gateways.

## Commands

```bash
# Setup
pip install -e ".[dev]"

# Run individual devices
bsim bacnet run --profile profiles/bacnet/generic_ahu.yaml --device-id 1001
bsim modbus run --profile profiles/modbus/generic_power_meter.yaml --port 10502

# Run multi-device scenarios
bsim scenario profiles/scenarios/small_office.yaml
bsim scenario profiles/scenarios/small_office.yaml --setup-skybox   # auto-register with gateway

# End-to-end verification (starts sims, registers with gateway, checks data flow)
bsim verify profiles/scenarios/small_office.yaml --settle-time 30

# Web dashboard (device management UI + per-device REST API)
bsim dashboard                                          # empty, add devices interactively
bsim dashboard profiles/scenarios/medium_office.yaml    # pre-load a scenario
bsim dashboard small_office.yaml --setup-skybox         # pre-load + register with gateway

# List available profiles/scenarios
bsim bacnet list-profiles
bsim modbus list-profiles
bsim list-scenarios

# Gateway
bsim skybox status        # check gateway connectivity
bsim teardown-skybox      # remove all simulated connections from gateway

# Docker
docker compose up         # runs one BACnet + one Modbus device

# Tests
pytest                    # all tests (uses pytest-asyncio, auto mode)
pytest tests/test_profiles.py
```

## Architecture

```
src/building_infra_sims/
  cli.py            — Typer CLI with subcommands: bacnet, modbus, skybox, scenario, dashboard, verify
  config.py         — Pydantic Settings (env prefix BSIM_), gateway/network/path config
  bacnet/           — BACnet/IP simulator (bacpypes3): server.py, objects.py, profiles.py
  modbus/           — Modbus TCP simulator (pymodbus): server.py, profiles.py
  behaviors/base.py — ValueBehavior plugin system for realistic data generation
  scenarios/        — ScenarioRunner (multi-device orchestration), E2EVerifier
  skybox/           — Async HTTP client + Pydantic models for Skycentrics gateway API
  dashboard/        — FastAPI + Jinja2 + HTMX web UI (app.py, routes.py, state.py, recorder.py)
profiles/
  bacnet/           — 12 device profiles (AHU, chiller, boiler, VAV, RTU, meter, etc.)
  modbus/           — 8 device profiles (power meter, VFD, pump, weather station, etc.)
  scenarios/        — 4 multi-device scenarios (small_office, medium_office, campus, data_center)
```

## Key Concepts

**Device profiles** — YAML files defining BACnet objects or Modbus registers with attached value behaviors. Each profile includes an `equipment_class` field (e.g. `AHU`, `VAV`, `Boiler`) that is propagated to the gateway during registration. Loaded by `bacnet/profiles.py` and `modbus/profiles.py`.

**ValueBehaviors** (`behaviors/base.py`) — Plugin system for realistic sensor data. Types: `static`, `sine_wave`, `phased_sine_wave`, `random_walk`, `accumulator`, `schedule`, `binary_toggle`, `weighted_choice`. Derived behaviors (`dew_point`, `wet_bulb`, `deadband_switch`) reference other behaviors by name and resolve in a second pass.

**ScenarioRunner** (`scenarios/runner.py`) — Starts multiple BACnet + Modbus simulators from a scenario YAML, optionally registers them with a Skybox gateway. After registration, sets each connection's Brick Schema equipment class via the gateway API if the profile specifies one.

**E2EVerifier** (`scenarios/verify.py`) — Starts a scenario, waits for gateway polling, then checks that telemetry data flows end-to-end.

**Dashboard** (`dashboard/`) — FastAPI + Jinja2 + HTMX web UI with per-device REST API. Scenario preloading and gateway registration happen in the FastAPI lifespan handler (not before server start) so Modbus asyncio server tasks survive in uvicorn's event loop. The dashboard REST API (`/api/devices/json`, `/actions/stop-device/{id}`, `/actions/start-device/{id}`) enables programmatic device control for integration tests. Supports sub-path deployment via `BSIM_DASHBOARD_ROOT_PATH` — all template links use a `{{ base_path }}` Jinja2 global. When proxied under the scanner at `/simulator`, a `{{ portal_path }}` global provides a link back to the scanner portal.

**Modbus per-instance shutdown** — Uses `ModbusTcpServer` directly (not `StartAsyncTcpServer`) so individual Modbus simulators can be stopped/started independently via `server.shutdown()`.

## Config

Environment variables (prefix `BSIM_`) or `.env` file:

| Variable | Default | Purpose |
|----------|---------|---------|
| `BSIM_SKYBOX_HOST` | `10.0.0.35` | Gateway IP |
| `BSIM_SKYBOX_PORT` | `8000` | Gateway port |
| `BSIM_SKYBOX_USERNAME` | | Gateway auth |
| `BSIM_SKYBOX_PASSWORD` | | Gateway auth |
| `BSIM_BACNET_INTERFACE` | `eth0` | Network interface for BACnet broadcasts |
| `BSIM_BACNET_PORT` | `47808` | BACnet UDP port |
| `BSIM_MODBUS_BIND_ADDRESS` | `0.0.0.0` | Modbus TCP bind |
| `BSIM_MODBUS_PORT` | `10502` | Modbus TCP port |
| `BSIM_DASHBOARD_ROOT_PATH` | `""` | URL prefix for sub-path deployment (e.g. `/scanner/simulator`) |

## Conventions

- Python 3.11+, Ruff for linting (line-length 100)
- Async-first — all networking uses asyncio
- Snake_case for behavior types (`sine_wave`, `random_walk`)
- Kebab-case for BACnet object types (`analog-input`, `binary-output`)
- UPPERCASE for Modbus datatypes (`UINT16`, `FLOAT32`)
- Two-pass profile loading for deferred behaviors (dew_point, wet_bulb reference other behaviors by name)

## Testing

pytest with pytest-asyncio (`asyncio_mode = "auto"`). Tests in `tests/`: profile loading, dashboard, data sanity, recorder, plus `integration/` for gateway tests.
