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
  world.py          — Shared WorldState singleton (Boston climate + occupancy schedule)
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

### BACnet object types

`bacnet/objects.py` maps profile `type:` strings to bacpypes3 classes. Non-commandable objects (inputs / values) go through `Application.from_json`. Commandable objects (`analog-output`, `binary-output`, `multi-state-output`) and `schedule` objects are instantiated programmatically *after* app creation — `json_to_sequence` can't handle the Commandable mixin's `__init__`, and ScheduleObject's `weeklySchedule` / `effectivePeriod` structured types don't round-trip through JSON decode. `generic_ahu.yaml` includes an `Occupancy_Schedule` Schedule object so a BMS-aware client (e.g. the scanner's `/api/connections/{id}/schedules` endpoint) can read existing time-of-day rules.

## Key Concepts

**Device profiles** — YAML files defining BACnet objects or Modbus registers with attached value behaviors. Each profile includes an `equipment_class` field (e.g. `AHU`, `VAV`, `Boiler`) that is propagated to the gateway during registration. Loaded by `bacnet/profiles.py` and `modbus/profiles.py`.

**ValueBehaviors** (`behaviors/base.py`) — Plugin system for realistic sensor data. Primitive types: `static`, `sine_wave`, `phased_sine_wave`, `random_walk`, `accumulator`, `schedule`, `binary_toggle`, `weighted_choice`. World-driven types: `world_value` (reads `oat`/`occupancy`/`outdoor_rh`/`solar_ghi`/`cooling_demand`/`heating_demand` from `WorldState`), `occupancy_binary` (on/off threshold on occupancy schedule), `conditional_on_oat` (OAT-reset bands for SAT reset, economizer position, boiler OAR curve). Derived behaviors reference other behaviors by name and resolve in a second pass: `dew_point`, `wet_bulb`, `deadband_switch`, `tracks` (value tracks a named source with bias + lag), `mixed_air` (damper-weighted blend of OAT and return-air temp). Nested deferred dependencies resolve transparently via recursive `_lookup`.

**WorldState** (`world.py`) — Singleton shared by every device simulator. Deterministic pure functions of `time.time()` that return Boston climate (NOAA KBOS 1991-2020 normals, annual cosine + seasonal diurnal + sub-diurnal harmonics) and DOE medium-office occupancy (weekday 6-20h with ramp/decay, Saturday 30%, Sunday 0). Makes every device in a scenario naturally agree on whether it's a cold winter morning or a hot summer afternoon, without explicit coordination. Calibration details + source references in `docs/realistic_values_research.md`.

**ScenarioRunner** (`scenarios/runner.py`) — Starts multiple BACnet + Modbus simulators from a scenario YAML, optionally registers them with a Skybox gateway. After registration, sets each connection's Brick Schema equipment class via the gateway API if the profile specifies one.

**E2EVerifier** (`scenarios/verify.py`) — Starts a scenario, waits for gateway polling, then checks that telemetry data flows end-to-end.

**Dashboard** (`dashboard/`) — FastAPI + Jinja2 + HTMX web UI with per-device REST API. Scenario preloading and gateway registration happen in the FastAPI lifespan handler (not before server start) so Modbus asyncio server tasks survive in uvicorn's event loop. The dashboard REST API (`/api/devices/json`, `/actions/stop-device/{id}`, `/actions/start-device/{id}`) enables programmatic device control for integration tests. Supports sub-path deployment via `BSIM_DASHBOARD_ROOT_PATH` — all template links use a `{{ base_path }}` Jinja2 global. When proxied under the scanner at `/simulator`, a `{{ portal_path }}` global provides a link back to the scanner portal.

**Modbus per-instance shutdown** — Uses `ModbusTcpServer` directly (not `StartAsyncTcpServer`) so individual Modbus simulators can be stopped/started independently via `server.shutdown()`.

**External-write tracking** — Both simulators detect and surface writes from an external client (e.g. the scanner's override feature):
- **Modbus** (`modbus/server.TrackedDataBlock`) — subclasses `ModbusSequentialDataBlock`. The pymodbus handler calls `setValues()`, which records an `external_writes[address] = time.time()` entry. The behavior loop bypasses tracking via `set_internal()` so scheduled updates are not counted as external writes. Registers written within the last `EXTERNAL_WRITE_HOLD_SECONDS` (60s) are *skipped* by the behavior loop, so FC06/FC05 overrides stick long enough to be observed.
- **BACnet** (`bacnet/server._fingerprint_priority_array`) — at each behavior tick, `_scan_priority_arrays()` fingerprints slots 1..15 of every commandable object's priorityArray. Slot 16 is excluded so the behavior loop's `presentValue` writes (which land at priority 16) don't register. Any change between ticks records `_external_writes[oid] = time.time()`. The bacpypes3 `Commandable` mixin already prevents higher-priority slots from being overwritten, so no hold-window is needed here.
- **Dashboard surface** — `get_register_values()` / `get_object_info()` / `read_local_telemetry()` expose `last_write_at`, `override_active`, and `commanded_priority`. The `/api/sim-data` partial highlights recently-written rows in amber and shows "Override @P8" badges + "wrote Ns ago" age labels.

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
- Two-pass profile loading for deferred behaviors (dew_point, wet_bulb, deadband_switch, tracks, mixed_air, conditional_on_oat reference other behaviors by name; `resolve_deferred` recurses to handle nested chains)
- pymodbus pinned to `>=3.6,<3.13` — version 3.13 rejects `ModbusSequentialDataBlock(0, values)` (address=0) and changes `ModbusServerContext` API, breaking all Modbus simulators

## Testing

pytest with pytest-asyncio (`asyncio_mode = "auto"`). 252 tests in `tests/`: profile loading, dashboard, data sanity, recorder, write-tracking (Modbus `TrackedDataBlock` + BACnet priority-array fingerprinting), `test_world.py` (WorldState climate/occupancy + WorldValue/Tracks/ConditionalOnOAT/OccupancyBinary/MixedAir behavior unit tests), plus `integration/` for gateway tests.
