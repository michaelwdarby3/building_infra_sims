"""Load YAML profiles and create configured BACnet simulators."""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

import yaml

from building_infra_sims.bacnet.server import BACnetDeviceSimulator
from building_infra_sims.behaviors import create_behavior

logger = logging.getLogger(__name__)


def load_profile(profile_path: str | Path) -> dict[str, Any]:
    """Load and return a BACnet device profile from YAML."""
    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")

    with open(path) as f:
        return yaml.safe_load(f)


def create_simulator_from_profile(
    profile_path: str | Path,
    device_id: int | None = None,
    ip_address: str | None = None,
    port: int | None = None,
) -> BACnetDeviceSimulator:
    """Load a YAML profile and return a configured BACnetDeviceSimulator."""
    profile = load_profile(profile_path)

    dev_id = device_id or profile.get("device_id", 1000)
    dev_port = port or profile.get("port", 47808)

    sim = BACnetDeviceSimulator(
        device_id=dev_id,
        device_name=profile.get("name", f"SimDevice-{dev_id}"),
        ip_address=ip_address,
        port=dev_port,
        vendor_name=profile.get("vendor_name", "BuildingSim"),
    )

    for obj_cfg in profile.get("objects", []):
        behavior = None
        if "behavior" in obj_cfg:
            behavior = create_behavior(obj_cfg["behavior"])

        # Accept both "type"/"object_type" and "initial_value"/"present_value"
        obj_type = obj_cfg.get("type") or obj_cfg.get("object_type")
        pv = obj_cfg.get("initial_value") or obj_cfg.get("present_value")

        sim.add_object(
            obj_type=obj_type,
            instance=obj_cfg["instance"],
            name=obj_cfg["name"],
            present_value=pv,
            units=obj_cfg.get("units"),
            description=obj_cfg.get("description"),
            behavior=behavior,
            states=obj_cfg.get("states", []),
        )

    logger.info(f"Loaded profile '{profile['name']}' with {len(profile.get('objects', []))} objects")
    return sim


def run_from_profile(profile_path: str, device_id: int, ip_address: str | None = None) -> None:
    """CLI entry point: load profile, start simulator, run until interrupted."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sim = create_simulator_from_profile(profile_path, device_id, ip_address)

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
