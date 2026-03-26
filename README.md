# building_infra_sims

Simulate BACnet/IP and Modbus TCP building automation devices on your LAN for integration testing. Devices appear as real equipment to any BACnet or Modbus client, producing realistic sensor data via configurable behaviors (sine waves, random walks, schedules, accumulators).

Includes a web dashboard for interactively spinning up/down individual devices or entire building scenarios, and optional integration with a Skycentrics Super Skybox gateway for end-to-end data pipeline testing.

## Requirements

- Python 3.11+
- Linux (BACnet/IP uses raw UDP sockets; tested on Ubuntu/WSL2)
- A network interface on the same subnet as your BACnet clients (if using BACnet)

## Installation

```bash
git clone https://github.com/michaelwdarby3/building_infra_sims.git
cd building_infra_sims

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

The `.env` file uses a `BSIM_` prefix for all variables:

| Variable | Default | Description |
|---|---|---|
| `BSIM_SKYBOX_HOST` | `10.0.0.35` | Gateway IP address |
| `BSIM_SKYBOX_PORT` | `8000` | Gateway HTTP API port |
| `BSIM_SKYBOX_USERNAME` | *(empty)* | Gateway login username |
| `BSIM_SKYBOX_PASSWORD` | *(empty)* | Gateway login password |
| `BSIM_BACNET_INTERFACE` | `eth0` | Network interface for BACnet |
| `BSIM_BACNET_PORT` | `47808` | BACnet/IP UDP port |
| `BSIM_MODBUS_BIND_ADDRESS` | `0.0.0.0` | Modbus TCP bind address |
| `BSIM_MODBUS_PORT` | `10502` | Default Modbus TCP port |

Gateway credentials are only required for the `--setup-skybox`, `register`, and `verify` features. Simulators run without them.

## Quick Start

### Web Dashboard (recommended)

The dashboard is an interactive control panel for starting/stopping devices, loading scenarios, and registering devices with the gateway.

```bash
bsim dashboard
```

Open http://localhost:8080 in your browser. From there you can:

- **Load a scenario** to spin up a pre-configured set of devices (e.g., a 9-device office or a 45-device campus)
- **Start individual devices** from any BACnet or Modbus profile
- **Stop or remove** devices one at a time or all at once
- **Register/unregister** devices with the gateway (requires credentials in `.env`)
- View live telemetry and gateway connection status

You can also pre-load a scenario at launch:

```bash
bsim dashboard profiles/scenarios/small_office.yaml
bsim dashboard profiles/scenarios/campus.yaml --setup-skybox
```

### CLI Usage

```bash
# Run a single BACnet device
bsim bacnet run --profile profiles/bacnet/generic_ahu.yaml --device-id 1001

# Run a single Modbus device
bsim modbus run --profile profiles/modbus/generic_power_meter.yaml --port 10502

# Run a multi-device scenario
bsim scenario profiles/scenarios/small_office.yaml

# Run a scenario and auto-register with the gateway
bsim scenario profiles/scenarios/small_office.yaml --setup-skybox

# Verify end-to-end data flow through the gateway
bsim verify profiles/scenarios/small_office.yaml

# Check gateway connectivity
bsim skybox status

# List available profiles and scenarios
bsim bacnet list-profiles
bsim modbus list-profiles
bsim list-scenarios

