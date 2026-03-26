"""Pydantic models for the gateway API, derived from the OpenAPI spec."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────


class ConnectionType(str, Enum):
    MODBUS_TCP = "modbus_tcp"
    BACNET_IP = "bacnet_ip"
    RTD = "rtd"
    ONE_WIRE = "one_wire"


class ConnectionStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    CONNECTING = "connecting"


class RegisterType(str, Enum):
    HOLDING_REGISTER = "holding_register"
    INPUT_REGISTER = "input_register"
    COIL = "coil"
    DISCRETE_INPUT = "discrete_input"


class PointDataType(str, Enum):
    FLOAT32 = "FLOAT32"
    FLOAT64 = "FLOAT64"
    INT16 = "INT16"
    UINT16 = "UINT16"
    INT32 = "INT32"
    UINT32 = "UINT32"
    INT64 = "INT64"
    UINT64 = "UINT64"
    STRING = "STRING"
    BOOL = "BOOL"


class BACnetObjectType(str, Enum):
    ANALOG_INPUT = "analog-input"
    ANALOG_OUTPUT = "analog-output"
    ANALOG_VALUE = "analog-value"
    BINARY_INPUT = "binary-input"
    BINARY_OUTPUT = "binary-output"
    BINARY_VALUE = "binary-value"
    MULTI_STATE_INPUT = "multi-state-input"
    MULTI_STATE_OUTPUT = "multi-state-output"
    MULTI_STATE_VALUE = "multi-state-value"


class DeviceStatus(str, Enum):
    OK = "ok"
    UNHEALTHY = "unhealthy"


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class IPv4Mode(str, Enum):
    DHCP = "dhcp"
    MANUAL = "manual"


class InterfaceType(str, Enum):
    ETHERNET = "ethernet"
    CELLULAR = "cellular"


# ── Auth ───────────────────────────────────────────────────────────────────


class SignInResponse(BaseModel):
    success: bool
    message: str


# ── Connection Configs ─────────────────────────────────────────────────────


class ModbusConnectionConfig(BaseModel):
    ip_address: str
    port: int = 502
    unit_id: int = 1
    poll_interval: int = 30
    scaling_enabled: bool = False


class BacnetConnectionConfig(BaseModel):
    ip_address: str
    device_id: int
    client_ip: str | None = None
    bbmd_ip: str | None = None
    bbmd_ttl: int = 900
    auto_discover: bool = False
    scaling_factor: int = 1
    port: int = 47808
    timeout: int = 30
    poll_interval: int = 60


class RTDConnectionConfig(BaseModel):
    channel: int
    sensor_type: str = "PT100"
    poll_interval: int = 30


class OneWireConnectionConfig(BaseModel):
    device_id: str
    sensor_type: str = "DS18B20"
    poll_interval: int = 30


# ── Connections ────────────────────────────────────────────────────────────


class Connection(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    connection_type: ConnectionType
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    location: dict[str, str] | None = None
    config: ModbusConnectionConfig | BacnetConnectionConfig | RTDConnectionConfig | OneWireConnectionConfig
    status: ConnectionStatus | None = None


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    connection_type: ConnectionType
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    location: dict[str, str] | None = None
    config: ModbusConnectionConfig | BacnetConnectionConfig | RTDConnectionConfig | OneWireConnectionConfig


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    connection_type: ConnectionType | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    location: dict[str, str] | None = None
    config: ModbusConnectionConfig | BacnetConnectionConfig | RTDConnectionConfig | OneWireConnectionConfig | None = None


class ConnectionList(BaseModel):
    items: list[Connection]
    total: int


class ConnectionMetadata(BaseModel):
    protocols: list[dict[str, Any]]
    register_types: list[str]
    point_data_types: list[str]
    bacnet_object_types: list[str]


class ConnectionStats(BaseModel):
    total_connections: int
    enabled_connections: int
    disabled_connections: int
    by_type: dict[str, int]
    by_status: dict[str, int]


# ── Network Scan ───────────────────────────────────────────────────────────


class NetworkDevice(BaseModel):
    ip_address: str | None = None
    port: int | None = None
    device_id: int | None = None
    device_name: str | None = None
    vendor: str | None = None


class NetworkScanResult(BaseModel):
    success: bool
    network_range: str
    devices_found: list[NetworkDevice] | None = None
    total_devices: int = 0
    scan_time_seconds: float
    error_message: str | None = None
    timestamp: str


# ── Connectivity Test ──────────────────────────────────────────────────────


class ConnectivityTestRequest(BaseModel):
    ip_address: str
    port: int = Field(ge=1, le=65535)
    protocol_type: str | None = None
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    bacnet_device_id: int | None = Field(default=None, ge=0, le=4194303)
    modbus_unit_id: int = Field(default=1, ge=1, le=247)


class ConnectivityTestResult(BaseModel):
    success: bool
    ip_address: str
    port: int
    protocol: str
    response_time_ms: float | None = None
    protocol_validated: bool | None = None
    error_message: str | None = None
    timestamp: str


# ── Points ─────────────────────────────────────────────────────────────────


class ModbusPointCreate(BaseModel):
    point_name: str = Field(min_length=1, max_length=100)
    address: int = Field(ge=0, le=65535)
    format: PointDataType
    count: int = Field(ge=1, le=10)
    unit: str = Field(min_length=1, max_length=20)
    register_type: RegisterType = RegisterType.HOLDING_REGISTER
    swap_words: bool = False
    little_endian_bytes: bool = False
    room: str | None = Field(default=None, max_length=50)
    zone: str | None = Field(default=None, max_length=50)
    sync: bool = False


class BACnetPointCreate(BaseModel):
    object_type: BACnetObjectType
    instance: int = Field(ge=0, le=4194303)
    object_name: str | None = Field(default=None, max_length=100)
    zone: str | None = Field(default=None, max_length=50)
    room: str | None = Field(default=None, max_length=50)
    sync: bool = False


class PointCloudSyncUpdate(BaseModel):
    sync: bool


class PointCloudSyncResponse(BaseModel):
    connection_id: str
    point_name: str
    sync: bool
    updated_at: str


class PointValue(BaseModel):
    id: str
    data: float | int | bool | str | None
    units: str | None = None
    type: str
    time: int
    zone: str | None = None
    room: str | None = None


class PointList(BaseModel):
    items: list[dict[str, Any]]
    total: int
    protocol: str


# ── BACnet Discovery ───────────────────────────────────────────────────────


class BACnetDeviceInfo(BaseModel):
    device_id: int | None = None
    device_name: str | None = None
    vendor: str | None = None
    model: str | None = None
    objects: list[dict[str, Any]] = Field(default_factory=list)


class BACnetDiscoveryResult(BaseModel):
    success: bool
    device_info: BACnetDeviceInfo | None = None
    total_objects_found: int = 0
    discovery_time_seconds: float
    error_message: str | None = None
    timestamp: str


class BACnetAutoDiscoveryRequest(BaseModel):
    auto_add_objects: bool = True


class BACnetAutoDiscoveryResult(BaseModel):
    success: bool
    connection_id: str
    device_info: BACnetDeviceInfo | None = None
    objects_discovered: int = 0
    objects_added: int = 0
    discovery_time_seconds: float
    configuration_updated: bool = False
    error_message: str | None = None
    timestamp: str


# ── Modbus Register Scan ───────────────────────────────────────────────────


class ModbusRegisterScanRequest(BaseModel):
    start_address: int = Field(default=0, ge=0, le=65535)
    end_address: int = Field(default=100, ge=0, le=65535)
    register_type: RegisterType = RegisterType.HOLDING_REGISTER
    unit_id: int | None = Field(default=None, ge=1, le=247)


class ModbusRegisterInfo(BaseModel):
    address: int
    value: int | None = None
    accessible: bool = True


class ModbusRegisterScanResult(BaseModel):
    success: bool
    connection_id: str
    device_address: str
    unit_id: int
    register_type: str
    start_address: int
    end_address: int
    registers: list[ModbusRegisterInfo]
    total_accessible: int = 0
    total_scanned: int = 0
    scan_time_seconds: float
    error_message: str | None = None
    timestamp: str


# ── Telemetry ──────────────────────────────────────────────────────────────


class TelemetryPointsResponse(BaseModel):
    timestamp: int
    data_points: list[PointValue]
    total_points: int


# ── Settings ───────────────────────────────────────────────────────────────


class StatusConnectionInfo(BaseModel):
    state: ConnectionState
    name: str | None = None
    interface: str | None = None


class StatusResponse(BaseModel):
    status: DeviceStatus
    connection: StatusConnectionInfo


class DestinationStatus(BaseModel):
    name: str | None = None
    status: str | None = None


class ModuleInfo(BaseModel):
    product_name: str
    sku: str
    mac_address: str | None = None
    firmware_version: str
    description: str
    destinations: list[DestinationStatus] = Field(default_factory=list)


class InterfaceStatus(BaseModel):
    device: str
    type: InterfaceType
    connection: str | None = None
    is_available: bool
    is_primary: bool = False
    metric: int | None = None


class NetworkConfiguration(BaseModel):
    ip_address: str | None = None
    gateway: str | None = None
    netmask: str | None = None
    dns_servers: list[str] | None = None
    mode: IPv4Mode


# ── SQL ────────────────────────────────────────────────────────────────────


class SqlQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)


class SqlQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    rowCount: int
    columnCount: int
