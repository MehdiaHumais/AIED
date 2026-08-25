"""AIED Shared Data Models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Enums ---

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRole(str, Enum):
    EXECUTIVE = "executive"
    PRODUCT = "product"
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"
    UX = "ux"
    QUALITY = "quality"
    DEVOPS = "devops"
    INTELLIGENCE = "intelligence"
    AIOPS = "aiops"


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    ERROR = "error"
    OFFLINE = "offline"


class ProjectStatus(str, Enum):
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    TESTING = "testing"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    MAINTENANCE = "maintenance"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# --- Base Models ---

class TimestampMixin(BaseModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IDMixin(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))


# --- Agent Models ---

class AgentConfig(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: str
    name: str
    role: AgentRole
    department: str
    model_provider: str
    model_name: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    max_retries: int = 3
    timeout_seconds: int = 300


class AgentState(BaseModel):
    agent_id: str
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_active: datetime = Field(default_factory=datetime.utcnow)


# --- Task Models ---

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_agent_id: Optional[str] = None
    project_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    subtasks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# --- Project Models ---

class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    codename: str
    description: str
    status: ProjectStatus = ProjectStatus.PLANNING
    repository_url: Optional[str] = None
    tech_stack: list[str] = Field(default_factory=list)
    team: list[str] = Field(default_factory=list)  # agent IDs
    tasks: list[str] = Field(default_factory=list)  # task IDs
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    mode: str = "scratch"  # "scratch" or "prebuilt"
    folder: str = ""  # project folder path
    user_id: str = ""  # owner user ID (empty = global/admin)


# --- Conversation Models ---

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user", "assistant", "system"
    content: str
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: Optional[str] = None
    messages: list[Message] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# --- Deployment Models ---

class Deployment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    status: DeploymentStatus = DeploymentStatus.PENDING
    version: str
    environment: str = "production"
    build_log: str = ""
    deploy_log: str = ""
    rollback_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# --- API Request/Response Models ---

class CreateProjectRequest(BaseModel):
    name: str
    codename: str
    description: str
    tech_stack: list[str] = Field(default_factory=list)


class CreateTaskRequest(BaseModel):
    title: str
    description: str
    project_id: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_agent_id: Optional[str] = None


class AgentMessageRequest(BaseModel):
    agent_id: str
    message: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None


class TaskResponse(BaseModel):
    task: Task
    agent_id: Optional[str] = None
    status_message: str = ""


class ProjectResponse(BaseModel):
    project: Project
    tasks: list[Task] = Field(default_factory=list)
    agents: list[AgentConfig] = Field(default_factory=list)
