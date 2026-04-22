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
from pymodbus.server import ModbusTcpServer

from building_infra_sims.behaviors import ValueBehavior

logger = logging.getLogger(__name__)

# Registers written by an external client are held for this many seconds
# before the behavior loop is allowed to overwrite them again. Without this,
# a gateway that writes an override at FC06 would see the value stomped back
# within 5 seconds by the behavior loop, defeating the point of the write.
EXTERNAL_WRITE_HOLD_SECONDS = 60.0


class TrackedDataBlock(ModbusSequentialDataBlock):
    """Data block that records external (client-initiated) writes.

    Writes coming from the pymodbus request handler hit ``setValues`` and are
    recorded with a timestamp per address. The simulator's behavior loop
    bypasses tracking by calling ``set_internal`` so that scheduled updates
    don't register as external writes.
    """

    def __init__(self, address: int, values: list[int]):
        super().__init__(address, values)
        self.external_writes: dict[int, float] = {}
        self._skip_track: bool = False

    def setValues(self, address: int, values):  # type: ignore[override]
        if not self._skip_track:
            ts = time.time()
            if isinstance(values, (list, tuple)):
                for offset in range(len(values)):
                    self.external_writes[address + offset] = ts
            else:
                self.external_writes[address] = ts
        super().setValues(address, values)

    def set_internal(self, address: int, values) -> None:
        """Update register values without recording an external write."""
        self._skip_track = True
        try:
            self.setValues(address, values)
        finally:
            self._skip_track = False

    def last_write_for_range(self, address: int, count: int) -> float | None:
        """Return the most recent external-write timestamp across a range."""
        latest: float | None = None
        for offset in range(count):
            ts = self.external_writes.get(address + offset)
            if ts is not None and (latest is None or ts > latest):
                latest = ts
        return latest

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
    elif datatype in ("UINT16", "INT16", "UINT32", "INT32", "UINT64", "INT64"):
        value = int(value)

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
        self._server: ModbusTcpServer | None = None
        self._server_task: asyncio.Task | None = None
        self._behavior_task: asyncio.Task | None = None
        self._start_time: float = 0.0
        self._hr_block: TrackedDataBlock | None = None
        self._ir_block: TrackedDataBlock | None = None
        self._co_block: TrackedDataBlock | None = None
        self._di_block: TrackedDataBlock | None = None

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

        def build_block(regs: list[RegisterDefinition]) -> TrackedDataBlock:
            if not regs:
                return TrackedDataBlock(1, [0] * 100)

            max_addr = max(r.address + r.count for r in regs)
            # Pad to at least max_addr registers
            # pymodbus uses 1-based internal addressing; block address 1
            # maps to Modbus protocol address 0
            values = [0] * max(max_addr + 10, 100)

            for reg in regs:
                packed = pack_value(reg.initial_value, reg.datatype)
                for i, v in enumerate(packed):
                    values[reg.address + i] = v

            return TrackedDataBlock(1, values)

        self._hr_block = build_block(holding_regs)
        self._ir_block = build_block(input_regs)
        self._co_block = TrackedDataBlock(0, [0] * 100)
        self._di_block = TrackedDataBlock(0, [0] * 100)

        device_context = ModbusDeviceContext(
            hr=self._hr_block,
            ir=self._ir_block,
            co=self._co_block,
            di=self._di_block,
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

        # Start server — use ModbusTcpServer directly so we can shut down
        # individual servers without affecting others in the same process.
        self._server = ModbusTcpServer(
            context=self._context,
            address=(self.bind_address, self.port),
        )
        self._server_task = asyncio.create_task(self._server.serve_forever())

        logger.info(f"Modbus device '{self.device_name}' is now online")

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._behavior_task:
            self._behavior_task.cancel()
            try:
                await self._behavior_task
            except asyncio.CancelledError:
                pass

        # Shut down this specific server instance (closes TCP socket)
        if self._server:
            await self._server.shutdown()
            self._server = None

        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Modbus device '{self.device_name}' stopped")

    def _block_for(self, register_type: str) -> TrackedDataBlock | None:
        if register_type == "holding":
            return self._hr_block
        if register_type == "input":
            return self._ir_block
        return None

    def set_register(self, address: int, value: Any, datatype: str = "UINT16") -> None:
        """Update a register value programmatically (not counted as an external write)."""
        if not self._context or self._hr_block is None:
            raise RuntimeError("Simulator not started")

        packed = pack_value(value, datatype)
        self._hr_block.set_internal(address + 1, packed)

    def get_register_values(self) -> list[dict]:
        """Read current values from all registers, including write-tracking metadata."""
        if not self._context:
            return []
        results = []
        device_ctx = self._context[self.unit_id]
        for reg in self._registers:
            block = self._block_for(reg.register_type)
            last_write = (
                block.last_write_for_range(reg.address + 1, reg.count)
                if block is not None
                else None
            )
            try:
                fx = 3 if reg.register_type == "holding" else 4
                raw = device_ctx.getValues(fx, reg.address, reg.count)
                value = unpack_value(raw, reg.datatype)
                results.append({
                    "name": reg.name,
                    "value": value,
                    "units": reg.unit,
                    "datatype": reg.datatype,
                    "last_write_at": last_write,
                })
            except Exception:
                results.append({
                    "name": reg.name,
                    "value": None,
                    "units": reg.unit,
                    "datatype": reg.datatype,
                    "last_write_at": last_write,
                })
        return results

    async def _run_behaviors(self, interval: float = 5.0) -> None:
        """Periodically update register values based on their behaviors.

        Registers that received an external write within the last
        ``EXTERNAL_WRITE_HOLD_SECONDS`` are skipped so that the behavior loop
        does not immediately overwrite commanded setpoints.
        """
        while True:
            elapsed = time.monotonic() - self._start_time
            now = time.time()
            for reg in self._registers:
                if not reg.behavior:
                    continue
                block = self._block_for(reg.register_type)
                if block is not None:
                    last_write = block.last_write_for_range(reg.address + 1, reg.count)
                    if last_write is not None and (now - last_write) < EXTERNAL_WRITE_HOLD_SECONDS:
                        continue
                try:
                    new_value = reg.behavior.update(elapsed)
                    packed = pack_value(new_value, reg.datatype)
                    if block is not None:
                        block.set_internal(reg.address + 1, packed)
                    else:
                        device_ctx = self._context[self.unit_id]
                        fx = 3 if reg.register_type == "holding" else 4
                        for i, v in enumerate(packed):
                            device_ctx.setValues(fx, reg.address + i, [v])
                except Exception as e:
                    logger.warning(f"Behavior update failed for {reg.name}: {e}")
            await asyncio.sleep(interval)
