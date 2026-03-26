"""Tests that validate all device profiles can load and start successfully.

These tests catch issues like missing unit mappings, invalid object types,
and other configuration errors that prevent simulators from starting.
"""

import glob
from pathlib import Path

import pytest
import yaml

from building_infra_sims.bacnet.objects import UNIT_MAP, resolve_units
from building_infra_sims.bacnet.profiles import create_simulator_from_profile as create_bacnet_sim
from building_infra_sims.modbus.profiles import create_simulator_from_profile as create_modbus_sim

PROFILES_DIR = Path(__file__).parent.parent / "profiles"
BACNET_PROFILES = sorted(PROFILES_DIR.glob("bacnet/*.yaml"))
MODBUS_PROFILES = sorted(PROFILES_DIR.glob("modbus/*.yaml"))
SCENARIO_FILES = sorted(PROFILES_DIR.glob("scenarios/*.yaml"))

# High port ranges to avoid conflicts between tests and real services
_bacnet_port = 40000
_modbus_port = 40500


def _next_bacnet_port() -> int:
    global _bacnet_port
    _bacnet_port += 1
    return _bacnet_port


def _next_modbus_port() -> int:
    global _modbus_port
    _modbus_port += 1
    return _modbus_port


# ── Unit mapping coverage ─────────────────────────────────────────────────