# Remove all simulated connections from the gateway
bsim teardown-skybox
```

## Device Profiles

Profiles are YAML files that define a simulated device's points and behaviors. Each profile specifies the BACnet objects or Modbus registers the device exposes, along with how their values change over time.

### BACnet Profiles (`profiles/bacnet/`)

| Profile | Description | Objects |
|---|---|---|
| `generic_ahu.yaml` | Air handling unit with supply/return/mixed air temps, dampers, fan status | ~14 |
| `generic_vav.yaml` | VAV terminal unit with zone temp, airflow, damper, reheat | ~9 |
| `generic_boiler.yaml` | Hot water boiler with supply/return temps, firing rate, flame status | ~12 |
| `generic_chiller.yaml` | Water-cooled chiller with evap/condenser pressures, compressor staging | ~17 |
| `generic_meter.yaml` | Electrical meter with 3-phase voltage, current, power, energy | ~13 |
| `generic_cooling_tower.yaml` | Cooling tower with basin/approach temps, fan speed, makeup valve | ~10 |
| `generic_heat_pump.yaml` | Heat pump with source/load temps, COP, defrost mode | ~10 |
| `generic_lighting_controller.yaml` | Lighting zones with occupancy sensors, daylight, schedules | ~11 |
| `generic_fire_alarm_panel.yaml` | Fire alarm panel with zone alarms, trouble, supervisory | ~12 |

### Modbus Profiles (`profiles/modbus/`)

| Profile | Description | Registers |
|---|---|---|
| `generic_power_meter.yaml` | 3-phase power meter with voltage, current, power, energy | ~12 |
| `generic_vfd.yaml` | Variable frequency drive with speed, current, torque, faults | ~10 |
| `generic_sensor_rack.yaml` | Multi-sensor rack with temperature, humidity, CO2, pressure | ~8 |
| `generic_hvac_controller.yaml` | Zone HVAC controller with temp, setpoint, damper, fan | ~12 |
| `generic_energy_meter_demand.yaml` | Demand energy meter with peak kW, kVA, TDD% | ~17 |
| `generic_weather_station.yaml` | Outdoor weather with temp, humidity, wind, barometric, solar | ~10 |

### Scenarios (`profiles/scenarios/`)

Scenarios define a collection of devices that represent a building:

| Scenario | Devices | Description |
|---|---|---|
| `small_office.yaml` | 9 | 1 AHU, 4 VAVs, 1 boiler, 1 meter, 1 VFD, 1 sensor rack |
| `medium_office.yaml` | 21 | 2 AHUs, 8 VAVs, 1 boiler, 1 chiller, 2 meters + Modbus devices |
| `campus.yaml` | 45 | 4 AHUs, 16 VAVs, 2 boilers, 2 chillers, cooling towers, heat pumps, lighting, fire alarm + Modbus |
| `data_center.yaml` | 38 | 6 chillers, 4 cooling towers, 8 CRAHs, 4 meters + VFDs, energy meters |

## Creating Custom Profiles

### BACnet Profile

```yaml
name: "My Custom Device"
description: "Description of the device"
device_id: 9001       # Default BACnet device instance ID
port: 47808           # Default BACnet/IP UDP port

objects:
  - object_type: analog-input
    instance: 1
    name: "Zone Temperature"
    present_value: 72.0
    units: degrees-fahrenheit
    description: "Space temperature sensor"
    behavior:
      type: sine_wave
      center: 72.0
      amplitude: 2.0
      period: 7200       # seconds per cycle

  - object_type: binary-input
    instance: 1
    name: "Occupancy Status"
    present_value: active
    behavior:
      type: binary_toggle
      on_duration: 600
      off_duration: 300

  - object_type: analog-output
    instance: 1
    name: "Damper Command"
    present_value: 50.0
    units: percent

  - object_type: multi-state-value
    instance: 1
    name: "Operating Mode"
    present_value: 2
    description: "1=Off 2=Heat 3=Cool 4=Auto"
```

### Modbus Profile

```yaml
name: "My Custom Meter"
description: "Description of the device"
port: 10502
unit_id: 1

registers:
  holding:
    - address: 0
      name: "Voltage"
      datatype: FLOAT32
      initial_value: 120.0
      unit: V
      behavior:
        type: random_walk
        center: 120.0
        step_size: 0.5
        min: 118.0
        max: 122.0

  input:
    - address: 100
      name: "Energy Total"
      datatype: FLOAT32
      initial_value: 1000.0
      unit: kWh
      behavior:
        type: accumulator
        initial: 1000.0
        rate_per_second: 0.01
```

### Scenario File

```yaml
name: "My Building"
description: "Custom scenario"

bacnet_devices:
  - profile: profiles/bacnet/generic_ahu.yaml
    device_id: 1001          # Unique BACnet device ID (required)

  - profile: profiles/bacnet/generic_vav.yaml
    device_id: 2001

