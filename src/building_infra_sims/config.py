"""Global configuration via environment variables (BSIM_ prefix)."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "BSIM_", "env_file": ".env", "env_file_encoding": "utf-8"}

    # Gateway connection
    skybox_host: str = "10.0.0.35"
    skybox_port: int = 8000
    skybox_username: str = ""
    skybox_password: str = ""

    # When the simulator runs co-located with the gateway (e.g. as an
    # ECS sidecar that shares the awsvpc network namespace), the
    # per-device IPs from the scenario file are unreachable — only
    # 127.0.0.1 works. Set BSIM_SKYBOX_ADVERTISE_HOST=127.0.0.1 to
    # force every BACnet/Modbus connection registered via
    # `--setup-skybox` to advertise that loopback host instead.
    skybox_advertise_host: str = ""

    # Prefix prepended to every connection name registered via
    # `--setup-skybox`. Defaults to "Sim: " (the historical value).
    # Set per-sidecar (e.g. "Sim RE1: ", "Sim Apt: ") when running
    # multiple simulators against a single gateway so each one's
    # registrations don't collide on names and the pre-registration
    # cleanup only wipes its own scenario's connections.
    skybox_connection_prefix: str = "Sim: "

    # BACnet simulator
    bacnet_interface: str = "eth0"
    bacnet_port: int = 47808

    # Modbus simulator
    modbus_bind_address: str = "0.0.0.0"
    modbus_port: int = 10502

    # Paths
    profiles_dir: Path = Path(__file__).parent.parent.parent / "profiles"

    # Dashboard
    dashboard_root_path: str = ""

    @property
    def skybox_base_url(self) -> str:
        return f"http://{self.skybox_host}:{self.skybox_port}"


settings = Settings()