class TestUnitMapping:
    """Verify that every unit string in every BACnet profile is in UNIT_MAP."""

    def _collect_units_from_profile(self, profile_path: Path) -> list[tuple[str, str]]:
        """Return list of (object_name, unit_string) from a profile."""
        with open(profile_path) as f:
            data = yaml.safe_load(f)
        results = []
        for obj in data.get("objects", []):
            unit = obj.get("units")
            if unit is not None:
                results.append((obj["name"], unit))
        return results

    @pytest.mark.parametrize(
        "profile_path",
        BACNET_PROFILES,
        ids=[p.stem for p in BACNET_PROFILES],
    )
    def test_all_units_in_unit_map(self, profile_path):
        """Every unit string used in a BACnet profile must resolve to a valid BACpypes3 unit."""
        units = self._collect_units_from_profile(profile_path)
        missing = []
        for obj_name, unit_str in units:
            resolved = resolve_units(unit_str)
            # If resolve_units returns the raw string unchanged, it's unmapped
            if resolved == unit_str and unit_str not in UNIT_MAP.values():
                missing.append(f"{obj_name}: {unit_str!r}")
        assert not missing, (
            f"Profile {profile_path.name} has unmapped units:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_unit_map_covers_common_units(self):
        """Sanity check that common building automation units are mapped."""
        expected = [
            "degrees-fahrenheit",
            "degrees-celsius",
            "percent",
            "psi",
            "pounds-per-square-inch",
            "kilowatts",
            "kilowatt-hours",
            "amperes",
            "volts",
            "cubic-feet-per-minute",
            "inches-of-water",
            "gallons-per-minute",
            "rpm",
            "hertz",
            "no-units",
        ]
        for unit in expected:
            assert unit in UNIT_MAP, f"Common unit {unit!r} missing from UNIT_MAP"

    def test_psi_aliases_resolve_same(self):
        """Both 'psi' and 'pounds-per-square-inch' should resolve to the same BACpypes3 value."""
        assert resolve_units("psi") == resolve_units("pounds-per-square-inch")
        assert resolve_units("psi") == "poundsForcePerSquareInch"


# ── BACnet profile loading and startup ────────────────────────────────────


class TestBACnetProfiles:
    """Verify every BACnet profile can load, create a simulator, and start it."""

    @pytest.mark.parametrize(
        "profile_path",
        BACNET_PROFILES,
        ids=[p.stem for p in BACNET_PROFILES],
    )
    def test_profile_loads(self, profile_path):
        """Profile YAML is valid and creates a simulator without errors."""
        sim = create_bacnet_sim(
            profile_path=str(profile_path),
            device_id=99000 + BACNET_PROFILES.index(profile_path),
            port=_next_bacnet_port(),
        )
        assert sim.device_name
        assert len(sim._object_defs) > 0

    @pytest.mark.parametrize(
        "profile_path",
        BACNET_PROFILES,
        ids=[p.stem for p in BACNET_PROFILES],
    )
    @pytest.mark.asyncio
    async def test_profile_starts(self, profile_path):
        """Profile creates a simulator that actually starts (catches BACpypes3 errors)."""
        port = _next_bacnet_port()
        sim = create_bacnet_sim(
            profile_path=str(profile_path),
            device_id=98000 + BACNET_PROFILES.index(profile_path),
            port=port,
        )
        try:
            await sim.start()
            assert sim._app is not None, f"Application not created for {profile_path.name}"
        finally:
            await sim.stop()

    @pytest.mark.parametrize(
        "profile_path",
        BACNET_PROFILES,
        ids=[p.stem for p in BACNET_PROFILES],
    )
    def test_profile_yaml_structure(self, profile_path):
        """Profile YAML has required top-level fields."""
        with open(profile_path) as f:
            data = yaml.safe_load(f)
        assert "name" in data, f"{profile_path.name} missing 'name'"
        assert "objects" in data, f"{profile_path.name} missing 'objects'"
        assert len(data["objects"]) > 0, f"{profile_path.name} has no objects"
        for obj in data["objects"]:
            obj_type = obj.get("type") or obj.get("object_type")
            assert obj_type, f"Object in {profile_path.name} missing type"
            assert "instance" in obj, f"Object in {profile_path.name} missing instance"
            assert "name" in obj, f"Object in {profile_path.name} missing name"


# ── Modbus profile loading and startup ────────────────────────────────────


class TestModbusProfiles:
    """Verify every Modbus profile can load, create a simulator, and start it."""

    @pytest.mark.parametrize(
        "profile_path",
        MODBUS_PROFILES,
        ids=[p.stem for p in MODBUS_PROFILES],
    )
    def test_profile_loads(self, profile_path):
        """Profile YAML is valid and creates a simulator without errors."""
        sim = create_modbus_sim(
            profile_path=str(profile_path),
            port=_next_modbus_port(),
        )
        assert sim.device_name
        assert len(sim._registers) > 0

    @pytest.mark.parametrize(
        "profile_path",
        MODBUS_PROFILES,
        ids=[p.stem for p in MODBUS_PROFILES],
    )
    @pytest.mark.asyncio
    async def test_profile_starts(self, profile_path):
        """Profile creates a simulator that actually starts."""
        port = _next_modbus_port()
        sim = create_modbus_sim(
            profile_path=str(profile_path),
            port=port,
        )
        try:
            await sim.start()
            assert sim._server_task is not None, f"Server not created for {profile_path.name}"
        finally:
            await sim.stop()

    @pytest.mark.parametrize(
        "profile_path",
        MODBUS_PROFILES,
        ids=[p.stem for p in MODBUS_PROFILES],
    )
    def test_profile_yaml_structure(self, profile_path):
        """Profile YAML has required top-level fields."""
        with open(profile_path) as f:
            data = yaml.safe_load(f)
        assert "name" in data, f"{profile_path.name} missing 'name'"
        assert "registers" in data, f"{profile_path.name} missing 'registers'"
        total_regs = sum(len(v) for v in data["registers"].values())
        assert total_regs > 0, f"{profile_path.name} has no registers"


# ── Scenario validation ──────────────────────────────────────────────────


class TestScenarios:
    """Verify scenario files reference valid profiles and have correct structure."""

    @pytest.mark.parametrize(
        "scenario_path",
        SCENARIO_FILES,
        ids=[p.stem for p in SCENARIO_FILES],
    )
    def test_scenario_structure(self, scenario_path):
        """Scenario YAML has required fields and valid device counts."""
        with open(scenario_path) as f:
            data = yaml.safe_load(f)
        assert "name" in data, f"{scenario_path.name} missing 'name'"
        bacnet = data.get("bacnet_devices", [])
        modbus = data.get("modbus_devices", [])
        assert len(bacnet) + len(modbus) > 0, f"{scenario_path.name} has no devices"

    @pytest.mark.parametrize(
        "scenario_path",
        SCENARIO_FILES,
        ids=[p.stem for p in SCENARIO_FILES],
    )
    def test_scenario_profiles_exist(self, scenario_path):
        """Every profile referenced by a scenario must exist on disk."""
        with open(scenario_path) as f:
            data = yaml.safe_load(f)
        missing = []
        for dev in data.get("bacnet_devices", []) + data.get("modbus_devices", []):
            profile = dev.get("profile", "")
            if not Path(profile).exists():
                missing.append(profile)
        assert not missing, (
            f"Scenario {scenario_path.name} references missing profiles:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    @pytest.mark.parametrize(
        "scenario_path",
        SCENARIO_FILES,
        ids=[p.stem for p in SCENARIO_FILES],
    )
    def test_scenario_no_port_conflicts(self, scenario_path):
        """No two devices in a scenario should use the same port."""
        with open(scenario_path) as f:
            data = yaml.safe_load(f)
        ports = []
        for dev in data.get("bacnet_devices", []):
            port = dev.get("port")
            if port:
                ports.append(("bacnet", dev.get("profile", "?"), port))
        for dev in data.get("modbus_devices", []):
            port = dev.get("port")
            if port:
                ports.append(("modbus", dev.get("profile", "?"), port))

        seen = {}
        conflicts = []
        for proto, profile, port in ports:
            key = (proto, port)
            if key in seen:
                conflicts.append(f"  Port {port} ({proto}): {seen[key]} vs {profile}")
            seen[key] = profile
        assert not conflicts, (
            f"Scenario {scenario_path.name} has port conflicts:\n" + "\n".join(conflicts)
        )

    @pytest.mark.parametrize(
        "scenario_path",
        SCENARIO_FILES,
        ids=[p.stem for p in SCENARIO_FILES],
    )
    def test_scenario_no_device_id_conflicts(self, scenario_path):
        """No two BACnet devices in a scenario should share a device_id."""
        with open(scenario_path) as f:
            data = yaml.safe_load(f)
        seen = {}
        conflicts = []
        for dev in data.get("bacnet_devices", []):
            did = dev.get("device_id")
            if did is not None:
                if did in seen:
                    conflicts.append(
                        f"  device_id {did}: {seen[did]} vs {dev.get('profile', '?')}"
                    )
                seen[did] = dev.get("profile", "?")
        assert not conflicts, (
            f"Scenario {scenario_path.name} has device_id conflicts:\n" + "\n".join(conflicts)
        )
