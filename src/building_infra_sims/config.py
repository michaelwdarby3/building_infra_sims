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
