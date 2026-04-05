"""FastAPI application factory for the simulator dashboard."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from building_infra_sims.dashboard.routes import router
from building_infra_sims.dashboard.state import DashboardState


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    # Pre-load scenario if configured (must happen in uvicorn's event loop
    # so that Modbus asyncio server tasks stay alive)
    if getattr(app.state, "preload_scenario", None):
        await app.state.dashboard.load_scenario(app.state.preload_scenario)
        logger.info("Scenario loaded, devices started")

        # Registration is slow (BACnet discovery ~25s per device) so run it
        # in the background — the dashboard starts serving immediately.
        if getattr(app.state, "preload_setup_skybox", False):
            async def _register():
                try:
                    await app.state.dashboard.register_all()
                    logger.info("All devices registered with gateway")
                except Exception as e:
                    logger.error(f"Registration failed: {e}")

            asyncio.create_task(_register())

    await app.state.dashboard.start_recording()
    yield
    await app.state.dashboard.stop_recording()
    await app.state.dashboard.unregister_all()
    await app.state.dashboard.stop_all()


def create_app(
    preload_scenario: str | None = None,
    preload_setup_skybox: bool = False,
) -> FastAPI:
    """Create a FastAPI app with an empty device pool."""
    app = FastAPI(
        title="Building Sim Dashboard",
        description="Control panel for simulated building infrastructure devices",
        lifespan=lifespan,
    )

    app.state.dashboard = DashboardState()
    app.state.preload_scenario = preload_scenario
    app.state.preload_setup_skybox = preload_setup_skybox
    app.include_router(router)

    return app
