"""Tests for the SQLite telemetry recorder."""

import time

import pytest

from building_infra_sims.dashboard.recorder import TelemetryRecorder


@pytest.fixture
def recorder():
    r = TelemetryRecorder(":memory:")
    yield r
    r.close()


def _make_points(device="TestDevice", n=3):
    return [
        {
            "device": device,
            "point": f"Point_{i}",
            "value": 10.0 + i,
            "units": "degF",
            "protocol": "Modbus",
        }
        for i in range(n)
    ]


class TestRecordAndQuery:
    def test_record_and_get_history(self, recorder):
        recorder.record_snapshot(_make_points())
        rows = recorder.get_history(minutes=5)
        assert len(rows) == 3
        assert rows[0]["device"] == "TestDevice"
        assert rows[0]["point"].startswith("Point_")
        assert isinstance(rows[0]["value"], float)

    def test_get_history_empty(self, recorder):
        assert recorder.get_history() == []

    def test_multiple_snapshots(self, recorder):
        recorder.record_snapshot(_make_points(n=2))
        recorder.record_snapshot(_make_points(n=2))
        rows = recorder.get_history(minutes=5)
        assert len(rows) == 4

    def test_filter_by_device(self, recorder):
        recorder.record_snapshot(_make_points("DevA", 2))
        recorder.record_snapshot(_make_points("DevB", 3))
        rows = recorder.get_history(minutes=5, device="DevA")
        assert len(rows) == 2
        assert all(r["device"] == "DevA" for r in rows)

    def test_filter_by_point(self, recorder):
        recorder.record_snapshot(_make_points(n=5))
        rows = recorder.get_history(minutes=5, point="Point_2")
        assert len(rows) == 1
        assert rows[0]["point"] == "Point_2"

    def test_skips_non_numeric_values(self, recorder):
        points = [
            {"device": "D", "point": "Status", "value": "active", "units": "", "protocol": "BACnet"},
            {"device": "D", "point": "Temp", "value": 72.5, "units": "degF", "protocol": "BACnet"},
        ]
        recorder.record_snapshot(points)
        rows = recorder.get_history(minutes=5)
        assert len(rows) == 1
        assert rows[0]["point"] == "Temp"

    def test_handles_none_value(self, recorder):
        points = [{"device": "D", "point": "P", "value": None, "units": "", "protocol": "Modbus"}]
        recorder.record_snapshot(points)
        rows = recorder.get_history(minutes=5)
        assert len(rows) == 1
        assert rows[0]["value"] is None


class TestGetLatest:
    def test_latest_one_per_point(self, recorder):
        recorder.record_snapshot([
            {"device": "D", "point": "Temp", "value": 70.0, "units": "F", "protocol": "Modbus"},
            {"device": "D", "point": "Humidity", "value": 50.0, "units": "%", "protocol": "Modbus"},
        ])
        recorder.record_snapshot([
            {"device": "D", "point": "Temp", "value": 72.0, "units": "F", "protocol": "Modbus"},
            {"device": "D", "point": "Humidity", "value": 55.0, "units": "%", "protocol": "Modbus"},
        ])
        latest = recorder.get_latest()
        assert len(latest) == 2
        by_point = {r["point"]: r for r in latest}
        assert by_point["Temp"]["value"] == 72.0
        assert by_point["Humidity"]["value"] == 55.0

    def test_latest_empty(self, recorder):
        assert recorder.get_latest() == []


class TestPrune:
    def test_prune_removes_old_rows(self, recorder):
        # Insert a row with a very old timestamp
        recorder._conn.execute(
            "INSERT INTO sim_readings (timestamp, device, point, value, units, protocol) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (time.time() - 10000, "Old", "P", 1.0, "", ""),
        )
        recorder._conn.commit()

        # New snapshot triggers prune
        recorder.record_snapshot(_make_points(n=1))
        rows = recorder.get_history(minutes=9999)
        # Old row should be gone (>7200s), only new one remains
        assert len(rows) == 1
        assert rows[0]["device"] == "TestDevice"

    def test_empty_snapshot_no_op(self, recorder):
        recorder.record_snapshot([])
        assert recorder.get_history() == []
