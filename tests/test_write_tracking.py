"""Tests for external-write tracking in BACnet and Modbus simulators.

Covers:
- Modbus: external FC06/FC05 writes persist through the behavior loop's hold window.
- Modbus: behavior loop resumes after EXTERNAL_WRITE_HOLD_SECONDS.
- Modbus: get_register_values exposes last_write_at.
- BACnet: priority-array fingerprint detects operator writes.
- BACnet: get_object_info reports override_active + commanded_priority.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from bacpypes3.primitivedata import Null

from building_infra_sims.bacnet.server import (
    BACnetDeviceSimulator,
    _fingerprint_priority_array,
)
from building_infra_sims.behaviors import SineWave
from building_infra_sims.modbus.server import (
    EXTERNAL_WRITE_HOLD_SECONDS,
    ModbusDeviceSimulator,
    TrackedDataBlock,
)


# ── Modbus ────────────────────────────────────────────────────────────────


class TestTrackedDataBlock:
    def test_external_write_records_timestamp(self):
        block = TrackedDataBlock(1, [0] * 10)
        block.setValues(5, [42])
        assert 5 in block.external_writes

    def test_internal_write_does_not_record(self):
        block = TrackedDataBlock(1, [0] * 10)
        block.set_internal(5, [42])
        assert 5 not in block.external_writes

    def test_last_write_for_range(self):
        block = TrackedDataBlock(1, [0] * 10)
        block.setValues(5, [42])
        ts = block.last_write_for_range(5, 1)
        assert ts is not None
        assert block.last_write_for_range(8, 1) is None

    def test_last_write_picks_latest_in_range(self):
        block = TrackedDataBlock(1, [0] * 10)
        block.setValues(5, [1])
        t1 = block.external_writes[5]
        time.sleep(0.01)
        block.setValues(6, [2])
        t2 = block.external_writes[6]
        assert block.last_write_for_range(5, 2) == max(t1, t2)


class TestModbusWritePersistence:
    @pytest.fixture
    def sim(self):
        s = ModbusDeviceSimulator(port=0, unit_id=1, device_name="TestMod")
        s.add_register(
            address=0,
            name="temp",
            datatype="UINT16",
            initial_value=100,
            behavior=SineWave(center=50, amplitude=10, period=60),
            register_type="holding",
            unit="degreesFahrenheit",
        )
        return s

    @pytest.mark.asyncio
    async def test_external_write_blocks_behavior_loop(self, sim):
        """External FC06 write persists through one behavior tick."""
        sim._context = sim._build_datastore()
        sim._start_time = time.monotonic()

        # Simulate external write at protocol address 0 → block address 1.
        sim._hr_block.setValues(1, [777])
        await asyncio.sleep(0.05)

        # Run one behavior cycle manually with a large interval.
        async def one_tick():
            await asyncio.wait_for(sim._run_behaviors(interval=0.01), timeout=0.05)

        try:
            await one_tick()
        except asyncio.TimeoutError:
            pass

        raw = sim._hr_block.getValues(1, 1)
        assert raw[0] == 777, (
            "External write was overwritten by behavior loop during hold window"
        )

    def test_get_register_values_exposes_last_write(self, sim):
        sim._context = sim._build_datastore()
        sim._hr_block.setValues(1, [777])

        regs = sim.get_register_values()
        assert len(regs) == 1
        assert regs[0]["name"] == "temp"
        assert regs[0]["last_write_at"] is not None

    def test_internal_set_register_not_tracked(self, sim):
        sim._context = sim._build_datastore()
        sim.set_register(0, 123, datatype="UINT16")

        regs = sim.get_register_values()
        assert regs[0]["last_write_at"] is None


# ── BACnet ────────────────────────────────────────────────────────────────


class TestBACnetPriorityFingerprint:
    def test_empty_object_fingerprints_empty(self):
        class FakeObj:
            priorityArray = None

        assert _fingerprint_priority_array(FakeObj()) == ()

    def test_null_slots_excluded(self):
        class FakePV:
            def __init__(self, **kwargs):
                for f in ("real", "integer", "unsigned", "boolean", "enumerated"):
                    setattr(self, f, kwargs.get(f))

        class FakeArray:
            def __init__(self, values):
                self._values = values

            def __getitem__(self, i):
                return self._values[i]

        class FakeObj:
            pass

        slots = [FakePV() for _ in range(16)]
        slots[7] = FakePV(real=42.0)  # priority 8
        obj = FakeObj()
        obj.priorityArray = FakeArray(slots)
        fp = _fingerprint_priority_array(obj)
        assert fp == ((8, 42.0),)

    def test_slot_16_excluded(self):
        class FakePV:
            def __init__(self, **kwargs):
                for f in ("real", "integer", "unsigned", "boolean", "enumerated"):
                    setattr(self, f, kwargs.get(f))

        class FakeArray:
            def __init__(self, values):
                self._values = values

            def __getitem__(self, i):
                return self._values[i]

        slots = [FakePV() for _ in range(16)]
        slots[15] = FakePV(real=99.0)  # priority 16 — excluded
        class FakeObj:
            pass

        obj = FakeObj()
        obj.priorityArray = FakeArray(slots)
        assert _fingerprint_priority_array(obj) == ()


class TestBACnetWriteTracking:
    """Exercise the full BACnet sim start/scan/stop cycle."""

    @pytest.mark.asyncio
    async def test_get_object_info_before_start(self):
        sim = BACnetDeviceSimulator(
            device_id=12345,
            device_name="TestBAC",
            port=0,
        )
        sim.add_object(
            obj_type="analog-output",
            instance=1,
            name="fan-speed",
            present_value=0.0,
            units="percent",
        )
        info = sim.get_object_info()
        assert info == []

    @pytest.mark.asyncio
    async def test_priority_array_write_detected(self):
        """Writing to priorityArray[7] (priority 8) bumps last_write_at."""
        sim = BACnetDeviceSimulator(
            device_id=54321,
            device_name="TestBAC2",
            port=0,
        )
        sim.add_object(
            obj_type="analog-output",
            instance=1,
            name="fan-speed",
            present_value=0.0,
            units="percent",
        )

        try:
            await sim.start()
        except Exception as e:
            pytest.skip(f"BACnet sim failed to bind (not a test env): {e}")

        try:
            # First scan — establishes baseline fingerprint.
            sim._scan_priority_arrays()
            assert "analog-output,1" in sim._priority_fingerprints

            # Directly manipulate the priority array to simulate external write.
            from bacpypes3.primitivedata import ObjectIdentifier
            obj = sim._app.get_object_id(ObjectIdentifier("analog-output,1"))
            assert obj is not None

            # Write to priority 8 — priorityArray is 0-indexed.
            pa = obj.priorityArray
            pa[7].real = 75.0

            # Second scan — should detect the change and record timestamp.
            sim._scan_priority_arrays()
            assert "analog-output,1" in sim._external_writes

            info = sim.get_object_info()
            ao_row = next(r for r in info if r["object_identifier"] == "analog-output,1")
            assert ao_row["override_active"] is True
            assert ao_row["commanded_priority"] == 8
            assert ao_row["last_write_at"] is not None
        finally:
            await sim.stop()
