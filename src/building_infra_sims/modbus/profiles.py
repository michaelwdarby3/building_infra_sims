"""Load YAML profiles and create configured Modbus simulators."""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

import yaml

from building_infra_sims.behaviors import create_behavior
from building_infra_sims.modbus.server import ModbusDeviceSimulator

logger = logging.getLogger(__name__)


def load_profile(profile_path: str | Path) -> dict[str, Any]:
    """Load and return a Modbus device profile from YAML."""
    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")

    with open(path) as f:
        return yaml.safe_load(f)


def create_simulator_from_profile(
    profile_path: str | Path,
    port: int | None = None,
    unit_id: int | None = None,
    bind_address: str = "0.0.0.0",
) -> ModbusDeviceSimulator:
    """Load a YAML profile and return a configured ModbusDeviceSimulator."""
    profile = load_profile(profile_path)

    sim = ModbusDeviceSimulator(
        bind_address=bind_address,
        port=port or profile.get("port", 10502),
        unit_id=unit_id or profile.get("unit_id", 1),
        device_name=profile.get("name", "SimModbus"),
    )

    registers = profile.get("registers", {})

    for reg_type, reg_list in registers.items():
        for reg_cfg in reg_list:
            behavior = None
            if "behavior" in reg_cfg:
                behavior = create_behavior(reg_cfg["behavior"])

            sim.add_register(
                address=reg_cfg["address"],
                name=reg_cfg["name"],
                datatype=reg_cfg.get("datatype", "UINT16"),
                initial_value=reg_cfg.get("initial_value", 0),
                behavior=behavior,
                register_type=reg_type,
                unit=reg_cfg.get("unit", "noUnits"),
            )

    logger.info(f"Loaded Modbus profile '{profile['name']}' with {len(sim._registers)} registers")
    return sim


def run_from_profile(
    profile_path: str, port: int = 10502, unit_id: int = 1
) -> None:
    """CLI entry point: load profile, start simulator, run until interrupted."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sim = create_simulator_from_profile(profile_path, port, unit_id)

    async def _run():
        await sim.start()
        stop_event = asyncio.Event()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        logger.info("Simulator running. Press Ctrl+C to stop.")
        await stop_event.wait()
        await sim.stop()

    asyncio.run(_run())
