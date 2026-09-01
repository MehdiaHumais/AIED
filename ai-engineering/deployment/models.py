"""VPS Deployment Models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# --- Enums ---

class VPSDeployStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    PLAN_READY = "plan_ready"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    CONNECTING = "connecting"
    PREPARING_SERVER = "preparing_server"
    CLONING = "cloning"
    INSTALLING = "installing"
    BUILDING = "building"
    CONFIGURING = "configuring"
    MIGRATING = "migrating"
    STARTING = "starting"
    HEALTH_CHECK = "health_check"
    VERIFYING = "verifying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"
    WAITING_FOR_INPUT = "waiting_for_input"


class DeployStrategy(str, Enum):
    DOCKER = "docker"
    NATIVE = "native"
    AUTO = "auto"


class DeployMode(str, Enum):
    AUTOMATIC = "automatic"
    APPROVAL = "approval"


class AuthMethod(str, Enum):
    SSH_KEY = "ssh_key"
    PASSWORD = "password"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"


class LogSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    DEBUG = "debug"


# --- VPS Server ---

class VPSServer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    host: str
    port: int = 22
    username: str
    auth_method: AuthMethod = AuthMethod.SSH_KEY
    encrypted_private_key: str = ""
    encrypted_password: str = ""
    os_info: str = ""
    cpu_cores: int = 0
    ram_gb: float = 0
    disk_gb: float = 0
    disk_free_gb: float = 0
    has_docker: bool = False
    has_nginx: bool = False
    has_node: bool = False
    has_python: bool = False
    has_java: bool = False
    has_php: bool = False
    has_postgresql: bool = False
    has_mysql: bool = False
    has_redis: bool = False
    has_certbot: bool = False
    suitable: bool = True
    unsuitable_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- Deployment ---

class VPSDeployment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str
    github_repo: str
    branch: str = "main"
    commit_sha: str = ""
    domain: str
    project_details: str = ""
    vps_server_id: str = ""
    vps_host: str = ""
    vps_port: int = 22
    vps_username: str = ""
    vps_auth_method: str = "ssh_key"
    encrypted_private_key: str = ""
    encrypted_password: str = ""
    deploy_mode: DeployMode = DeployMode.AUTOMATIC
    deploy_strategy: DeployStrategy = DeployStrategy.AUTO
    status: VPSDeployStatus = VPSDeployStatus.PENDING
    detected_stack: dict[str, Any] = Field(default_factory=dict)
    deployment_plan: str = ""
    plan_json: list[dict[str, Any]] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    missing_env_vars: list[str] = Field(default_factory=list)
    project_dir: str = ""
    service_name: str = ""
    backend_port: int = 0
    frontend_port: int = 0
    nginx_config: str = ""
    systemd_service: str = ""
    docker_compose: str = ""
    ssl_enabled: bool = False
    health_check_url: str = ""
    health_check_passed: bool = False
    error_message: str = ""
    failed_step: str = ""
    recommended_action: str = ""
    rollback_available: bool = False
    rollback_dir: str = ""
    deployment_time_seconds: float = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# --- Deployment Steps ---

class DeploymentStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    name: str
    display_name: str
    status: StepStatus = StepStatus.PENDING
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0
    order: int = 0
    is_dangerous: bool = False


# --- Deployment Logs ---

class DeploymentLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step: str = ""
    status: StepStatus = StepStatus.RUNNING
    message: str = ""
    severity: LogSeverity = LogSeverity.INFO
    command: str = ""
    output: str = ""


# --- Health Checks ---

class HealthCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    check_type: str  # "http", "service", "database", "nginx", "disk", "ram"
    name: str
    status: StepStatus = StepStatus.PENDING
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    checked_at: Optional[datetime] = None


# --- API Request/Response ---

class CreateVPSDeploymentRequest(BaseModel):
    project_name: str
    github_repo: str
    branch: str = "main"
    domain: str
    project_details: str = ""
    vps_host: str
    vps_port: int = 22
    vps_username: str
    vps_private_key: str = ""
    vps_password: str = ""
    deploy_mode: DeployMode = DeployMode.AUTOMATIC
    env_vars: dict[str, str] = Field(default_factory=dict)

    @field_validator("domain")
    @classmethod
    def domain_must_be_real(cls, v: str) -> str:
        """Require a real domain name - never an IP address or localhost.

        The VPS deployer always publishes the app at the domain, so the domain
        field is mandatory and must not be an IP or localhost/127.0.0.1.
        """
        import re as _re
        value = (v or "").strip().replace("http://", "").replace("https://", "").rstrip("/")
        if not value:
            raise ValueError("Domain is required - the app is deployed to a domain, not an IP.")
        lower = value.lower()
        if lower in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise ValueError("Invalid domain: use a real domain (e.g. app.example.com), not localhost or an IP address.")
        # Reject pure IPv4 / IPv6 addresses
        if _re.match(r"^\d{1,3}(\.\d{1,3}){3}$", value):
            raise ValueError("Invalid domain: use a real domain, not an IP address.")
        looks_ipv6 = ":" in value or value.startswith("[")
        if looks_ipv6:
            raise ValueError("Invalid domain: use a real domain, not an IP address.")
        if not _re.match(r"^(?!-)[a-zA-Z0-9-]{1,63}(\.[a-zA-Z0-9-]{1,63})+$", value):
            raise ValueError("Invalid domain format - must be a domain name like app.example.com")
        return value


class DeploymentPlanResponse(BaseModel):
    deployment_id: str
    status: str
    plan: str
    plan_steps: list[dict[str, Any]]
    detected_stack: dict[str, Any]
    missing_env_vars: list[str]
    requires_approval: list[str]


class VPSDeploymentResponse(BaseModel):
    deployment: VPSDeployment
    steps: list[DeploymentStep]
    logs: list[DeploymentLog]
    health_checks: list[HealthCheck]
