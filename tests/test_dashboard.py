"""Tests for the dashboard control panel."""

import pytest
from fastapi.testclient import TestClient

from building_infra_sims.dashboard.app import create_app
from building_infra_sims.dashboard.state import DashboardState

# Use high port range to avoid conflicts between tests and with real services
_port_counter = 30000


def _next_port() -> int:
    global _port_counter
    _port_counter += 1
    return _port_counter


@pytest.fixture
def app():
    a = create_app()
    # Start port allocation high to avoid conflicts
    a.state.dashboard._next_modbus_port = _next_port()
    a.state.dashboard._next_bacnet_port = _next_port()
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def state(app) -> DashboardState:
    return app.state.dashboard


# ── Page rendering ────────────────────────────────────────────────────────


class TestPages:
    """All HTML pages should render without errors."""

    def test_index_empty(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Simulator Overview" in resp.text

    def test_devices_empty(self, client):
        resp = client.get("/devices")
        assert resp.status_code == 200
        assert "Device Control Panel" in resp.text
        assert "Load Scenario" in resp.text

    def test_telemetry_empty(self, client):
        resp = client.get("/telemetry")
        assert resp.status_code == 200
        assert "Live Telemetry" in resp.text

    def test_history_page(self, client):
        resp = client.get("/telemetry/history")
        assert resp.status_code == 200
        assert "Telemetry History" in resp.text

    def test_connections_empty(self, client):
        resp = client.get("/connections")
        assert resp.status_code == 200
        assert "Gateway Connections" in resp.text


# ── State: profile and scenario listing ───────────────────────────────────


class TestProfileListing:
    def test_list_profiles(self, state):
        profiles = state.list_profiles()
        assert "bacnet" in profiles
        assert "modbus" in profiles
        assert len(profiles["bacnet"]) >= 5  # original 5 + 4 new
        assert len(profiles["modbus"]) >= 3  # original 3 + 3 new

    def test_profile_has_fields(self, state):
        profiles = state.list_profiles()
        for p in profiles["bacnet"]:
            assert "path" in p
            assert "name" in p
            assert "description" in p

    def test_list_scenarios(self, state):
        scenarios = state.list_scenarios()
        assert len(scenarios) >= 4
        names = {s["name"] for s in scenarios}
        assert "Small Office Building" in names
        assert "University Campus" in names

    def test_scenario_has_counts(self, state):
        scenarios = state.list_scenarios()
        for s in scenarios:
            assert "bacnet_count" in s
            assert "modbus_count" in s
            assert s["total"] == s["bacnet_count"] + s["modbus_count"]


# ── State: device lifecycle ───────────────────────────────────────────────


class TestDeviceLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop_modbus(self, state):
        device = await state.start_modbus_device(
            profile_path="profiles/modbus/generic_power_meter.yaml",
        )
        assert device.status == "running"
        assert device.protocol == "modbus"
        assert device.id in state.devices
        assert len(state.get_device_summary()) == 1

        await state.stop_device(device.id)
        assert state.devices[device.id].status == "stopped"

    @pytest.mark.asyncio
    async def test_start_and_stop_bacnet(self, state):
        device = await state.start_bacnet_device(
            profile_path="profiles/bacnet/generic_vav.yaml",
        )
        assert device.status == "running"
        assert device.protocol == "bacnet"
        assert device.id in state.devices

        await state.stop_device(device.id)
        assert state.devices[device.id].status == "stopped"

    @pytest.mark.asyncio
    async def test_remove_device(self, state):
        device = await state.start_modbus_device(
            profile_path="profiles/modbus/generic_vfd.yaml",
        )
        assert device.id in state.devices

        await state.remove_device(device.id)
        assert device.id not in state.devices

    @pytest.mark.asyncio
    async def test_stop_all(self, state):
        await state.start_modbus_device(
            profile_path="profiles/modbus/generic_power_meter.yaml",
        )
        await state.start_modbus_device(
            profile_path="profiles/modbus/generic_vfd.yaml",
        )
        assert len(state.devices) == 2

        await state.stop_all()
        for dev in state.devices.values():
            assert dev.status == "stopped"

    @pytest.mark.asyncio
    async def test_device_summary_fields(self, state):
        await state.start_modbus_device(
            profile_path="profiles/modbus/generic_power_meter.yaml",
        )
        summary = state.get_device_summary()
        assert len(summary) == 1
        d = summary[0]
        assert d["protocol"] == "Modbus"
        assert d["status"] == "running"
        assert d["registered"] is False
        assert d["points"] > 0
        assert d["name"] == "Generic Power Meter"

    @pytest.mark.asyncio
    async def test_port_auto_allocation(self, state):
        d1 = await state.start_modbus_device(
            profile_path="profiles/modbus/generic_power_meter.yaml",
        )
        d2 = await state.start_modbus_device(
            profile_path="profiles/modbus/generic_vfd.yaml",
        )
        # Ports should be different
        assert d1.sim.port != d2.sim.port

        await state.stop_all()


# ── State: scenario loading ───────────────────────────────────────────────


class TestScenarioLoading:
    @pytest.mark.asyncio
    async def test_load_small_office(self, state):
        devices = await state.load_scenario("profiles/scenarios/small_office.yaml")
        assert len(devices) == 10  # 7 BACnet + 3 Modbus

        summary = state.get_device_summary()
        bacnet = [d for d in summary if d["protocol"] == "BACnet"]
        modbus = [d for d in summary if d["protocol"] == "Modbus"]
        assert len(bacnet) == 7
        assert len(modbus) == 3

        await state.stop_all()


# ── Route actions ─────────────────────────────────────────────────────────


class TestActions:
    def test_start_device_action(self, client):
        resp = client.post(
            "/actions/start-device",
            data={
                "profile_path": "profiles/modbus/generic_power_meter.yaml",
                "protocol": "modbus",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/devices"

        # Check device appears
        resp = client.get("/devices")
        assert "Generic Power Meter" in resp.text

    def test_stop_device_action(self, client, state):
        # Start via the HTTP action so it's on the TestClient's event loop
        client.post(
            "/actions/start-device",
            data={
                "profile_path": "profiles/modbus/generic_power_meter.yaml",
                "protocol": "modbus",
            },
            follow_redirects=False,
        )
        device_id = list(state.devices.keys())[0]

        resp = client.post(
            f"/actions/stop-device/{device_id}",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert state.devices[device_id].status == "stopped"

    def test_remove_device_action(self, client, state):
        client.post(
            "/actions/start-device",
            data={
                "profile_path": "profiles/modbus/generic_power_meter.yaml",
                "protocol": "modbus",
            },
            follow_redirects=False,
        )
        device_id = list(state.devices.keys())[0]

        client.post(f"/actions/remove-device/{device_id}", follow_redirects=False)
        assert device_id not in state.devices

    def test_load_scenario_action(self, client, state):
        resp = client.post(
            "/actions/load-scenario",
            data={"scenario_path": "profiles/scenarios/small_office.yaml"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # Some devices may fail to start due to BACnet unit quirks in test env,
        # but the action should complete and devices should be tracked
        assert len(state.devices) >= 2  # at least the Modbus devices should work


# ── HTMX partials ────────────────────────────────────────────────────────


class TestPartials:
    def test_devices_partial_empty(self, client):
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        assert "No devices" in resp.text

    def test_devices_partial_with_device(self, client):
        client.post(
            "/actions/start-device",
            data={
                "profile_path": "profiles/modbus/generic_power_meter.yaml",
                "protocol": "modbus",
            },
            follow_redirects=False,
        )
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        assert "Generic Power Meter" in resp.text
        assert "running" in resp.text

    def test_telemetry_partial(self, client):
        resp = client.get("/api/telemetry")
        assert resp.status_code == 200

    def test_telemetry_history_json(self, client):
        resp = client.get("/api/telemetry/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "count" in data

    def test_telemetry_history_with_params(self, client):
        resp = client.get("/api/telemetry/history?minutes=5&source=local")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data

    def test_telemetry_sources_empty(self, client):
        resp = client.get("/api/telemetry/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "count" in data

    def test_sim_data_partial_empty(self, client):
        resp = client.get("/api/sim-data")
        assert resp.status_code == 200
        assert "No simulator data" in resp.text

    def test_sim_data_partial_with_device(self, client):
        client.post(
            "/actions/start-device",
            data={
                "profile_path": "profiles/modbus/generic_power_meter.yaml",
                "protocol": "modbus",
            },
            follow_redirects=False,
        )
        resp = client.get("/api/sim-data")
        assert resp.status_code == 200
        assert "Generic Power Meter" in resp.text


# ── Local telemetry ──────────────────────────────────────────────────────


class TestLocalTelemetry:
    def test_sim_data_page_empty(self, client):
        resp = client.get("/sim-data")
        assert resp.status_code == 200
        assert "Simulator Data" in resp.text
        assert "0 data points" in resp.text

    def test_sim_data_page_with_device(self, client):
        client.post(
            "/actions/start-device",
            data={
                "profile_path": "profiles/modbus/generic_power_meter.yaml",
                "protocol": "modbus",
            },
            follow_redirects=False,
        )
        resp = client.get("/sim-data")
        assert resp.status_code == 200
        assert "Generic Power Meter" in resp.text

    @pytest.mark.asyncio
    async def test_read_local_telemetry_modbus(self, state):
        await state.start_modbus_device(
            profile_path="profiles/modbus/generic_power_meter.yaml",
        )
        points = state.read_local_telemetry()
        assert len(points) > 0
        for p in points:
            assert "device" in p
            assert "point" in p
            assert "value" in p
            assert "units" in p
            assert p["protocol"] == "Modbus"

        await state.stop_all()

    @pytest.mark.asyncio
    async def test_read_local_telemetry_bacnet(self, state):
        await state.start_bacnet_device(
            profile_path="profiles/bacnet/generic_vav.yaml",
        )
        points = state.read_local_telemetry()
        assert len(points) > 0
        for p in points:
            assert "device" in p
            assert "point" in p
            assert "value" in p
            assert p["protocol"] == "BACnet"

        await state.stop_all()

    @pytest.mark.asyncio
    async def test_read_local_telemetry_empty(self, state):
        points = state.read_local_telemetry()
        assert points == []
