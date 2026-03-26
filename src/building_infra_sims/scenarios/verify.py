"""End-to-end verification: confirm simulated data flows through the gateway."""

import asyncio
import logging
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from building_infra_sims.scenarios.runner import ScenarioRunner

logger = logging.getLogger(__name__)
console = Console()


class E2EVerifier:
    """Verify that the gateway is polling simulators and recording telemetry."""

    def __init__(self, settle_time: int = 30):
        self.settle_time = settle_time

    async def verify(self, runner: ScenarioRunner) -> bool:
        """Run full verification against a started and registered scenario.

        Returns True if all checks pass.
        """
        from building_infra_sims.config import settings
        from building_infra_sims.skybox.client import SkyboxClient

        url = settings.skybox_base_url
        user = settings.skybox_username
        pwd = settings.skybox_password

        if not user or not pwd:
            console.print("[red]Gateway credentials not configured[/red]")
            return False

        async with SkyboxClient(url, user, pwd) as sb:
            await sb.sign_in()

            # Check connections exist
            conns = await sb.list_connections()
            sim_conns = [c for c in conns.items if c.name.startswith("Sim: ")]
            expected_count = len(runner._bacnet_sims) + len(runner._modbus_sims)

            console.print(
                f"\n[bold]Connections:[/bold] {len(sim_conns)} of "
                f"{expected_count} expected"
            )

            if not sim_conns:
                console.print("[red]No simulated connections found in gateway[/red]")
                return False

            # Check points are configured for each connection
            console.print("\n[bold]Checking points per connection...[/bold]")
            conn_points = {}
            for c in sim_conns:
                if not c.id:
                    continue
                try:
                    points = await sb.list_points(c.id)
                    conn_points[c.name] = points.total
                except Exception as e:
                    conn_points[c.name] = f"error: {e}"

            points_table = Table(title="Connection Points")
            points_table.add_column("Connection", style="bold")
            points_table.add_column("Points", style="green")
            points_table.add_column("Status")

            for name, count in conn_points.items():
                if isinstance(count, int) and count > 0:
                    status = "[green]OK[/green]"
                elif isinstance(count, int) and count == 0:
                    status = "[yellow]No points[/yellow]"
                else:
                    status = f"[red]{count}[/red]"
                points_table.add_row(name, str(count), status)

            console.print(points_table)

            # Wait for gateway to poll
            console.print(
                f"\n[bold]Waiting {self.settle_time}s for gateway to poll...[/bold]"
            )
            await asyncio.sleep(self.settle_time)

            # Check telemetry
            telemetry = await sb.get_telemetry()
            console.print(
                f"\n[bold]Telemetry:[/bold] {telemetry.total_points} data points"
            )

            # Check SQL for sensor_readings
            row_count_before = await self._get_reading_count(sb)
            console.print(
                f"[bold]Sensor readings in DB:[/bold] {row_count_before} rows"
            )

            # Wait a bit more and check again to confirm data is accumulating
            if row_count_before > 0:
                console.print(
                    "\n[bold]Waiting 15s to confirm data accumulation...[/bold]"
                )
                await asyncio.sleep(15)
                row_count_after = await self._get_reading_count(sb)
                new_rows = row_count_after - row_count_before
                console.print(
                    f"[bold]New rows in 15s:[/bold] {new_rows}"
                )
            else:
                row_count_after = row_count_before
                new_rows = 0

            # Get fresh telemetry for the report
            telemetry = await sb.get_telemetry()

            # Build results
            results = self._build_results(
                runner, sim_conns, conn_points, telemetry, row_count_after, new_rows
            )
            self._print_report(results)

            return results["passed"]

    async def _get_reading_count(self, sb) -> int:
        """Get total row count from sensor_readings table."""
        try:
            result = await sb.execute_sql(
                "SELECT COUNT(*) FROM sensor_readings"
            )
            return result.rows[0][0] if result.rows else 0
        except Exception as e:
            logger.warning(f"Could not query sensor_readings: {e}")
            return 0

    def _build_results(
        self, runner, sim_conns, conn_points, telemetry, row_count, new_rows
    ) -> dict:
        """Compile verification results."""
        expected_conns = len(runner._bacnet_sims) + len(runner._modbus_sims)
        actual_conns = len(sim_conns)

        # Count connections with at least 1 point
        conns_with_points = sum(
            1
            for v in conn_points.values()
            if isinstance(v, int) and v > 0
        )

        has_telemetry = telemetry.total_points > 0
        data_accumulating = new_rows > 0

        passed = (
            actual_conns == expected_conns
            and conns_with_points > 0
            and has_telemetry
        )

        # Build per-device status
        devices = []
        for sim in runner._bacnet_sims:
            conn_name = f"Sim: {sim.device_name}"
            pts = conn_points.get(conn_name, 0)
            devices.append({
                "name": sim.device_name,
                "protocol": "BACnet",
                "id": str(sim.device_id),
                "expected_points": len(sim._object_defs),
                "actual_points": pts if isinstance(pts, int) else 0,
                "status": "PASS" if isinstance(pts, int) and pts > 0 else "FAIL",
            })

        for sim in runner._modbus_sims:
            conn_name = f"Sim: {sim.device_name}"
            pts = conn_points.get(conn_name, 0)
            devices.append({
                "name": sim.device_name,
                "protocol": "Modbus",
                "id": f"unit {sim.unit_id}",
                "expected_points": len(sim._registers),
                "actual_points": pts if isinstance(pts, int) else 0,
                "status": "PASS" if isinstance(pts, int) and pts > 0 else "FAIL",
            })

        # Sample telemetry values
        samples = []
        for dp in telemetry.data_points[:10]:
            samples.append({
                "id": dp.id,
                "value": dp.data,
                "units": dp.units or "",
                "type": dp.type,
            })

        return {
            "passed": passed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "connections_expected": expected_conns,
            "connections_found": actual_conns,
            "connections_with_points": conns_with_points,
            "total_telemetry_points": telemetry.total_points,
            "db_row_count": row_count,
            "new_rows": new_rows,
            "data_accumulating": data_accumulating,
            "devices": devices,
            "samples": samples,
        }

    def _print_report(self, results: dict) -> None:
        """Print a summary report."""
        console.print("\n")
        console.rule("[bold]End-to-End Verification Report")

        # Overall status
        if results["passed"]:
            console.print("[bold green]OVERALL: PASS[/bold green]\n")
        else:
            console.print("[bold red]OVERALL: FAIL[/bold red]\n")

        # Summary
        console.print(
            f"  Connections: {results['connections_found']}/{results['connections_expected']}"
        )
        console.print(
            f"  Connections with points: {results['connections_with_points']}"
        )
        console.print(
            f"  Telemetry data points: {results['total_telemetry_points']}"
        )
        console.print(f"  DB rows: {results['db_row_count']}")
        console.print(
            f"  Data accumulating: "
            f"{'[green]Yes[/green]' if results['data_accumulating'] else '[yellow]No[/yellow]'} "
            f"({results['new_rows']} new rows)"
        )

        # Per-device table
        table = Table(title="\nDevice Status")
        table.add_column("Device", style="bold")
        table.add_column("Protocol", style="cyan")
        table.add_column("ID")
        table.add_column("Expected Pts", justify="right")
        table.add_column("Actual Pts", justify="right")
        table.add_column("Status")

        for d in results["devices"]:
            status_style = "green" if d["status"] == "PASS" else "red"
            table.add_row(
                d["name"],
                d["protocol"],
                d["id"],
                str(d["expected_points"]),
                str(d["actual_points"]),
                f"[{status_style}]{d['status']}[/{status_style}]",
            )

        console.print(table)

        # Sample telemetry
        if results["samples"]:
            sample_table = Table(title="\nSample Telemetry (first 10)")
            sample_table.add_column("Point ID")
            sample_table.add_column("Value")
            sample_table.add_column("Units")
            sample_table.add_column("Type")

            for s in results["samples"]:
                sample_table.add_row(
                    str(s["id"]),
                    str(s["value"]),
                    s["units"],
                    s["type"],
                )

            console.print(sample_table)

        console.print()
