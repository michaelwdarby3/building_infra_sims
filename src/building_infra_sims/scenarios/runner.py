"""Scenario runner: orchestrate multiple simulators from a single YAML config.

Runs all BACnet and Modbus simulators in a single process. BACnet devices
are auto-assigned sequential UDP ports (47808, 47809, ...) so multiple
BACpypes3 Applications can coexist without conflicts. Modbus devices each
get their own TCP port as configured.

Optionally registers all simulated devices with the gateway via its API.
"""

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

from building_infra_sims.bacnet.profiles import (
    create_simulator_from_profile as create_bacnet_sim,
)
from building_infra_sims.modbus.profiles import (
    create_simulator_from_profile as create_modbus_sim,
)

logger = logging.getLogger(__name__)
console = Console()

BACNET_BASE_PORT = int(os.environ.get("BSIM_BACNET_BASE_PORT", "47808"))
# Added to every Modbus device port at scenario load. Use to deconflict
# multiple simulators sharing one network namespace whose scenarios
# happen to pin overlapping Modbus TCP ports.
MODBUS_PORT_SHIFT = int(os.environ.get("BSIM_MODBUS_PORT_SHIFT", "0"))


def load_scenario(scenario_path: str | Path) -> dict[str, Any]:
    path = Path(scenario_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


class ScenarioRunner:
    """Start and manage multiple BACnet/Modbus simulators from a scenario config."""

    def __init__(self, scenario_path: str | Path):
        self._scenario = load_scenario(scenario_path)
        self._bacnet_sims = []
        self._modbus_sims = []
        self._local_ip: str | None = None

    @property
    def name(self) -> str:
        return self._scenario.get("name", "Unnamed Scenario")

    def _build_simulators(self) -> None:
        # Auto-assign sequential BACnet ports
        bacnet_port = BACNET_BASE_PORT
        for dev in self._scenario.get("bacnet_devices", []):
            port = dev.get("port", bacnet_port)
            sim = create_bacnet_sim(
                profile_path=dev["profile"],
                device_id=dev.get("device_id"),
                ip_address=dev.get("ip_address"),
                port=port,
            )
            # Read equipment_class from profile for later registration
            profile_path = Path(dev["profile"])
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)
            sim._equipment_class = dev.get(
                "equipment_class", profile_data.get("equipment_class")
            )
            self._bacnet_sims.append(sim)
            # Next device gets the next port (if not explicitly set)
            if "port" not in dev:
                bacnet_port = port + 1
            else:
                bacnet_port = max(bacnet_port, port + 1)

        for dev in self._scenario.get("modbus_devices", []):
            base_port = dev.get("port")
            shifted_port = base_port + MODBUS_PORT_SHIFT if base_port else None
            sim = create_modbus_sim(
                profile_path=dev["profile"],
                port=shifted_port,
                unit_id=dev.get("unit_id"),
                bind_address=dev.get("bind_address", "0.0.0.0"),
            )
            # Read equipment_class from profile for later registration
            profile_path = Path(dev["profile"])
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)
            sim._equipment_class = dev.get(
                "equipment_class", profile_data.get("equipment_class")
            )
            self._modbus_sims.append(sim)

    def _print_device_table(self) -> None:
        """Print a summary table of all running devices."""
        table = Table(title=f"Scenario: {self.name}")
        table.add_column("Protocol", style="cyan")
        table.add_column("Device Name", style="bold")
        table.add_column("ID / Unit", style="green")
        table.add_column("Address", style="yellow")
        table.add_column("Objects / Registers")

        for sim in self._bacnet_sims:
            self._local_ip = self._local_ip or sim.ip_address
            table.add_row(
                "BACnet",
                sim.device_name,
                str(sim.device_id),
                f"{sim.ip_address}:{sim.port}",
                str(len(sim._object_defs)),
            )

        for sim in self._modbus_sims:
            table.add_row(
                "Modbus",
                sim.device_name,
                f"unit {sim.unit_id}",
                f"{sim.bind_address}:{sim.port}",
                str(len(sim._registers)),
            )

        console.print(table)

    async def start(self) -> None:
        """Build and start all simulators."""
        self._build_simulators()

        logger.info(
            f"Starting scenario '{self.name}': "
            f"{len(self._bacnet_sims)} BACnet + {len(self._modbus_sims)} Modbus devices"
        )

        # Start all simulators concurrently
        tasks = []
        for sim in self._bacnet_sims:
            tasks.append(sim.start())
        for sim in self._modbus_sims:
            tasks.append(sim.start())

        await asyncio.gather(*tasks)

        self._print_device_table()
        logger.info(f"Scenario '{self.name}' is fully online")

    async def stop(self) -> None:
        """Stop all simulators."""
        tasks = []
        for sim in self._bacnet_sims:
            tasks.append(sim.stop())
        for sim in self._modbus_sims:
            tasks.append(sim.stop())

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"Scenario '{self.name}' stopped")

    async def register_with_skybox(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Register all simulated devices as connections in the gateway.

        For BACnet devices: creates connections and triggers auto-discovery so the
        gateway discovers all BACnet objects and begins polling.

        For Modbus devices: creates connections and registers each individual point
        (register) so the gateway knows which addresses to poll.
        """
        from building_infra_sims.config import settings
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

        # Map sim register type strings to gateway API enums
        register_type_map = {
            "holding": RegisterType.HOLDING_REGISTER,
            "input": RegisterType.INPUT_REGISTER,
            "coil": RegisterType.COIL,
            "discrete_input": RegisterType.DISCRETE_INPUT,
        }

        # Map sim datatype strings to gateway API enums
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

        url = base_url or settings.skybox_base_url
        user = username or settings.skybox_username
        pwd = password or settings.skybox_password
        advertise_host = settings.skybox_advertise_host or None
        conn_prefix = settings.skybox_connection_prefix

        if not user or not pwd:
            logger.warning("Gateway credentials not configured — skipping registration")
            return

        if advertise_host:
            logger.info(
                f"BSIM_SKYBOX_ADVERTISE_HOST set — registering all devices with "
                f"ip_address={advertise_host} (overrides per-device IPs)"
            )

        async with SkyboxClient(url, user, pwd) as sb:
            await sb.sign_in()

            # Get existing connections to avoid duplicates
            existing = await sb.list_connections()
            existing_names = {c.name for c in existing.items}

            created_conns = 0
            created_points = 0
            discovered_objects = 0

            # ── BACnet devices ──
            for sim in self._bacnet_sims:
                conn_name = f"{conn_prefix}{sim.device_name}"
                if conn_name in existing_names:
                    logger.info(f"Connection '{conn_name}' already exists — skipping")
                    continue

                ip = advertise_host or sim.ip_address or self._local_ip
                conn = await sb.create_connection(
                    ConnectionCreate(
                        name=conn_name,
                        description=f"Simulated BACnet device (scenario: {self.name})",
                        connection_type=ConnectionType.BACNET_IP,
                        config=BacnetConnectionConfig(
                            ip_address=ip,
                            device_id=sim.device_id,
                            port=sim.port,
                            auto_discover=True,
                            poll_interval=30,
                        ),
                    )
                )
                created_conns += 1
                logger.info(f"Created BACnet connection '{conn_name}'")

                # Trigger auto-discovery to find all BACnet objects
                if conn.id:
                    await asyncio.sleep(2)  # let gateway establish connection
                    try:
                        result = await sb.save_bacnet_objects(conn.id, auto_add=True)
                        discovered_objects += result.objects_added
                        logger.info(
                            f"BACnet discovery for '{sim.device_name}': "
                            f"found {result.objects_discovered}, added {result.objects_added}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"BACnet discovery failed for '{sim.device_name}': {e}"
                        )
                    # Set equipment class from profile
                    eq_class = getattr(sim, "_equipment_class", None)
                    if eq_class and conn.id:
                        try:
                            await sb.update_equipment_class(conn.id, eq_class)
                        except Exception as e:
                            logger.warning(
                                f"Failed to set equipment class for '{sim.device_name}': {e}"
                            )

            # ── Modbus devices ──
            for sim in self._modbus_sims:
                conn_name = f"{conn_prefix}{sim.device_name}"
                if conn_name in existing_names:
                    logger.info(f"Connection '{conn_name}' already exists — skipping")
                    continue

                ip = advertise_host or self._local_ip or "127.0.0.1"
                conn = await sb.create_connection(
                    ConnectionCreate(
                        name=conn_name,
                        description=f"Simulated Modbus device (scenario: {self.name})",
                        connection_type=ConnectionType.MODBUS_TCP,
                        config=ModbusConnectionConfig(
                            ip_address=ip,
                            port=sim.port,
                            unit_id=sim.unit_id,
                            poll_interval=30,
                        ),
                    )
                )
                created_conns += 1
                logger.info(f"Created Modbus connection '{conn_name}'")

                # Register individual Modbus points
                if conn.id:
                    await asyncio.sleep(1)  # let gateway establish connection
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
                            created_points += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to add point '{reg.name}' for "
                                f"'{sim.device_name}': {e}"
                            )

                    logger.info(
                        f"Registered {created_points} Modbus points for "
                        f"'{sim.device_name}'"
                    )
                    # Set equipment class from profile
                    eq_class = getattr(sim, "_equipment_class", None)
                    if eq_class and conn.id:
                        try:
                            await sb.update_equipment_class(conn.id, eq_class)
                        except Exception as e:
                            logger.warning(
                                f"Failed to set equipment class for '{sim.device_name}': {e}"
                            )

            console.print(
                f"[bold green]Gateway registration complete:[/bold green] "
                f"{created_conns} connections, {created_points} Modbus points, "
                f"{discovered_objects} BACnet objects discovered "
                f"({len(existing_names)} connections already existed)"
            )

    async def unregister_from_skybox(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Remove this scenario's connections from the gateway.

        Scoped by `BSIM_SKYBOX_CONNECTION_PREFIX` so multi-sidecar
        deployments don't wipe each other's registrations.
        """
        from building_infra_sims.config import settings
        from building_infra_sims.skybox.client import SkyboxClient

        url = base_url or settings.skybox_base_url
        user = username or settings.skybox_username
        pwd = password or settings.skybox_password
        conn_prefix = settings.skybox_connection_prefix

        async with SkyboxClient(url, user, pwd) as sb:
            await sb.sign_in()
            conns = await sb.list_connections()
            removed = 0
            for c in conns.items:
                if c.name.startswith(conn_prefix) and c.id:
                    await sb.delete_connection(c.id)
                    logger.info(f"Removed connection '{c.name}'")
                    removed += 1

            console.print(
                f"[bold]Removed {removed} '{conn_prefix}'-prefixed connections from gateway[/bold]"
            )

    async def run_forever(self, setup_skybox: bool = False) -> None:
        """Start and run until SIGINT/SIGTERM."""
        await self.start()

        if setup_skybox:
            # When multiple sidecars share a single gateway, stagger
            # them via BSIM_REGISTER_DELAY_S so the scanner isn't
            # serving N concurrent floods of POST /api/connections at
            # boot — the smaller sim should set this to 0 and the
            # larger one should set it to ~30s (or vice versa).
            delay_s = float(os.environ.get("BSIM_REGISTER_DELAY_S", "0"))
            if delay_s > 0:
                logger.info(
                    f"BSIM_REGISTER_DELAY_S={delay_s}: deferring skybox "
                    f"registration to give other sidecars head room"
                )
                await asyncio.sleep(delay_s)
            # Sidecar deployments persist the gateway DB on EFS, which
            # means stale connections from a prior task run (with a
            # different awsvpc IP) survive across deploys and cause
            # permanent poll errors. Clear them before re-registering.
            try:
                await self.unregister_from_skybox()
            except Exception as e:
                logger.warning(f"Pre-registration cleanup failed: {e}")
            await self.register_with_skybox()

        stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        console.print("\n[bold]All devices running. Press Ctrl+C to stop.[/bold]\n")
        await stop_event.wait()

        if setup_skybox:
            console.print("[bold]Cleaning up gateway registrations...[/bold]")
            try:
                await self.unregister_from_skybox()
            except Exception as e:
                logger.warning(f"Failed to clean up gateway registrations: {e}")

        await self.stop()


def run_scenario(scenario_path: str, setup_skybox: bool = False) -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    runner = ScenarioRunner(scenario_path)
    asyncio.run(runner.run_forever(setup_skybox=setup_skybox))
