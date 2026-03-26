"""SQLite-backed telemetry recorder for local simulator data."""

import sqlite3
import time


class TelemetryRecorder:
    """Records simulator telemetry snapshots to SQLite."""

    def __init__(self, db_path: str = ":memory:"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sim_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device TEXT NOT NULL,
                point TEXT NOT NULL,
                value REAL,
                units TEXT,
                protocol TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_time
            ON sim_readings(timestamp)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_device_point
            ON sim_readings(device, point)
        """)
        self._conn.commit()

    def record_snapshot(self, points: list[dict]) -> None:
        """Bulk-insert a telemetry snapshot with current timestamp."""
        if not points:
            return
        ts = time.time()
        rows = []
        for p in points:
            value = p.get("value")
            if value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            rows.append((
                ts,
                p.get("device", ""),
                p.get("point", ""),
                value,
                p.get("units", ""),
                p.get("protocol", ""),
            ))
        self._conn.executemany(
            "INSERT INTO sim_readings (timestamp, device, point, value, units, protocol) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        self._prune()

    def get_history(
        self,
        minutes: int = 60,
        device: str | None = None,
        point: str | None = None,
    ) -> list[dict]:
        """Query readings within the last N minutes."""
        cutoff = time.time() - (minutes * 60)
        sql = "SELECT timestamp, device, point, value, units, protocol FROM sim_readings WHERE timestamp > ?"
        params: list = [cutoff]
        if device:
            sql += " AND device = ?"
            params.append(device)
        if point:
            sql += " AND point = ?"
            params.append(point)
        sql += " ORDER BY timestamp DESC LIMIT 5000"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_latest(self) -> list[dict]:
        """Most recent reading per (device, point)."""
        rows = self._conn.execute("""
            SELECT r.timestamp, r.device, r.point, r.value, r.units, r.protocol
            FROM sim_readings r
            INNER JOIN (
                SELECT device, point, MAX(timestamp) AS max_ts
                FROM sim_readings
                GROUP BY device, point
            ) latest ON r.device = latest.device
                    AND r.point = latest.point
                    AND r.timestamp = latest.max_ts
            ORDER BY r.device, r.point
        """).fetchall()
        return [dict(r) for r in rows]

    def _prune(self, max_age_seconds: float = 7200.0) -> None:
        """Drop rows older than max_age_seconds (default 2 hours)."""
        cutoff = time.time() - max_age_seconds
        self._conn.execute("DELETE FROM sim_readings WHERE timestamp < ?", (cutoff,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
