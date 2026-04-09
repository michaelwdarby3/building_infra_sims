"""Async HTTP client for the gateway API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from building_infra_sims.skybox.models import (
    BACnetAutoDiscoveryRequest,
    BACnetAutoDiscoveryResult,
    BACnetDiscoveryResult,
    BACnetPointCreate,
    ConnectivityTestRequest,
    ConnectivityTestResult,
    Connection,
    ConnectionCreate,
    ConnectionList,
    ConnectionMetadata,
    ConnectionStats,
    ConnectionUpdate,
    InterfaceStatus,
    ModbusPointCreate,
    ModbusRegisterScanRequest,
    ModbusRegisterScanResult,
    ModuleInfo,
    NetworkConfiguration,
    NetworkScanResult,
    PointCloudSyncResponse,
    PointCloudSyncUpdate,
    PointList,
    SignInResponse,
    SqlQueryRequest,
    SqlQueryResponse,
    StatusResponse,
    TelemetryPointsResponse,
)

logger = logging.getLogger(__name__)


class SkyboxClient:
    """Async client for the gateway REST API.

    Usage::

        async with SkyboxClient("http://10.0.0.35:8000", "admin", "pass") as sb:
            await sb.sign_in()
            conns = await sb.list_connections()
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )
        self._auth_header: dict[str, str] = {}

    async def __aenter__(self) -> SkyboxClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ── Auth ───────────────────────────────────────────────────────────────

    async def sign_in(
        self, username: str | None = None, password: str | None = None
    ) -> SignInResponse:
        """Authenticate via HTTP Basic and store the auth header for future requests."""
        user = username or self._username
        pwd = password or self._password
        if not user or not pwd:
            raise ValueError("Username and password are required for sign-in")

        resp = await self._client.post(
            "/api/auth/sign-in",
            auth=(user, pwd),
        )
        resp.raise_for_status()

        result = SignInResponse.model_validate(resp.json())

        # Store basic auth for subsequent requests
        self._auth_header = {"Authorization": resp.request.headers["authorization"]}
        self._client.headers.update(self._auth_header)

        logger.info(f"Signed in to gateway at {self.base_url}")
        return result

    # ── Connections CRUD ───────────────────────────────────────────────────

    async def list_connections(
        self,
        enabled_only: bool | None = None,
        connection_type: str | None = None,
        search: str | None = None,
    ) -> ConnectionList:
        params: dict[str, Any] = {}
        if enabled_only is not None:
            params["enabled_only"] = enabled_only
        if connection_type:
            params["type"] = connection_type
        if search:
            params["search"] = search

        resp = await self._client.get("/api/connections/", params=params)
        resp.raise_for_status()
        return ConnectionList.model_validate(resp.json())

    async def get_connection(self, connection_id: str) -> Connection:
        resp = await self._client.get(f"/api/connections/{connection_id}")
        resp.raise_for_status()
        return Connection.model_validate(resp.json())

    async def create_connection(self, connection: ConnectionCreate) -> Connection:
        resp = await self._client.post(
            "/api/connections/",
            json=connection.model_dump(mode="json"),
        )
        if resp.status_code == 409:
            # Stale connection exists — delete it and retry
            existing = await self.list_connections(search=connection.name)
            for conn in existing.connections:
                if conn.name == connection.name:
                    await self.delete_connection(conn.id)
            resp = await self._client.post(
                "/api/connections/",
                json=connection.model_dump(mode="json"),
            )
        resp.raise_for_status()
        return Connection.model_validate(resp.json())

    async def update_connection(
        self, connection_id: str, update: ConnectionUpdate
    ) -> Connection:
        resp = await self._client.put(
            f"/api/connections/{connection_id}",
            json=update.model_dump(mode="json", exclude_none=True),
        )
        resp.raise_for_status()
        return Connection.model_validate(resp.json())

    async def delete_connection(self, connection_id: str) -> None:
        resp = await self._client.delete(f"/api/connections/{connection_id}")
        resp.raise_for_status()

    async def get_connection_metadata(self) -> ConnectionMetadata:
        resp = await self._client.get("/api/connections/metadata")
        resp.raise_for_status()
        return ConnectionMetadata.model_validate(resp.json())

    async def get_connection_stats(self) -> ConnectionStats:
        resp = await self._client.get("/api/connections/stats")
        resp.raise_for_status()
        return ConnectionStats.model_validate(resp.json())

    # ── Network Scanning ──────────────────────────────────────────────────

    async def scan_bacnet_network(self) -> NetworkScanResult:
        resp = await self._client.post("/api/connections/scan-network")
        resp.raise_for_status()
        return NetworkScanResult.model_validate(resp.json())

    async def scan_modbus_network(self) -> NetworkScanResult:
        resp = await self._client.post("/api/connections/scan-modbus-network")
        resp.raise_for_status()
        return NetworkScanResult.model_validate(resp.json())

    async def test_connectivity(
        self, request: ConnectivityTestRequest
    ) -> ConnectivityTestResult:
        resp = await self._client.post(
            "/api/connections/test-connectivity",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        resp.raise_for_status()
        return ConnectivityTestResult.model_validate(resp.json())

    # ── BACnet Discovery ──────────────────────────────────────────────────

    async def discover_bacnet_objects(
        self, connection_id: str
    ) -> BACnetDiscoveryResult:
        resp = await self._client.post(
            f"/api/connections/{connection_id}/bacnet-objects"
        )
        resp.raise_for_status()
        return BACnetDiscoveryResult.model_validate(resp.json())

    async def save_bacnet_objects(
        self,
        connection_id: str,
        auto_add: bool = True,
    ) -> BACnetAutoDiscoveryResult:
        body = BACnetAutoDiscoveryRequest(auto_add_objects=auto_add)
        resp = await self._client.post(
            f"/api/connections/{connection_id}/bacnet-objects-save",
            json=body.model_dump(mode="json"),
        )
        resp.raise_for_status()
        return BACnetAutoDiscoveryResult.model_validate(resp.json())

    # ── Modbus Register Scan ──────────────────────────────────────────────

    async def scan_modbus_registers(
        self,
        connection_id: str,
        request: ModbusRegisterScanRequest | None = None,
    ) -> ModbusRegisterScanResult:
        body = (request or ModbusRegisterScanRequest()).model_dump(
            mode="json", exclude_none=True
        )
        resp = await self._client.post(
            f"/api/connections/{connection_id}/modbus-registers",
            json=body,
        )
        resp.raise_for_status()
        return ModbusRegisterScanResult.model_validate(resp.json())

    # ── Points ────────────────────────────────────────────────────────────

    async def list_points(self, connection_id: str) -> PointList:
        resp = await self._client.get(
            f"/api/connections/{connection_id}/points"
        )
        resp.raise_for_status()
        return PointList.model_validate(resp.json())

    async def add_modbus_point(
        self, connection_id: str, point: ModbusPointCreate
    ) -> None:
        resp = await self._client.post(
            f"/api/connections/{connection_id}/points",
            json=point.model_dump(mode="json"),
        )
        resp.raise_for_status()

    async def add_bacnet_point(
        self, connection_id: str, point: BACnetPointCreate
    ) -> None:
        resp = await self._client.post(
            f"/api/connections/{connection_id}/points",
            json=point.model_dump(mode="json"),
        )
        resp.raise_for_status()

    async def delete_point(
        self, connection_id: str, point_name: str
    ) -> None:
        resp = await self._client.delete(
            f"/api/connections/{connection_id}/points/{point_name}"
        )
        resp.raise_for_status()

    async def update_equipment_class(
        self, connection_id: str, equipment_class: str
    ) -> dict:
        """Set the Brick Schema equipment class for a connection."""
        resp = await self._client.put(
            f"/api/connections/{connection_id}/equipment-class",
            json={"equipment_class": equipment_class},
        )
        resp.raise_for_status()
        return resp.json()

    async def update_point_cloud_sync(
        self, connection_id: str, point_name: str, sync: bool
    ) -> PointCloudSyncResponse:
        body = PointCloudSyncUpdate(sync=sync)
        resp = await self._client.put(
            f"/api/connections/{connection_id}/points/{point_name}/cloud-sync",
            json=body.model_dump(mode="json"),
        )
        resp.raise_for_status()
        return PointCloudSyncResponse.model_validate(resp.json())

    # ── Telemetry ─────────────────────────────────────────────────────────

    async def get_telemetry(self) -> TelemetryPointsResponse:
        resp = await self._client.get("/api/telemetry/points")
        resp.raise_for_status()
        return TelemetryPointsResponse.model_validate(resp.json())

    # ── Settings ──────────────────────────────────────────────────────────

    async def get_status(self) -> StatusResponse:
        resp = await self._client.get("/api/settings/status")
        resp.raise_for_status()
        return StatusResponse.model_validate(resp.json())

    async def get_system_info(self) -> ModuleInfo:
        resp = await self._client.get("/api/settings/system-info")
        resp.raise_for_status()
        return ModuleInfo.model_validate(resp.json())

    async def get_network_interfaces(self) -> list[InterfaceStatus]:
        resp = await self._client.get("/api/settings/network/interfaces")
        resp.raise_for_status()
        return [InterfaceStatus.model_validate(i) for i in resp.json()]

    async def get_ipv4_config(self) -> NetworkConfiguration:
        resp = await self._client.get("/api/settings/network/ipv4")
        resp.raise_for_status()
        return NetworkConfiguration.model_validate(resp.json())

    async def update_ipv4_config(self, config: NetworkConfiguration) -> None:
        resp = await self._client.put(
            "/api/settings/network/ipv4",
            json=config.model_dump(mode="json", exclude_none=True),
        )
        resp.raise_for_status()

    async def reboot(self) -> None:
        resp = await self._client.post("/api/settings/reboot")
        resp.raise_for_status()

    # ── SQL ────────────────────────────────────────────────────────────────

    async def execute_sql(self, query: str) -> SqlQueryResponse:
        body = SqlQueryRequest(query=query)
        resp = await self._client.post(
            "/api/sql/execute",
            json=body.model_dump(mode="json"),
        )
        resp.raise_for_status()
        return SqlQueryResponse.model_validate(resp.json())

    # ── Convenience helpers ───────────────────────────────────────────────

    async def setup_bacnet_connection(
        self,
        name: str,
        ip_address: str,
        device_id: int,
        port: int = 47808,
        auto_discover: bool = True,
    ) -> tuple[Connection, BACnetAutoDiscoveryResult | None]:
        """Create a BACnet connection and optionally auto-discover objects."""
        from building_infra_sims.skybox.models import (
            BacnetConnectionConfig,
            ConnectionType,
        )

        conn = await self.create_connection(
            ConnectionCreate(
                name=name,
                connection_type=ConnectionType.BACNET_IP,
                config=BacnetConnectionConfig(
                    ip_address=ip_address,
                    device_id=device_id,
                    port=port,
                    auto_discover=auto_discover,
                ),
            )
        )

        discovery = None
        if auto_discover and conn.id:
            discovery = await self.save_bacnet_objects(conn.id)

        return conn, discovery

    async def setup_modbus_connection(
        self,
        name: str,
        ip_address: str,
        port: int = 502,
        unit_id: int = 1,
    ) -> Connection:
        """Create a Modbus TCP connection."""
        from building_infra_sims.skybox.models import (
            ConnectionType,
            ModbusConnectionConfig,
        )

        return await self.create_connection(
            ConnectionCreate(
                name=name,
                connection_type=ConnectionType.MODBUS_TCP,
                config=ModbusConnectionConfig(
                    ip_address=ip_address,
                    port=port,
                    unit_id=unit_id,
                ),
            )
        )
