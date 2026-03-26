"""Modbus TCP device simulator built on pymodbus."""

import asyncio
import logging
import struct
import time
from typing import Any

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer

from building_infra_sims.behaviors import ValueBehavior

logger = logging.getLogger(__name__)

# Number of 16-bit registers needed for each data type
REGISTER_COUNTS = {
    "UINT16": 1,
    "INT16": 1,
    "FLOAT32": 2,
    "UINT32": 2,
    "INT32": 2,
    "FLOAT64": 4,
    "UINT64": 4,
    "INT64": 4,
    "BOOL": 1,
}

# struct format strings for packing values into 16-bit registers
PACK_FORMATS = {
    "UINT16": ">H",
    "INT16": ">h",
    "FLOAT32": ">f",
    "UINT32": ">I",
    "INT32": ">i",
    "FLOAT64": ">d",
    "UINT64": ">Q",
    "INT64": ">q",
    "BOOL": ">H",
}


def pack_value(value: Any, datatype: str) -> list[int]:
    """Pack a value into a list of 16-bit register values."""
    fmt = PACK_FORMATS.get(datatype)
    if not fmt:
        raise ValueError(f"Unknown datatype: {datatype}")

    if datatype == "BOOL":
        value = 1 if value else 0

    packed = struct.pack(fmt, value)
    # Convert to list of 16-bit unsigned integers
    return list(struct.unpack(f">{len(packed) // 2}H", packed))


def unpack_value(registers: list[int], datatype: str) -> Any:
    """Unpack 16-bit register values back to a typed value."""
    fmt = PACK_FORMATS.get(datatype)
    if not fmt:
        raise ValueError(f"Unknown datatype: {datatype}")

    # Convert list of 16-bit ints to bytes
    packed = struct.pack(f">{len(registers)}H", *registers)
    result = struct.unpack(fmt, packed)[0]

    if datatype == "BOOL":
        return bool(result)
    return result


class RegisterDefinition:
    """Describes a named register in the Modbus address space."""

    def __init__(
        self,
        address: int,
        name: str,
        datatype: str = "UINT16",
        initial_value: Any = 0,
        behavior: ValueBehavior | None = None,
        register_type: str = "holding",
        unit: str = "noUnits",
    ):
        self.address = address
        self.name = name
        self.datatype = datatype
        self.initial_value = initial_value
        self.behavior = behavior
        self.register_type = register_type
        self.unit = unit
        self.count = REGISTER_COUNTS.get(datatype, 1)


class ModbusDeviceSimulator:
    """A simulated Modbus TCP device."""

    def __init__(
        self,
        bind_address: str = "0.0.0.0",
        port: int = 10502,
        unit_id: int = 1,
        device_name: str = "SimModbus",
    ):
        self.bind_address = bind_address
        self.port = port
        self.unit_id = unit_id
        self.device_name = device_name

        self._registers: list[RegisterDefinition] = []
        self._context: ModbusServerContext | None = None
        self._server_task: asyncio.Task | None = None
        self._behavior_task: asyncio.Task | None = None
        self._start_time: float = 0.0

    def add_register(
        self,
        address: int,
        name: str,
        datatype: str = "UINT16",
        initial_value: Any = 0,
        behavior: ValueBehavior | None = None,
        register_type: str = "holding",
        unit: str = "noUnits",
    ) -> None:
        """Add a register definition."""
        self._registers.append(
            RegisterDefinition(
                address=address,
                name=name,
                datatype=datatype,
                initial_value=initial_value,
                behavior=behavior,
                register_type=register_type,
                unit=unit,
            )
        )

    def _build_datastore(self) -> ModbusServerContext:
        """Build the pymodbus datastore from register definitions."""
        # Find the max address for each register type to size the data blocks
        holding_regs = [r for r in self._registers if r.register_type == "holding"]
        input_regs = [r for r in self._registers if r.register_type == "input"]

        def build_block(regs: list[RegisterDefinition]) -> ModbusSequentialDataBlock:
            if not regs:
                return ModbusSequentialDataBlock(1, [0] * 100)

            max_addr = max(r.address + r.count for r in regs)
            # Pad to at least max_addr registers
            # pymodbus uses 1-based internal addressing; block address 1
            # maps to Modbus protocol address 0
            values = [0] * max(max_addr + 10, 100)

            for reg in regs:
                packed = pack_value(reg.initial_value, reg.datatype)
                for i, v in enumerate(packed):
                    values[reg.address + i] = v

            return ModbusSequentialDataBlock(1, values)

        device_context = ModbusDeviceContext(
            hr=build_block(holding_regs),
            ir=build_block(input_regs),
            co=ModbusSequentialDataBlock(0, [0] * 100),
            di=ModbusSequentialDataBlock(0, [0] * 100),
        )

        return ModbusServerContext(
            devices={self.unit_id: device_context},
            single=False,
        )

    async def start(self) -> None:
        """Start the Modbus TCP server."""
        self._context = self._build_datastore()
        self._start_time = time.monotonic()

        logger.info(
            f"Starting Modbus device '{self.device_name}' "
            f"(unit={self.unit_id}) at {self.bind_address}:{self.port} "
            f"with {len(self._registers)} registers"
        )

        # Start behavior update loop
        behaviors = [r for r in self._registers if r.behavior]
        if behaviors:
            self._behavior_task = asyncio.create_task(self._run_behaviors())

        # Start server in background task
        self._server_task = asyncio.create_task(
            StartAsyncTcpServer(
                context=self._context,
                address=(self.bind_address, self.port),
            )
        )

        logger.info(f"Modbus device '{self.device_name}' is now online")

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._behavior_task:
            self._behavior_task.cancel()
            try:
                await self._behavior_task
            except asyncio.CancelledError:
                pass

        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Modbus device '{self.device_name}' stopped")

    def set_register(self, address: int, value: Any, datatype: str = "UINT16") -> None:
        """Update a register value."""
        if not self._context:
            raise RuntimeError("Simulator not started")

        packed = pack_value(value, datatype)
        device_ctx = self._context[self.unit_id]
        for i, v in enumerate(packed):
            device_ctx.setValues(3, address + i, [v])  # 3 = holding registers

    async def _run_behaviors(self, interval: float = 5.0) -> None:
        """Periodically update register values based on their behaviors."""
        while True:
            elapsed = time.monotonic() - self._start_time
            for reg in self._registers:
                if not reg.behavior:
                    continue
                try:
                    new_value = reg.behavior.update(elapsed)
                    packed = pack_value(new_value, reg.datatype)
                    device_ctx = self._context[self.unit_id]
                    fx = 3 if reg.register_type == "holding" else 4
                    for i, v in enumerate(packed):
                        device_ctx.setValues(fx, reg.address + i, [v])
                except Exception as e:
                    logger.warning(f"Behavior update failed for {reg.name}: {e}")
            await asyncio.sleep(interval)
