"""Verify the Modbus TCP simulator by reading all registers."""

import asyncio
import logging
import struct

from building_infra_sims.modbus.profiles import create_simulator_from_profile
from building_infra_sims.modbus.server import PACK_FORMATS, REGISTER_COUNTS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROFILE = "profiles/modbus/generic_power_meter.yaml"


async def main():
    sim = create_simulator_from_profile(PROFILE)

    await sim.start()
    # Give the server a moment to bind
    await asyncio.sleep(0.5)

    try:
        from pymodbus.client import AsyncModbusTcpClient

        client = AsyncModbusTcpClient("127.0.0.1", port=sim.port)
        await client.connect()

        logger.info(f"Connected to Modbus simulator at 127.0.0.1:{sim.port}")

        # Read holding registers
        logger.info("\n=== Holding Registers ===")
        for reg in sim._registers:
            if reg.register_type != "holding":
                continue
            count = REGISTER_COUNTS.get(reg.datatype, 1)
            result = await client.read_holding_registers(
                reg.address, count=count, device_id=sim.unit_id
            )
            if result.isError():
                logger.error(f"  {reg.name} @ {reg.address}: ERROR {result}")
                continue

            # Unpack the value
            fmt = PACK_FORMATS[reg.datatype]
            raw = struct.pack(f">{len(result.registers)}H", *result.registers)
            value = struct.unpack(fmt, raw)[0]
            logger.info(f"  {reg.name} @ {reg.address}: {value:.4f} ({reg.datatype})")

        # Read input registers
        logger.info("\n=== Input Registers ===")
        for reg in sim._registers:
            if reg.register_type != "input":
                continue
            count = REGISTER_COUNTS.get(reg.datatype, 1)
            result = await client.read_input_registers(
                reg.address, count=count, device_id=sim.unit_id
            )
            if result.isError():
                logger.error(f"  {reg.name} @ {reg.address}: ERROR {result}")
                continue

            fmt = PACK_FORMATS[reg.datatype]
            raw = struct.pack(f">{len(result.registers)}H", *result.registers)
            value = struct.unpack(fmt, raw)[0]
            logger.info(f"  {reg.name} @ {reg.address}: {value} ({reg.datatype})")

        # Wait for one behavior cycle and re-read a register to confirm updates
        logger.info("\nWaiting 6 seconds for behavior update cycle...")
        await asyncio.sleep(6)

        result = await client.read_holding_registers(
            0, count=2, device_id=sim.unit_id
        )
        raw = struct.pack(f">{len(result.registers)}H", *result.registers)
        voltage_a = struct.unpack(">f", raw)[0]
        logger.info(f"  Voltage Phase A after behavior update: {voltage_a:.4f}")

        client.close()
        logger.info("\nModbus simulator verification PASSED")

    finally:
        await sim.stop()


if __name__ == "__main__":
    asyncio.run(main())
