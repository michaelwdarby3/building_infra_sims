#!/usr/bin/env python3
"""Verify a BACnet device is discoverable and readable on the local network.

Uses BAC0 as a client to:
1. Send Who-Is and discover devices
2. Read object lists from discovered devices
3. Read presentValue from each object
"""

import asyncio
import sys
import time

import BAC0
from BAC0.core.io.IOExceptions import ReadPropertyException


async def main():
    target_ip = sys.argv[1] if len(sys.argv) > 1 else None

    print("Starting BAC0 client for BACnet device verification...")
    bacnet = BAC0.lite()

    # Give the network a moment to settle
    await asyncio.sleep(2)

    print("\nDiscovering BACnet devices (Who-Is)...")
    bacnet.discover()
    await asyncio.sleep(3)

    devices = bacnet.discoveredDevices
    if not devices:
        print("No BACnet devices discovered on the network.")
        print("Make sure:")
        print("  - The simulator is running on the same subnet")
        print("  - UDP port 47808 is not blocked by firewall")
        print("  - You're on the same VLAN/broadcast domain")
        bacnet.disconnect()
        return

    print(f"\nFound {len(devices)} device(s):")
    for addr, dev_id in devices.items():
        print(f"  Device {dev_id} at {addr}")

    # If a target IP was specified, filter to just that device
    for addr, dev_id in devices.items():
        if target_ip and target_ip not in str(addr):
            continue

        print(f"\n{'='*60}")
        print(f"Reading device {dev_id} at {addr}")
        print(f"{'='*60}")

        try:
            device_name = bacnet.read(f"{addr} device {dev_id} objectName")
            vendor = bacnet.read(f"{addr} device {dev_id} vendorName")
            model = bacnet.read(f"{addr} device {dev_id} modelName")
            print(f"  Name: {device_name}")
            print(f"  Vendor: {vendor}")
            print(f"  Model: {model}")
        except Exception as e:
            print(f"  Could not read device properties: {e}")
            continue

        try:
            object_list = bacnet.read(f"{addr} device {dev_id} objectList")
            print(f"\n  Objects ({len(object_list)}):")

            for obj_id in object_list:
                obj_type, instance = str(obj_id).split(",") if "," in str(obj_id) else (str(obj_id), "")
                # Skip device and network-port objects
                if obj_type in ("device", "network-port"):
                    continue

                try:
                    name = bacnet.read(f"{addr} {obj_type} {instance} objectName")
                    value = bacnet.read(f"{addr} {obj_type} {instance} presentValue")
                    units = ""
                    if obj_type.startswith("analog"):
                        try:
                            units = bacnet.read(f"{addr} {obj_type} {instance} units")
                        except Exception:
                            pass
                    print(f"    {obj_type},{instance}: {name} = {value} {units}")
                except Exception as e:
                    print(f"    {obj_type},{instance}: ERROR - {e}")

        except Exception as e:
            print(f"  Could not read object list: {e}")

    bacnet.disconnect()
    print("\nVerification complete.")


if __name__ == "__main__":
    asyncio.run(main())
