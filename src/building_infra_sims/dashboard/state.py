"""Dashboard state: manages a dynamic pool of running simulators."""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from building_infra_sims.dashboard.recorder import TelemetryRecorder

logger = logging.getLogger(__name__)

BACNET_BASE_PORT = 47808


class CachedValue:
    """Simple TTL cache for a single value."""

    def __init__(self, ttl: float = 10.0):
        self.ttl = ttl
        self._value: Any = None
        self._fetched_at: float = 0.0

    @property
    def is_stale(self) -> bool:
        return time.monotonic() - self._fetched_at > self.ttl

    def get(self) -> Any:
        if self.is_stale:
            return None
        return self._value

    def set(self, value: Any) -> None:
        self._value = value
        self._fetched_at = time.monotonic()


@dataclass
class RunningDevice:
    """Tracks a running simulator instance."""

    id: str
    name: str
    protocol: str  # "bacnet" or "modbus"
    profile_path: str
    sim: Any  # BACnetDeviceSimulator or ModbusDeviceSimulator
    status: str = "running"  # "running", "stopped", "error"
    registered: bool = False
    gateway_conn_id: str | None = None
    error: str | None = None
    equipment_class: str | None = None


class DashboardState:
    """Manages a dynamic pool of running simulators."""

    def __init__(self):
        self.devices: dict[str, RunningDevice] = {}
        self._next_bacnet_port = BACNET_BASE_PORT
        self._next_modbus_port = 10502
        self._telemetry_cache = CachedValue(ttl=8.0)
        self._connections_cache = CachedValue(ttl=15.0)
        self._stats_cache = CachedValue(ttl=15.0)
        self._lock = asyncio.Lock()
        self.recorder = TelemetryRecorder()
        self._recording_task: asyncio.Task | None = None

    # ── Profile discovery ─────────────────────────────────────────────────

    def list_profiles(self) -> dict[str, list[dict]]:
        """List available BACnet and Modbus profiles."""
        from building_infra_sims.config import settings

        result = {"bacnet": [], "modbus": []}
        for protocol in ("bacnet", "modbus"):
            profile_dir = settings.profiles_dir / protocol
            if not profile_dir.exists():
                continue
            for p in sorted(profile_dir.glob("*.yaml")):
                with open(p) as f:
                    data = yaml.safe_load(f)
                result[protocol].append({
                    "path": str(p),
                    "filename": p.name,
                    "name": data.get("name", p.stem),
                    "description": data.get("description", ""),
                })
        return result

    def list_scenarios(self) -> list[dict]:
        """List available scenario files."""
        from building_infra_sims.config import settings

        scenarios_dir = settings.profiles_dir / "scenarios"
        if not scenarios_dir.exists():
            return []
        result = []
        for p in sorted(scenarios_dir.glob("*.yaml")):
            with open(p) as f:
                data = yaml.safe_load(f)
            bacnet_count = len(data.get("bacnet_devices", []))
            modbus_count = len(data.get("modbus_devices", []))
            result.append({
                "path": str(p),
                "filename": p.name,
                "name": data.get("name", p.stem),
                "description": data.get("description", ""),
                "bacnet_count": bacnet_count,
                "modbus_count": modbus_count,
                "total": bacnet_count + modbus_count,
            })
        return result

    # ── Device lifecycle ──────────────────────────────────────────────────

    def _allocate_bacnet_port(self) -> int:
        port = self._next_bacnet_port
        self._next_bacnet_port += 1
        return port

    def _allocate_modbus_port(self) -> int:
        port = self._next_modbus_port
        self._next_modbus_port += 1
        return port

    async def start_bacnet_device(
        self,
        profile_path: str,
        device_id: int | None = None,
        port: int | None = None,
    ) -> RunningDevice:
        """Start a BACnet simulator from a profile."""
        from building_infra_sims.bacnet.profiles import create_simulator_from_profile

        async with self._lock:
            if port is None:
                port = self._allocate_bacnet_port()
            elif port >= self._next_bacnet_port:
                self._next_bacnet_port = port + 1

            sim = create_simulator_from_profile(
                profile_path=profile_path,
                device_id=device_id,
                port=port,
            )

            # Read equipment_class from profile
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)
            eq_class = profile_data.get("equipment_class")

            dev_id = str(uuid.uuid4())[:8]
            device = RunningDevice(
                id=dev_id,
                name=sim.device_name,
                protocol="bacnet",
                profile_path=profile_path,
                sim=sim,
                equipment_class=eq_class,
            )

            try:
                await sim.start()
                device.status = "running"
            except Exception as e:
                device.status = "error"
                device.error = str(e)
                logger.error(f"Failed to start BACnet device: {e}")

            self.devices[dev_id] = device
            return device

    async def start_modbus_device(
        self,
        profile_path: str,
        port: int | None = None,
        unit_id: int | None = None,
    ) -> RunningDevice:
        """Start a Modbus simulator from a profile."""
        from building_infra_sims.modbus.profiles import create_simulator_from_profile

        async with self._lock:
            if port is None:
                port = self._allocate_modbus_port()
            elif port >= self._next_modbus_port:
                self._next_modbus_port = port + 1

            sim = create_simulator_from_profile(
                profile_path=profile_path,
                port=port,
                unit_id=unit_id,
            )

            # Read equipment_class from profile
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)
            eq_class = profile_data.get("equipment_class")

            dev_id = str(uuid.uuid4())[:8]
            device = RunningDevice(
                id=dev_id,
                name=sim.device_name,
                protocol="modbus",
                profile_path=profile_path,
                sim=sim,
                equipment_class=eq_class,
            )

            try:
                await sim.start()
                device.status = "running"
            except Exception as e:
                device.status = "error"
                device.error = str(e)
                logger.error(f"Failed to start Modbus device: {e}")

            self.devices[dev_id] = device
            return device

    async def stop_device(self, device_id: str) -> bool:
        """Stop a running simulator."""
        device = self.devices.get(device_id)
        if not device:
            return False

        try:
            await device.sim.stop()
            device.status = "stopped"
        except Exception as e:
            device.status = "error"
            device.error = str(e)
            logger.error(f"Failed to stop device {device_id}: {e}")

        return True

    async def remove_device(self, device_id: str) -> bool:
        """Stop and remove a device from the pool."""
        device = self.devices.get(device_id)
        if not device:
            return False

        if device.status == "running":
            await self.stop_device(device_id)

        # Unregister from gateway if registered
        if device.registered and device.gateway_conn_id:
            await self._unregister_device(device)

        del self.devices[device_id]
        return True

    async def stop_all(self) -> None:
        """Stop all running simulators."""
        for device in list(self.devices.values()):
            if device.status == "running":
                await self.stop_device(device.id)

    # ── Recording ───────────────────────────────────────────────────────

    async def start_recording(self, interval: float = 5.0) -> None:
        """Start background task that records simulator telemetry."""
        if self._recording_task is not None:
            return
        self._recording_task = asyncio.create_task(self._record_loop(interval))

    async def stop_recording(self) -> None:
        """Stop the background recording task."""
        if self._recording_task:
            self._recording_task.cancel()
            try:
                await self._recording_task
            except asyncio.CancelledError:
                pass
            self._recording_task = None

    async def _record_loop(self, interval: float) -> None:
        while True:
            try:
                points = self.read_local_telemetry()
                if points:
                    self.recorder.record_snapshot(points)
            except Exception as e:
                logger.warning(f"Recording snapshot failed: {e}")
            await asyncio.sleep(interval)

    # ── Scenario loading ──────────────────────────────────────────────────

    async def load_scenario(self, scenario_path: str) -> list[RunningDevice]:
        """Load and start all devices from a scenario file."""
        path = Path(scenario_path)
        with open(path) as f:
            scenario = yaml.safe_load(f)

        started = []

        for dev_cfg in scenario.get("bacnet_devices", []):
            device = await self.start_bacnet_device(
                profile_path=dev_cfg["profile"],
                device_id=dev_cfg.get("device_id"),
                port=dev_cfg.get("port"),
            )
            started.append(device)

        for dev_cfg in scenario.get("modbus_devices", []):
            device = await self.start_modbus_device(
                profile_path=dev_cfg["profile"],
                port=dev_cfg.get("port"),
                unit_id=dev_cfg.get("unit_id"),
            )
            started.append(device)

        return started

    # ── Gateway registration ──────────────────────────────────────────────

    def _get_skybox_params(self) -> tuple[str, str | None, str | None]:
        from building_infra_sims.config import settings

        return settings.skybox_base_url, settings.skybox_username, settings.skybox_password

    async def register_device(self, device_id: str) -> bool:
        """Register a single device with the gateway."""
        device = self.devices.get(device_id)
        if not device or device.status != "running":
            return False

        from building_infra_sims.skybox.client import SkyboxClient
        from building_infra_sims.skybox.models import (
            BacnetConnectionConfig,
            ConnectionCreate,
            ConnectionType,
            ModbusConnectionConfig,
            ModbusPointCreate,
            PointDataType,
            RegisterType,
        )

        register_type_map = {
            "holding": RegisterType.HOLDING_REGISTER,
            "input": RegisterType.INPUT_REGISTER,
        }
        datatype_map = {
            "FLOAT32": PointDataType.FLOAT32,
            "FLOAT64": PointDataType.FLOAT64,
            "INT16": PointDataType.INT16,
            "UINT16": PointDataType.UINT16,
            "INT32": PointDataType.INT32,
            "UINT32": PointDataType.UINT32,
            "INT64": PointDataType.INT64,
            "UINT64": PointDataType.UINT64,
            "BOOL": PointDataType.BOOL,
        }

        url, user, pwd = self._get_skybox_params()
        if not user or not pwd:
            device.error = "Gateway credentials not configured (set BSIM_SKYBOX_USERNAME and BSIM_SKYBOX_PASSWORD)"
            logger.error(f"Cannot register device {device_id}: {device.error}")
            return False

        try:
            async with SkyboxClient(url, user, pwd) as sb:
                await sb.sign_in()
                sim = device.sim
                conn_name = f"Sim: {device.name}"

                if device.protocol == "bacnet":
                    conn = await sb.create_connection(
                        ConnectionCreate(
                            name=conn_name,
                            description=f"Simulated BACnet device",
                            connection_type=ConnectionType.BACNET_IP,
                            config=BacnetConnectionConfig(
                                ip_address=sim.ip_address,
                                device_id=sim.device_id,
                                port=sim.port,
                                auto_discover=True,
                                poll_interval=30,
                            ),
                        )
                    )
                    device.gateway_conn_id = conn.id
                    if conn.id:
                        await asyncio.sleep(2)
                        try:
                            await sb.save_bacnet_objects(conn.id, auto_add=True)
                        except Exception as e:
                            logger.warning(f"BACnet discovery failed: {e}")
                        if device.equipment_class:
                            try:
                                await sb.update_equipment_class(
                                    conn.id, device.equipment_class
                                )
                            except Exception as e:
                                logger.warning(f"Failed to set equipment class: {e}")

                elif device.protocol == "modbus":
                    conn = await sb.create_connection(
                        ConnectionCreate(
                            name=conn_name,
                            description=f"Simulated Modbus device",
                            connection_type=ConnectionType.MODBUS_TCP,
                            config=ModbusConnectionConfig(
                                ip_address=sim.bind_address
                                if sim.bind_address != "0.0.0.0"
                                else self._get_local_ip(),
                                port=sim.port,
                                unit_id=sim.unit_id,
                                poll_interval=30,
                            ),
                        )
                    )
                    device.gateway_conn_id = conn.id
                    if conn.id:
                        await asyncio.sleep(1)
                        for reg in sim._registers:
                            try:
                                await sb.add_modbus_point(
                                    conn.id,
                                    ModbusPointCreate(
                                        point_name=reg.name,
                                        address=reg.address,
                                        format=datatype_map.get(
                                            reg.datatype, PointDataType.UINT16
                                        ),
                                        count=reg.count,
                                        unit=reg.unit,
                                        register_type=register_type_map.get(
                                            reg.register_type,
                                            RegisterType.HOLDING_REGISTER,
                                        ),
                                    ),
                                )
                            except Exception as e:
                                logger.warning(f"Failed to add point '{reg.name}': {e}")
                        if device.equipment_class:
                            try:
                                await sb.update_equipment_class(
                                    conn.id, device.equipment_class
                                )
                            except Exception as e:
                                logger.warning(f"Failed to set equipment class: {e}")

                device.registered = True
                device.error = None  # clear any previous error
                self._connections_cache.set(None)  # invalidate
                return True

        except Exception as e:
            device.error = f"Registration failed: {e}"
            logger.error(f"Failed to register device {device_id}: {e}")
            return False

    async def _unregister_device(self, device: RunningDevice) -> None:
        """Remove a device's connection from the gateway."""
        if not device.gateway_conn_id:
            return

        from building_infra_sims.skybox.client import SkyboxClient

        url, user, pwd = self._get_skybox_params()
        try:
            async with SkyboxClient(url, user, pwd) as sb:
                await sb.sign_in()
                await sb.delete_connection(device.gateway_conn_id)
                device.registered = False
                device.gateway_conn_id = None
                self._connections_cache.set(None)
        except Exception as e:
            logger.warning(f"Failed to unregister device: {e}")

    async def unregister_device(self, device_id: str) -> bool:
        """Unregister a single device from the gateway."""
        device = self.devices.get(device_id)
        if not device or not device.registered:
            return False
        await self._unregister_device(device)
        return True

    async def register_all(self) -> int:
        """Register all running, unregistered devices."""
        count = 0
        for device in list(self.devices.values()):
            if device.status == "running" and not device.registered:
                if await self.register_device(device.id):
                    count += 1
        return count

    async def unregister_all(self) -> int:
        """Unregister all registered devices from the gateway."""
        count = 0
        for device in list(self.devices.values()):
            if device.registered:
                await self._unregister_device(device)
                count += 1
        return count

    def _get_local_ip(self) -> str:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.0.0.1", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    # ── Device info ───────────────────────────────────────────────────────

    def get_device_summary(self) -> list[dict]:
        """Get summary of all managed devices."""
        devices = []
        for dev in self.devices.values():
            sim = dev.sim
            if dev.protocol == "bacnet":
                info = {
                    "id": dev.id,
                    "name": dev.name,
                    "protocol": "BACnet",
                    "device_id": str(sim.device_id),
                    "address": f"{sim.ip_address}:{sim.port}",
                    "points": len(sim._object_defs),
                    "status": dev.status,
                    "registered": dev.registered,
                    "profile": Path(dev.profile_path).name,
                    "error": dev.error,
                }
            else:
                info = {
                    "id": dev.id,
                    "name": dev.name,
                    "protocol": "Modbus",
                    "device_id": f"unit {sim.unit_id}",
                    "address": f"{sim.bind_address}:{sim.port}",
                    "points": len(sim._registers),
                    "status": dev.status,
                    "registered": dev.registered,
                    "profile": Path(dev.profile_path).name,
                    "error": dev.error,
                }
            devices.append(info)
        return devices

    # ── Local telemetry (reads directly from simulators) ─────────────────

    def read_local_telemetry(self) -> list[dict]:
        """Read current values from all running simulators."""
        from bacpypes3.primitivedata import ObjectIdentifier

        points = []
        for dev in self.devices.values():
            if dev.status != "running":
                continue
            sim = dev.sim

            if dev.protocol == "bacnet":
                if not sim._app:
                    continue
                for obj_def in sim._object_defs:
                    try:
                        oid = ObjectIdentifier(obj_def["object-identifier"])
                        obj = sim._app.get_object_id(oid)
                        if obj is None:
                            continue
                        value = obj.presentValue
                        # Convert BACpypes values to plain Python types
                        if hasattr(value, "value"):
                            value = value.value
                        if isinstance(value, float):
                            value = round(value, 4)
                        points.append({
                            "device": dev.name,
                            "device_id": dev.id,
                            "protocol": "BACnet",
                            "point": obj_def["object-name"],
                            "value": value,
                            "units": obj_def.get("units", ""),
                            "obj_type": obj_def["object-type"],
                        })
                    except Exception:
                        continue

            elif dev.protocol == "modbus":
                for reg_data in sim.get_register_values():
                    value = reg_data["value"]
                    if isinstance(value, float):
                        value = round(value, 4)
                    points.append({
                        "device": dev.name,
                        "device_id": dev.id,
                        "protocol": "Modbus",
                        "point": reg_data["name"],
                        "value": value,
                        "units": reg_data["units"],
                        "obj_type": reg_data["datatype"],
                    })

        return points

    # ── Gateway data (cached) ─────────────────────────────────────────────

    async def fetch_telemetry(self) -> dict:
        cached = self._telemetry_cache.get()
        if cached is not None:
            return cached

        from building_infra_sims.skybox.client import SkyboxClient

        url, user, pwd = self._get_skybox_params()
        try:
            async with SkyboxClient(url, user, pwd) as sb:
                await sb.sign_in()
                telem = await sb.get_telemetry()
                result = {
                    "timestamp": telem.timestamp,
                    "total_points": telem.total_points,
                    "data_points": [
                        {
                            "id": dp.id,
                            "data": dp.data,
                            "units": dp.units or "",
                            "type": dp.type,
                            "time": dp.time,
                            "zone": dp.zone or "",
                            "room": dp.room or "",
                        }
                        for dp in telem.data_points
                    ],
                }
                self._telemetry_cache.set(result)
                return result
        except Exception as e:
            logger.warning(f"Failed to fetch telemetry: {e}")
            return {"timestamp": 0, "total_points": 0, "data_points": [], "error": str(e)}

    async def fetch_connections(self) -> list[dict]:
        cached = self._connections_cache.get()
        if cached is not None:
            return cached

        from building_infra_sims.skybox.client import SkyboxClient

        url, user, pwd = self._get_skybox_params()
        try:
            async with SkyboxClient(url, user, pwd) as sb:
                await sb.sign_in()
                conns = await sb.list_connections()
                result = [
                    {
                        "id": c.id,
                        "name": c.name,
                        "type": c.connection_type.value,
                        "enabled": c.enabled,
                        "status": c.status.value if c.status else "unknown",
                    }
                    for c in conns.items
                ]
                self._connections_cache.set(result)
                return result
        except Exception as e:
            logger.warning(f"Failed to fetch connections: {e}")
            return []

    async def fetch_connection_stats(self) -> dict:
        cached = self._stats_cache.get()
        if cached is not None:
            return cached

        from building_infra_sims.skybox.client import SkyboxClient

        url, user, pwd = self._get_skybox_params()
        try:
            async with SkyboxClient(url, user, pwd) as sb:
                await sb.sign_in()
                stats = await sb.get_connection_stats()
                result = {
                    "total": stats.total_connections,
                    "enabled": stats.enabled_connections,
                    "disabled": stats.disabled_connections,
                    "by_type": stats.by_type,
                    "by_status": stats.by_status,
                }
                self._stats_cache.set(result)
                return result
        except Exception as e:
            logger.warning(f"Failed to fetch stats: {e}")
            return {"total": 0, "enabled": 0, "disabled": 0, "by_type": {}, "by_status": {}}

    async def fetch_telemetry_history(self, minutes: int = 60) -> list[dict]:
        from building_infra_sims.skybox.client import SkyboxClient

        url, user, pwd = self._get_skybox_params()
        try:
            async with SkyboxClient(url, user, pwd) as sb:
                await sb.sign_in()
                result = await sb.execute_sql(
                    "SELECT * FROM sensor_readings ORDER BY rowid DESC LIMIT 500"
                )
                return [dict(zip(result.columns, row)) for row in result.rows]
        except Exception as e:
            logger.warning(f"Failed to fetch history: {e}")
            return []
