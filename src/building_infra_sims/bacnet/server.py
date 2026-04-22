"""BACnet/IP device simulator built on BACpypes3."""

import asyncio
import copy
import logging
import socket
import time
from typing import Any

from bacpypes3.app import Application
from bacpypes3.primitivedata import ObjectIdentifier

from building_infra_sims.bacnet.objects import (
    BACNET_OBJECT_MAP,
    COMMANDABLE_TYPES,
    create_bacnet_object,
    create_commandable_object,
)
from building_infra_sims.behaviors import ValueBehavior

logger = logging.getLogger(__name__)


# Priority-array fingerprint helpers. A commandable object in bacpypes3 exposes a
# 16-slot priorityArray where slot N (1-based) holds the value commanded at
# priority N (or `null` when that priority is free). The object's effective
# present-value is the value at the lowest (highest-priority) non-null slot,
# or the relinquishDefault if all 16 are null.
_PRIORITY_VALUE_FIELDS = ("real", "integer", "unsigned", "boolean", "enumerated")


def _priority_slot_value(priority_value) -> Any:
    """Extract the active choice from a PriorityValue, or None if null."""
    for field in _PRIORITY_VALUE_FIELDS:
        val = getattr(priority_value, field, None)
        if val is not None:
            return val
    return None


def _fingerprint_priority_array(obj) -> tuple[tuple[int, Any], ...]:
    """Capture the non-null slots 1..15 of a commandable object's priority array.

    Slot 16 (relinquish default / local writes) is excluded so the behavior loop
    setting ``.presentValue`` each tick does not register as an external write.
    """
    pa = getattr(obj, "priorityArray", None)
    if pa is None:
        return ()
    slots: list[tuple[int, Any]] = []
    for priority in range(1, 16):
        try:
            pv = pa[priority - 1]
        except (IndexError, Exception):
            continue
        val = _priority_slot_value(pv)
        if val is not None:
            slots.append((priority, val))
    return tuple(slots)