modbus_devices:
  - profile: profiles/modbus/generic_power_meter.yaml
    port: 10503              # Unique TCP port (required)
    unit_id: 1
```

Each BACnet device in a scenario needs a unique `device_id`. Each Modbus device needs a unique `port`. The dashboard auto-allocates these if not specified, but scenarios should be explicit to avoid conflicts.

### Available Behaviors

| Type | Parameters | Use Case |
|---|---|---|
| `sine_wave` | `center`, `amplitude`, `period` | Temperatures, pressures, cyclical loads |
| `random_walk` | `center`, `step_size`, `min`, `max` | Sensor noise, fluctuating readings |
| `accumulator` | `initial`, `rate_per_second` | Energy meters, runtime counters |
| `schedule` | `schedule` (dict of "HH:MM" -> value), `default` | Occupancy, setpoint schedules |
| `binary_toggle` | `on_duration`, `off_duration` | Equipment status, alarms |
| `static` | `value` | Fixed setpoints, configuration values |

### Available BACnet Units

Profiles use human-readable unit strings that map to BACpypes3 engineering units:

`degrees-fahrenheit`, `degrees-celsius`, `percent`, `watts`, `kilowatts`, `kilowatt-hours`, `volts`, `amperes`, `cubic-feet-per-minute`, `inches-of-water`, `psi`, `pounds-per-square-inch`, `gallons-per-minute`, `rpm`, `hertz`, `kilovolt-amperes-reactive`, `no-units`

## Testing

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run only profile validation tests
pytest tests/test_profiles.py -v

# Run only dashboard tests
pytest tests/test_dashboard.py -v
```

The test suite includes:

- **Profile validation** (72 tests) -- every BACnet and Modbus profile is loaded and started to catch configuration errors (e.g., missing unit mappings). Every scenario is checked for valid profile references, port conflicts, and device ID conflicts.
- **Dashboard tests** (24 tests) -- page rendering, device lifecycle, HTTP actions, HTMX partials.

## Docker

```bash
# Run a single BACnet device
docker compose up bacnet-sim

# Run a single Modbus device
docker compose up modbus-sim
```

BACnet uses `network_mode: host` because BACnet/IP requires Layer 2 broadcast access for Who-Is/I-Am discovery. Modbus uses standard port mapping.

## Architecture

```
src/building_infra_sims/
    bacnet/              BACnet/IP simulator (BACpypes3)
        server.py            BACnetDeviceSimulator class
        objects.py           BACnet object factory + unit mapping
        profiles.py          YAML profile loader
    modbus/              Modbus TCP simulator (pymodbus)
        server.py            ModbusDeviceSimulator class
        profiles.py          YAML profile loader
    skybox/              Gateway REST API client
        client.py            SkyboxClient (async httpx)
        models.py            Pydantic models for API requests/responses
    scenarios/           Multi-device orchestration
        runner.py            ScenarioRunner - starts devices + registers with gateway
        verify.py            E2EVerifier - checks telemetry flows end-to-end
    dashboard/           Web control panel
        app.py               FastAPI app factory
        state.py             DashboardState - manages device pool
        routes.py            HTML pages + action endpoints + HTMX partials
        templates/           Jinja2 templates (Pico CSS + HTMX)
    behaviors/           Value simulation engines
        base.py              SineWave, RandomWalk, Accumulator, etc.
    config.py            Pydantic Settings (reads .env)
    cli.py               Typer CLI entry point
```

## Network Requirements

- **BACnet/IP**: Uses UDP. Each simulated device binds to a unique port starting from 47808. The host must be on the same subnet as BACnet clients (or use a BBMD). On WSL2, this means the WSL network adapter.
- **Modbus TCP**: Uses standard TCP. Each simulated device listens on a unique port (default starting from 10502). Works across subnets and through NAT.
- **Dashboard**: HTTP on port 8080 (configurable via `--port`).
- **Gateway API**: HTTP to the Skybox at the configured host/port. Only needed for registration and telemetry features.
