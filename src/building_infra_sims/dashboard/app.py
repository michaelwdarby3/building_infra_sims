"""FastAPI application factory for the simulator dashboard."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from building_infra_sims.dashboard.routes import router
from building_infra_sims.dashboard.state import DashboardState


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Stop all simulators on shutdown
    await app.state.dashboard.stop_all()


def create_app() -> FastAPI:
    """Create a FastAPI app with an empty device pool."""
    app = FastAPI(
        title="Building Sim Dashboard",
        description="Control panel for simulated building infrastructure devices",
        lifespan=lifespan,
    )

    app.state.dashboard = DashboardState()
    app.include_router(router)

    return app
