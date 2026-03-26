# building_infra_sims

Building infrastructure protocol simulators for testing BACnet/IP and Modbus TCP integrations.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in your gateway credentials.

## Usage

```bash
# Run a BACnet device simulator
bsim bacnet run --profile profiles/bacnet/generic_ahu.yaml --device-id 1001

# Run a Modbus device simulator
bsim modbus run --profile profiles/modbus/generic_power_meter.yaml --port 10502

# Run a full scenario (multiple devices, one process)
bsim scenario profiles/scenarios/small_office.yaml

# Run a scenario and auto-register devices with the gateway
bsim scenario profiles/scenarios/small_office.yaml --setup-skybox

# Remove all simulated connections from the gateway
bsim teardown-skybox

# Check gateway connectivity
bsim skybox status

# List available profiles and scenarios
bsim bacnet list-profiles
bsim modbus list-profiles
bsim list-scenarios
```

## Docker

```bash
docker compose up bacnet-sim   # BACnet simulator (host networking)
docker compose up modbus-sim   # Modbus TCP simulator
```

## Project Structure

- `src/building_infra_sims/bacnet/` - BACnet/IP device simulator (BACpypes3)
- `src/building_infra_sims/modbus/` - Modbus TCP device simulator (pymodbus)
- `src/building_infra_sims/skybox/` - Gateway REST API client library
- `profiles/` - YAML device profiles for simulated equipment
- `scripts/` - Utility scripts for verification and exploration
- `docs/` - API specs and documentation
