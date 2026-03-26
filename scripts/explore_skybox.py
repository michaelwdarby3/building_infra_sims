"""Interactive exploration of the gateway API.

Usage:
    python scripts/explore_skybox.py [--host HOST] [--user USER] [--pass PASS]

If not supplied, reads from BSIM_ environment variables or .env file.
"""

import asyncio
import json
import logging
import os
import sys

from rich.console import Console
from rich.table import Table

from building_infra_sims.config import settings
from building_infra_sims.skybox.client import SkyboxClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
console = Console()


async def explore():
    host = os.environ.get("BSIM_SKYBOX_HOST", settings.skybox_host)
    port = int(os.environ.get("BSIM_SKYBOX_PORT", str(settings.skybox_port)))
    user = os.environ.get("BSIM_SKYBOX_USERNAME", settings.skybox_username)
    pwd = os.environ.get("BSIM_SKYBOX_PASSWORD", settings.skybox_password)

    base_url = f"http://{host}:{port}"

    if not user or not pwd:
        console.print("[red]Set BSIM_SKYBOX_USERNAME and BSIM_SKYBOX_PASSWORD[/red]")
        sys.exit(1)

    async with SkyboxClient(base_url, user, pwd) as sb:
        # Auth
        console.rule("[bold]Authentication")
        auth = await sb.sign_in()
        console.print(f"Sign-in: {auth.success} — {auth.message}")

        # System info
        console.rule("[bold]System Info")
        try:
            info = await sb.get_system_info()
            console.print(f"Product: {info.product_name} ({info.sku})")
            console.print(f"Firmware: {info.firmware_version}")
            console.print(f"MAC: {info.mac_address}")
            console.print(f"Description: {info.description}")
            for dest in info.destinations:
                console.print(f"  Destination: {dest.name} — {dest.status}")
        except Exception as e:
            console.print(f"[yellow]Could not get system info: {e}[/yellow]")

        # Status
        console.rule("[bold]Device Status")
        try:
            status = await sb.get_status()
            console.print(f"Status: {status.status.value}")
            console.print(f"Connection: {status.connection.state.value}")
        except Exception as e:
            console.print(f"[yellow]Could not get status: {e}[/yellow]")

        # Network
        console.rule("[bold]Network")
        try:
            ifaces = await sb.get_network_interfaces()
            for iface in ifaces:
                console.print(
                    f"  {iface.device} ({iface.type.value}) "
                    f"primary={iface.is_primary} available={iface.is_available}"
                )
        except Exception as e:
            console.print(f"[yellow]Could not get interfaces: {e}[/yellow]")

        try:
            ipv4 = await sb.get_ipv4_config()
            console.print(f"  IPv4: {ipv4.ip_address} gw={ipv4.gateway} mode={ipv4.mode.value}")
        except Exception as e:
            console.print(f"[yellow]Could not get IPv4: {e}[/yellow]")

        # Connection metadata
        console.rule("[bold]Connection Metadata")
        try:
            meta = await sb.get_connection_metadata()
            console.print(f"Register types: {meta.register_types}")
            console.print(f"Point data types: {meta.point_data_types}")
            console.print(f"BACnet object types: {meta.bacnet_object_types}")
        except Exception as e:
            console.print(f"[yellow]Could not get metadata: {e}[/yellow]")

        # Connections
        console.rule("[bold]Connections")
        try:
            stats = await sb.get_connection_stats()
            console.print(
                f"Total: {stats.total_connections} "
                f"(enabled={stats.enabled_connections}, disabled={stats.disabled_connections})"
            )
            console.print(f"By type: {stats.by_type}")
            console.print(f"By status: {stats.by_status}")
        except Exception as e:
            console.print(f"[yellow]Could not get stats: {e}[/yellow]")

        try:
            conns = await sb.list_connections()
            if conns.items:
                table = Table(title=f"Connections ({conns.total})")
                table.add_column("ID")
                table.add_column("Name")
                table.add_column("Type")
                table.add_column("Enabled")
                table.add_column("Status")

                for c in conns.items:
                    table.add_row(
                        str(c.id),
                        c.name,
                        c.connection_type.value,
                        str(c.enabled),
                        c.status.value if c.status else "—",
                    )
                console.print(table)

                # List points for each connection
                for c in conns.items:
                    if not c.id:
                        continue
                    console.rule(f"[dim]Points for {c.name}")
                    try:
                        points = await sb.list_points(c.id)
                        console.print(f"  {points.total} points ({points.protocol})")
                        for p in points.items[:10]:
                            console.print(f"    {json.dumps(p, default=str)[:120]}")
                        if points.total > 10:
                            console.print(f"    ... and {points.total - 10} more")
                    except Exception as e:
                        console.print(f"  [yellow]Error: {e}[/yellow]")
            else:
                console.print("[dim]No connections configured[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not list connections: {e}[/yellow]")

        # Telemetry
        console.rule("[bold]Telemetry")
        try:
            telem = await sb.get_telemetry()
            console.print(f"Total points: {telem.total_points}")
            for dp in telem.data_points[:10]:
                console.print(f"  {dp.id}: {dp.data} {dp.units or ''} ({dp.type})")
            if telem.total_points > 10:
                console.print(f"  ... and {telem.total_points - 10} more")
        except Exception as e:
            console.print(f"[yellow]Could not get telemetry: {e}[/yellow]")

        # SQL — list tables
        console.rule("[bold]SQL — Database Tables")
        try:
            result = await sb.execute_sql(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            console.print(f"Tables ({result.rowCount}):")
            for row in result.rows:
                console.print(f"  {row[0]}")
        except Exception as e:
            console.print(f"[yellow]Could not query SQL: {e}[/yellow]")


if __name__ == "__main__":
    asyncio.run(explore())
