"""Dashboard routes: HTML pages and action endpoints."""

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from building_infra_sims.dashboard.state import DashboardState

router = APIRouter()

templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)


def _get_state(request: Request) -> DashboardState:
    return request.app.state.dashboard


# ── HTML pages ────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    state = _get_state(request)
    devices = state.get_device_summary()
    stats = await state.fetch_connection_stats()

    running = sum(1 for d in devices if d["status"] == "running")
    registered = sum(1 for d in devices if d["registered"])
    bacnet_count = sum(1 for d in devices if d["protocol"] == "BACnet")
    modbus_count = sum(1 for d in devices if d["protocol"] == "Modbus")

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "devices": devices,
            "running": running,
            "registered": registered,
            "bacnet_count": bacnet_count,
            "modbus_count": modbus_count,
            "total_devices": len(devices),
            "gateway_stats": stats,
        },
    )


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    state = _get_state(request)
    devices = state.get_device_summary()
    profiles = state.list_profiles()
    scenarios = state.list_scenarios()
    return templates.TemplateResponse(
        request,
        "devices.html",
        {
            "devices": devices,
            "profiles": profiles,
            "scenarios": scenarios,
        },
    )


@router.get("/telemetry", response_class=HTMLResponse)
async def telemetry_page(request: Request):
    state = _get_state(request)
    telem = await state.fetch_telemetry()
    return templates.TemplateResponse(
        request,
        "telemetry.html",
        {"telemetry": telem},
    )


@router.get("/telemetry/history", response_class=HTMLResponse)
async def telemetry_history_page(request: Request):
    return templates.TemplateResponse(
        request,
        "telemetry_history.html",
    )


@router.get("/connections", response_class=HTMLResponse)
async def connections_page(request: Request):
    state = _get_state(request)
    conns = await state.fetch_connections()
    return templates.TemplateResponse(
        request,
        "connections.html",
        {"connections": conns},
    )


# ── Actions (POST endpoints for HTMX) ────────────────────────────────────


@router.post("/actions/start-device")
async def action_start_device(
    request: Request,
    profile_path: str = Form(...),
    protocol: str = Form(...),
    device_id: int = Form(None),
    port: int = Form(None),
    unit_id: int = Form(None),
):
    """Start a new simulated device from a profile."""
    state = _get_state(request)

    if protocol == "bacnet":
        await state.start_bacnet_device(
            profile_path=profile_path,
            device_id=device_id or None,
            port=port or None,
        )
    elif protocol == "modbus":
        await state.start_modbus_device(
            profile_path=profile_path,
            port=port or None,
            unit_id=unit_id or None,
        )

    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/stop-device/{device_id}")
async def action_stop_device(request: Request, device_id: str):
    """Stop a running simulator."""
    state = _get_state(request)
    await state.stop_device(device_id)
    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/remove-device/{device_id}")
async def action_remove_device(request: Request, device_id: str):
    """Stop and remove a device entirely."""
    state = _get_state(request)
    await state.remove_device(device_id)
    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/register-device/{device_id}")
async def action_register_device(request: Request, device_id: str):
    """Register a device with the gateway."""
    state = _get_state(request)
    await state.register_device(device_id)
    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/unregister-device/{device_id}")
async def action_unregister_device(request: Request, device_id: str):
    """Unregister a device from the gateway."""
    state = _get_state(request)
    await state.unregister_device(device_id)
    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/register-all")
async def action_register_all(request: Request):
    """Register all running devices with the gateway."""
    state = _get_state(request)
    await state.register_all()
    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/unregister-all")
async def action_unregister_all(request: Request):
    """Unregister all devices from the gateway."""
    state = _get_state(request)
    await state.unregister_all()
    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/stop-all")
async def action_stop_all(request: Request):
    """Stop all running simulators."""
    state = _get_state(request)
    await state.stop_all()
    return RedirectResponse("/devices", status_code=303)


@router.post("/actions/load-scenario")
async def action_load_scenario(
    request: Request,
    scenario_path: str = Form(...),
):
    """Load and start all devices from a scenario file."""
    state = _get_state(request)
    await state.load_scenario(scenario_path)
    return RedirectResponse("/devices", status_code=303)


# ── HTMX partials ────────────────────────────────────────────────────────


@router.get("/api/telemetry", response_class=HTMLResponse)
async def api_telemetry_partial(request: Request):
    """Return just the telemetry table rows (HTMX swap target)."""
    state = _get_state(request)
    telem = await state.fetch_telemetry()
    return templates.TemplateResponse(
        request,
        "partials/telemetry_table.html",
        {"data_points": telem.get("data_points", [])},
    )


@router.get("/api/devices", response_class=HTMLResponse)
async def api_devices_partial(request: Request):
    """Return just the devices table (HTMX swap target)."""
    state = _get_state(request)
    devices = state.get_device_summary()
    return templates.TemplateResponse(
        request,
        "partials/devices_table.html",
        {"devices": devices},
    )


@router.get("/api/telemetry/history")
async def api_telemetry_history(request: Request):
    """JSON time-series data for charts."""
    state = _get_state(request)
    rows = await state.fetch_telemetry_history(minutes=60)
    return {"rows": rows, "count": len(rows)}