def _get_local_ip() -> str:
    """Auto-detect the local IP address on the LAN."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.0.0.1", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _get_subnet_mask(ip: str) -> str:
    """Get the subnet mask for the interface with the given IP."""
    try:
        import subprocess

        result = subprocess.run(
            ["ip", "-o", "-4", "addr", "show"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if ip in line:
                cidr = line.split("inet ")[1].split(" ")[0]
                prefix = int(cidr.split("/")[1])
                mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
                return f"{(mask >> 24) & 0xFF}.{(mask >> 16) & 0xFF}.{(mask >> 8) & 0xFF}.{mask & 0xFF}"
    except Exception:
        pass
    return "255.255.255.0"


class BACnetDeviceSimulator:
    """A simulated BACnet/IP device.

    Non-commandable objects (inputs) go through Application.from_json().
    Commandable objects (outputs) are added programmatically after creation
    due to a BACpypes3 limitation with json_to_sequence and the Commandable mixin.
    """

    def __init__(
        self,
        device_id: int,
        device_name: str,
        ip_address: str | None = None,
        port: int = 47808,
        vendor_id: int = 999,
        vendor_name: str = "BuildingSim",
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.ip_address = ip_address or _get_local_ip()
        self.subnet_mask = _get_subnet_mask(self.ip_address)
        self.port = port
        self.vendor_id = vendor_id
        self.vendor_name = vendor_name

        self._object_defs: list[dict[str, Any]] = []
        self._behaviors: dict[str, ValueBehavior] = {}
        self._app: Application | None = None
        self._behavior_task: asyncio.Task | None = None
        self._start_time: float = 0.0
        # Per-object external-write tracking. A "write" is any change to
        # priority-array slots 1..15 between behavior ticks (slot 16 is the
        # relinquish default / local writes, so it's excluded).
        self._external_writes: dict[str, float] = {}
        self._priority_fingerprints: dict[str, tuple[tuple[int, Any], ...]] = {}

    def add_object(
        self,
        obj_type: str,
        instance: int,
        name: str,
        present_value: Any = None,
        units: str | None = None,
        description: str | None = None,
        behavior: ValueBehavior | None = None,
        **kwargs,
    ) -> None:
        """Add a BACnet object to the simulator."""
        obj_def = create_bacnet_object(
            obj_type=obj_type,
            instance=instance,
            name=name,
            present_value=present_value,
            units=units,
            description=description,
            **kwargs,
        )
        self._object_defs.append(obj_def)

        if behavior:
            key = f"{obj_type},{instance}"
            self._behaviors[key] = behavior

    def _build_application_json(self) -> list[dict[str, Any]]:
        """Build the JSON config for Application.from_json().

        Only includes device, network-port, and non-commandable objects.
        Commandable objects are added after app creation.
        """
        object_list = [
            f"device,{self.device_id}",
            "network-port,1",
        ]
        for obj_def in self._object_defs:
            object_list.append(obj_def["object-identifier"])

        device_obj = {
            "object-type": "device",
            "object-identifier": f"device,{self.device_id}",
            "object-name": self.device_name,
            "vendor-identifier": self.vendor_id,
            "vendor-name": self.vendor_name,
            "model-name": "BACnet Simulator",
            "firmware-revision": "0.1.0",
            "application-software-version": "0.1.0",
            "protocol-version": 1,
            "protocol-revision": 22,
            "system-status": "operational",
            "max-apdu-length-accepted": 1024,
            "segmentation-supported": "segmented-both",
            "max-segments-accepted": 16,
            "apdu-timeout": 3000,
            "number-of-apdu-retries": 3,
            "apdu-segment-timeout": 1000,
            "database-revision": 1,
            "object-list": object_list,
            "device-address-binding": [],
            "active-cov-subscriptions": [],
            "status-flags": [],
            "property-list": [
                "object-identifier",
                "object-name",
                "object-type",
                "property-list",
                "system-status",
                "vendor-name",
                "vendor-identifier",
                "model-name",
                "firmware-revision",
                "application-software-version",
                "protocol-version",
                "protocol-revision",
                "protocol-services-supported",
                "protocol-object-types-supported",
                "object-list",
                "max-apdu-length-accepted",
                "segmentation-supported",
                "max-segments-accepted",
                "local-time",
                "local-date",
                "apdu-segment-timeout",
                "apdu-timeout",
                "number-of-apdu-retries",
                "device-address-binding",
                "database-revision",
                "active-cov-subscriptions",
                "status-flags",
            ],
            "protocol-services-supported": [
                "acknowledge-alarm",
                "confirmed-cov-notification",
                "confirmed-event-notification",
                "subscribe-cov",
                "read-property",
                "read-property-multiple",
                "write-property",
                "write-property-multiple",
            ],
            "protocol-object-types-supported": [],
        }

        network_port_obj = {
            "object-type": "network-port",
            "object-identifier": "network-port,1",
            "object-name": "NetworkPort-1",
            "network-type": "ipv4",
            "protocol-level": "bacnet-application",
            "network-number": 1,
            "network-number-quality": "unknown",
            "bacnet-ip-mode": "normal",
            "ip-address": self.ip_address,
            "bacnet-ip-udp-port": self.port,
            "ip-subnet-mask": self.subnet_mask,
            "link-speed": 0.0,
            "changes-pending": False,
            "out-of-service": False,
            "reliability": "no-fault-detected",
            "status-flags": [],
            "property-list": [
                "object-identifier",
                "object-name",
                "object-type",
                "property-list",
                "status-flags",
                "reliability",
                "out-of-service",
                "network-type",
                "protocol-level",
                "network-number",
                "network-number-quality",
                "changes-pending",
                "mac-address",
                "link-speed",
                "bacnet-ip-mode",
                "ip-address",
                "bacnet-ip-udp-port",
                "ip-subnet-mask",
            ],
            "bbmd-broadcast-distribution-table": [],
            "bbmd-accept-f-d-registrations": False,
            "bbmd-foreign-device-table": [],
        }

        # Non-commandable objects go in the JSON config
        # Deep copy because Application.from_json() mutates the input dicts
        non_cmd_objects = [
            copy.deepcopy(o) for o in self._object_defs if o["object-type"] not in COMMANDABLE_TYPES
        ]

        return [device_obj, network_port_obj] + non_cmd_objects

    def _add_commandable_objects(self) -> None:
        """Add commandable objects (outputs) programmatically after app creation."""
        for obj_def in self._object_defs:
            if obj_def["object-type"] not in COMMANDABLE_TYPES:
                continue

            obj = create_commandable_object(obj_def)
            self._app.add_object(obj)
            logger.debug(f"Added commandable object: {obj_def['object-identifier']}")

    async def start(self) -> None:
        """Start the BACnet application and begin responding to network requests."""
        logger.info(
            f"Starting BACnet device '{self.device_name}' "
            f"(ID={self.device_id}) at {self.ip_address}:{self.port} "
            f"with {len(self._object_defs)} objects"
        )

        json_config = self._build_application_json()
        self._app = Application.from_json(json_config)

        # Add commandable objects programmatically
        self._add_commandable_objects()

        self._start_time = time.monotonic()

        if self._behaviors:
            self._behavior_task = asyncio.create_task(self._run_behaviors())

        logger.info(f"BACnet device '{self.device_name}' is now online")

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._behavior_task:
            self._behavior_task.cancel()
            try:
                await self._behavior_task
            except asyncio.CancelledError:
                pass

        if self._app:
            self._app.close()
            self._app = None

        logger.info(f"BACnet device '{self.device_name}' stopped")

    def set_value(self, obj_type: str, instance: int, value: Any) -> None:
        """Update a point's presentValue."""
        if not self._app:
            raise RuntimeError("Simulator not started")

        oid = ObjectIdentifier(f"{obj_type},{instance}")
        obj = self._app.get_object_id(oid)
        if obj is None:
            raise ValueError(f"Object {obj_type},{instance} not found")

        obj.presentValue = value

    def _scan_priority_arrays(self) -> None:
        """Check every commandable object for priority-array changes.

        Called at the start of each behavior tick. If an object's fingerprint
        (non-null slots 1..15) has changed since the last tick, record the
        current wall-clock time as the last external-write timestamp for that
        object. Slot 16 is excluded, so the behavior loop's own writes — which
        set ``presentValue`` and land at priority 16 — do not register.
        """
        if self._app is None:
            return
        for obj_def in self._object_defs:
            if obj_def["object-type"] not in COMMANDABLE_TYPES:
                continue
            key = obj_def["object-identifier"]
            try:
                oid = ObjectIdentifier(key)
                obj = self._app.get_object_id(oid)
            except Exception:
                continue
            if obj is None:
                continue
            fingerprint = _fingerprint_priority_array(obj)
            previous = self._priority_fingerprints.get(key)
            if previous is not None and fingerprint != previous:
                self._external_writes[key] = time.time()
            self._priority_fingerprints[key] = fingerprint

    def get_object_info(self) -> list[dict[str, Any]]:
        """Return per-object state including override / last-write metadata."""
        if self._app is None:
            return []
        info: list[dict[str, Any]] = []
        for obj_def in self._object_defs:
            key = obj_def["object-identifier"]
            try:
                oid = ObjectIdentifier(key)
                obj = self._app.get_object_id(oid)
            except Exception:
                obj = None
            present_value = None
            override_active = False
            commanded_priority: int | None = None
            if obj is not None:
                try:
                    present_value = obj.presentValue
                except Exception:
                    present_value = None
                if obj_def["object-type"] in COMMANDABLE_TYPES:
                    fingerprint = _fingerprint_priority_array(obj)
                    if fingerprint:
                        override_active = True
                        commanded_priority = fingerprint[0][0]
            info.append({
                "name": obj_def.get("object-name"),
                "object_type": obj_def["object-type"],
                "object_identifier": key,
                "present_value": present_value,
                "units": obj_def.get("units"),
                "last_write_at": self._external_writes.get(key),
                "override_active": override_active,
                "commanded_priority": commanded_priority,
            })
        return info

    async def _run_behaviors(self, interval: float = 5.0) -> None:
        """Periodically update object values based on their behaviors."""
        while True:
            self._scan_priority_arrays()
            elapsed = time.monotonic() - self._start_time
            for key, behavior in self._behaviors.items():
                try:
                    new_value = behavior.update(elapsed)
                    oid = ObjectIdentifier(key)
                    obj = self._app.get_object_id(oid)
                    if obj is not None:
                        obj.presentValue = new_value
                except Exception as e:
                    logger.warning(f"Behavior update failed for {key}: {e}")
            await asyncio.sleep(interval)
