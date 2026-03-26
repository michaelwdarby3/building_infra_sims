"""CLI entry point for building infrastructure simulators."""

import typer
from rich.console import Console

app = typer.Typer(
    name="bsim",
    help="Building infrastructure protocol simulators for BACnet/IP and Modbus TCP.",
)
console = Console()

# Sub-command groups
bacnet_app = typer.Typer(help="BACnet/IP device simulator commands.")
modbus_app = typer.Typer(help="Modbus TCP device simulator commands.")
skybox_app = typer.Typer(help="Gateway API client commands.")

app.add_typer(bacnet_app, name="bacnet")
app.add_typer(modbus_app, name="modbus")
app.add_typer(skybox_app, name="skybox")


@app.callback()
def main():
    """Building infrastructure simulators - simulate BACnet and Modbus devices for integration testing."""


@bacnet_app.command("run")
def bacnet_run(
    profile: str = typer.Option(..., help="Path to BACnet device profile YAML"),
    device_id: int = typer.Option(..., help="BACnet device instance ID"),
    ip: str = typer.Option(None, help="IP address to bind (auto-detect if not set)"),
):
    """Run a simulated BACnet/IP device from a profile."""
    console.print(f"[bold]Starting BACnet device[/bold] (ID={device_id}, profile={profile})")
    from building_infra_sims.bacnet.profiles import run_from_profile

    run_from_profile(profile, device_id, ip)


@bacnet_app.command("list-profiles")
def bacnet_list_profiles():
    """List available BACnet device profiles."""
    from building_infra_sims.config import settings

    profiles_dir = settings.profiles_dir / "bacnet"
    if not profiles_dir.exists():
        console.print("[yellow]No BACnet profiles directory found.[/yellow]")
        return
    for p in sorted(profiles_dir.glob("*.yaml")):
        console.print(f"  {p.stem}")


@modbus_app.command("run")
def modbus_run(
    profile: str = typer.Option(..., help="Path to Modbus device profile YAML"),
    port: int = typer.Option(10502, help="TCP port to listen on"),
    unit_id: int = typer.Option(1, help="Modbus unit ID"),
):
    """Run a simulated Modbus TCP device from a profile."""
    console.print(f"[bold]Starting Modbus device[/bold] (unit={unit_id}, port={port})")
    from building_infra_sims.modbus.profiles import run_from_profile

    run_from_profile(profile, port, unit_id)


@modbus_app.command("list-profiles")
def modbus_list_profiles():
    """List available Modbus device profiles."""
    from building_infra_sims.config import settings

    profiles_dir = settings.profiles_dir / "modbus"
    if not profiles_dir.exists():
        console.print("[yellow]No Modbus profiles directory found.[/yellow]")
        return
    for p in sorted(profiles_dir.glob("*.yaml")):
        console.print(f"  {p.stem}")


@skybox_app.command("status")
def skybox_status():
    """Check gateway connectivity and system info."""
    import asyncio

    asyncio.run(_skybox_status())


async def _skybox_status():
    from building_infra_sims.config import settings
    from building_infra_sims.skybox.client import SkyboxClient

    async with SkyboxClient(
        settings.skybox_base_url,
        settings.skybox_username,
        settings.skybox_password,
    ) as sb:
        await sb.sign_in()
        status = await sb.get_status()
        info = await sb.get_system_info()
        console.print(f"[bold green]Gateway {status.status.value}[/bold green]")
        console.print(f"  Product: {info.product_name} ({info.sku})")
        console.print(f"  Firmware: {info.firmware_version}")
        console.print(f"  MAC: {info.mac_address}")

        stats = await sb.get_connection_stats()
        console.print(
            f"  Connections: {stats.total_connections} "
            f"(enabled={stats.enabled_connections})"
        )


@skybox_app.command("explore")
def skybox_explore():
    """Full interactive exploration of the gateway API."""
    import asyncio
    import importlib

    mod = importlib.import_module("scripts.explore_skybox")
    asyncio.run(mod.explore())


@app.command("scenario")
def run_scenario(
    scenario: str = typer.Argument(..., help="Path to scenario YAML file"),
    setup_skybox: bool = typer.Option(
        False, "--setup-skybox", help="Auto-register devices with the gateway"
    ),
):
    """Run a multi-device scenario (BACnet + Modbus simulators)."""
    console.print(f"[bold]Loading scenario:[/bold] {scenario}")
    from building_infra_sims.scenarios.runner import run_scenario as _run

    _run(scenario, setup_skybox=setup_skybox)


@app.command("teardown-skybox")
def teardown_skybox():
    """Remove all simulated device connections from the gateway."""
    import asyncio

    from building_infra_sims.scenarios.runner import ScenarioRunner

    async def _teardown():
        runner = ScenarioRunner.__new__(ScenarioRunner)
        runner._scenario = {"name": "teardown"}
        runner._bacnet_sims = []
        runner._modbus_sims = []
        runner._local_ip = None
        await runner.unregister_from_skybox()

    asyncio.run(_teardown())


@app.command("list-scenarios")
def list_scenarios():
    """List available scenario profiles."""
    from building_infra_sims.config import settings

    scenarios_dir = settings.profiles_dir / "scenarios"
    if not scenarios_dir.exists():
        console.print("[yellow]No scenarios directory found.[/yellow]")
        return
    for p in sorted(scenarios_dir.glob("*.yaml")):
        import yaml

        with open(p) as f:
            data = yaml.safe_load(f)
        bacnet_count = len(data.get("bacnet_devices", []))
        modbus_count = len(data.get("modbus_devices", []))
        console.print(
            f"  {p.stem}: {data.get('name', '?')} "
            f"({bacnet_count} BACnet, {modbus_count} Modbus)"
        )


if __name__ == "__main__":
    app()
