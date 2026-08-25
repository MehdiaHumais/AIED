"""PostgreSQL Memory Layer - Projects, Tasks, Conversations, Logs, Users."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    create_engine,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from shared.config import DatabaseConfig


class Base(DeclarativeBase):
    """Base model for all database tables."""
    pass


# --- ORM Models ---

class ProjectDB(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    codename = Column(String, nullable=False, unique=True)
    description = Column(Text, default="")
    status = Column(String, default="planning")
    repository_url = Column(String, nullable=True)
    tech_stack = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks = relationship("TaskDB", back_populates="project")


class TaskDB(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="pending")
    priority = Column(String, default="medium")
    assigned_agent_id = Column(String, nullable=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    parent_task_id = Column(String, nullable=True)
    subtasks = Column(JSON, default=list)
    dependencies = Column(JSON, default=list)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("ProjectDB", back_populates="tasks")


class ConversationDB(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=True)
    context = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("MessageDB", back_populates="conversation")


class MessageDB(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    agent_id = Column(String, nullable=True)
    task_id = Column(String, nullable=True)
    metadata_json = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("ConversationDB", back_populates="messages")


class AgentLogDB(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=True)
    level = Column(String, default="info")
    message = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=datetime.utcnow)


class DeploymentDB(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    status = Column(String, default="pending")
    version = Column(String, nullable=False)
    environment = Column(String, default="production")
    build_log = Column(Text, default="")
    deploy_log = Column(Text, default="")
    rollback_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class UserDB(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, default="")
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    company_name = Column(String, default="")
    company_role = Column(String, default="")
    company_size = Column(String, default="")
    company_website = Column(String, default="")
    status = Column(String, default="pending")
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)


class VPSDeploymentDB(Base):
    __tablename__ = "vps_deployments"

    id = Column(String, primary_key=True)
    project_name = Column(String, nullable=False)
    github_repo = Column(String, nullable=False)
    branch = Column(String, default="main")
    domain = Column(String, nullable=True)
    deploy_mode = Column(String, default="auto")
    status = Column(String, default="pending")
    error_message = Column(Text, default="")
    vps_host = Column(String, nullable=True)
    vps_port = Column(Integer, default=22)
    vps_username = Column(String, nullable=True)
    vps_auth_method = Column(String, default="password")
    encrypted_password = Column(Text, default="")
    encrypted_private_key = Column(Text, default="")
    vps_server_id = Column(String, nullable=True)
    service_name = Column(String, nullable=True)
    env_vars = Column(JSON, default=dict)
    failed_step = Column(String, nullable=True)
    recommended_action = Column(Text, default="")
    rollback_available = Column(Boolean, default=False)
    rollback_dir = Column(String, nullable=True)
    deployment_time_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class VPSStepDB(Base):
    __tablename__ = "vps_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(String, ForeignKey("vps_deployments.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    display_name = Column(String, default="")
    status = Column(String, default="pending")
    message = Column(Text, default="")
    is_dangerous = Column(Boolean, default=False)
    order = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)


class VPSLogDB(Base):
    __tablename__ = "vps_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(String, ForeignKey("vps_deployments.id", ondelete="CASCADE"), nullable=False, index=True)
    step = Column(String, default="")
    status = Column(String, default="running")
    message = Column(Text, default="")
    severity = Column(String, default="info")
    command = Column(Text, default="")
    output = Column(Text, default="")
    timestamp = Column(DateTime, default=datetime.utcnow)


class VPSHealthCheckDB(Base):
    __tablename__ = "vps_health_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(String, ForeignKey("vps_deployments.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String, default="")
    status_code = Column(Integer, nullable=True)
    is_healthy = Column(Boolean, default=False)
    response_time_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)


class MemoryStore:
    """PostgreSQL memory store for persistent data."""

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self.engine = create_async_engine(
            config.url,
            pool_size=min(config.pool_size, 5),
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=300,
            pool_pre_ping=True,
            echo=config.echo,
        )
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self) -> None:
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Close the database engine."""
        await self.engine.dispose()

    async def get_session(self) -> AsyncSession:
        """Get a new database session."""
        return self.session_factory()

    # --- Project Operations ---

    async def create_project(self, project_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new project."""
        async with self.session_factory() as session:
            project = ProjectDB(**project_data)
            session.add(project)
            await session.commit()
            await session.refresh(project)
            return self._to_dict(project)

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Get a project by ID."""
        async with self.session_factory() as session:
            project = await session.get(ProjectDB, project_id)
            return self._to_dict(project) if project else None

    async def list_projects(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all projects."""
        from sqlalchemy import select

        async with self.session_factory() as session:
            result = await session.execute(
                select(ProjectDB).order_by(ProjectDB.created_at.desc()).limit(limit)
            )
            return [self._to_dict(p) for p in result.scalars().all()]

    async def update_project(self, project_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update a project."""
        async with self.session_factory() as session:
            project = await session.get(ProjectDB, project_id)
            if not project:
                return None
            for key, value in updates.items():
                setattr(project, key, value)
            project.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(project)
            return self._to_dict(project)

    # --- Task Operations ---

    async def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new task."""
        async with self.session_factory() as session:
            task = TaskDB(**task_data)
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self._to_dict(task)

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Get a task by ID."""
        async with self.session_factory() as session:
            task = await session.get(TaskDB, task_id)
            return self._to_dict(task) if task else None

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update a task."""
        async with self.session_factory() as session:
            task = await session.get(TaskDB, task_id)
            if not task:
                return None
            for key, value in updates.items():
                setattr(task, key, value)
            task.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(task)
            return self._to_dict(task)

    async def list_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List tasks with optional filters."""
        from sqlalchemy import select

        async with self.session_factory() as session:
            query = select(TaskDB)
            if project_id:
                query = query.where(TaskDB.project_id == project_id)
            if status:
                query = query.where(TaskDB.status == status)
            if agent_id:
                query = query.where(TaskDB.assigned_agent_id == agent_id)
            query = query.order_by(TaskDB.created_at.desc()).limit(limit)

            result = await session.execute(query)
            return [self._to_dict(t) for t in result.scalars().all()]

    # --- Conversation Operations ---

    async def create_conversation(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new conversation."""
        async with self.session_factory() as session:
            conv = ConversationDB(**data)
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            return self._to_dict(conv)

    async def add_message(self, conversation_id: str, message_data: dict[str, Any]) -> dict[str, Any]:
        """Add a message to a conversation."""
        async with self.session_factory() as session:
            message = MessageDB(conversation_id=conversation_id, **message_data)
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return self._to_dict(message)

    async def get_conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get all messages in a conversation."""
        from sqlalchemy import select

        async with self.session_factory() as session:
            result = await session.execute(
                select(MessageDB)
                .where(MessageDB.conversation_id == conversation_id)
                .order_by(MessageDB.timestamp)
            )
            return [self._to_dict(m) for m in result.scalars().all()]

    # --- Agent Logs ---

    async def log_agent_action(
        self,
        agent_id: str,
        message: str,
        task_id: str | None = None,
        level: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log an agent action."""
        async with self.session_factory() as session:
            log = AgentLogDB(
                agent_id=agent_id,
                task_id=task_id,
                level=level,
                message=message,
                metadata_json=metadata or {},
            )
            session.add(log)
            await session.commit()

    async def get_agent_logs(
        self,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get agent logs."""
        from sqlalchemy import select

        async with self.session_factory() as session:
            query = select(AgentLogDB)
            if agent_id:
                query = query.where(AgentLogDB.agent_id == agent_id)
            query = query.order_by(AgentLogDB.timestamp.desc()).limit(limit)

            result = await session.execute(query)
            return [self._to_dict(l) for l in result.scalars().all()]

    # --- User Operations (Auth) ---

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        async with self.session_factory() as session:
            user = UserDB(**user_data)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return self._to_dict(user)

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        from sqlalchemy import select
        async with self.session_factory() as session:
            result = await session.execute(select(UserDB).where(UserDB.email == email.lower().strip()))
            user = result.scalar_one_or_none()
            return self._to_dict(user) if user else None

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            user = await session.get(UserDB, user_id)
            return self._to_dict(user) if user else None

    async def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            user = await session.get(UserDB, user_id)
            if not user:
                return None
            for key, value in updates.items():
                setattr(user, key, value)
            await session.commit()
            await session.refresh(user)
            return self._to_dict(user)

    async def delete_user(self, user_id: str) -> bool:
        async with self.session_factory() as session:
            user = await session.get(UserDB, user_id)
            if not user:
                return False
            await session.delete(user)
            await session.commit()
            return True

    async def list_pending_users(self) -> list[dict[str, Any]]:
        from sqlalchemy import select
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserDB).where(UserDB.status == "pending").order_by(UserDB.created_at.desc())
            )
            return [self._to_dict(u) for u in result.scalars().all()]

    async def list_all_users(self) -> list[dict[str, Any]]:
        from sqlalchemy import select
        async with self.session_factory() as session:
            result = await session.execute(select(UserDB).order_by(UserDB.created_at.desc()))
            return [self._to_dict(u) for u in result.scalars().all()]

    # --- VPS Deployment Operations ---

    async def save_vps_deployment(self, data: dict[str, Any]) -> None:
        async with self.session_factory() as session:
            existing = await session.get(VPSDeploymentDB, data["id"])
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                session.add(VPSDeploymentDB(**data))
            await session.commit()

    async def get_vps_deployment(self, dep_id: str) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            dep = await session.get(VPSDeploymentDB, dep_id)
            return self._to_dict(dep) if dep else None

    async def list_vps_deployments(self) -> list[dict[str, Any]]:
        from sqlalchemy import select
        async with self.session_factory() as session:
            result = await session.execute(select(VPSDeploymentDB).order_by(VPSDeploymentDB.created_at.desc()))
            return [self._to_dict(d) for d in result.scalars().all()]

    async def delete_vps_deployment(self, dep_id: str) -> None:
        async with self.session_factory() as session:
            dep = await session.get(VPSDeploymentDB, dep_id)
            if dep:
                await session.delete(dep)
                await session.commit()

    async def save_vps_steps(self, dep_id: str, steps: list[dict[str, Any]]) -> None:
        async with self.session_factory() as session:
            from sqlalchemy import delete as sql_delete
            await session.execute(sql_delete(VPSStepDB).where(VPSStepDB.deployment_id == dep_id))
            for s in steps:
                session.add(VPSStepDB(deployment_id=dep_id, **s))
            await session.commit()

    async def get_vps_steps(self, dep_id: str) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(VPSStepDB).where(VPSStepDB.deployment_id == dep_id).order_by(VPSStepDB.order)
            )
            return [self._to_dict(s) for s in result.scalars().all()]

    async def append_vps_log(self, dep_id: str, log_data: dict[str, Any]) -> None:
        async with self.session_factory() as session:
            session.add(VPSLogDB(deployment_id=dep_id, **log_data))
            await session.commit()

    async def get_vps_logs(self, dep_id: str, limit: int = 200) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(VPSLogDB).where(VPSLogDB.deployment_id == dep_id)
                .order_by(VPSLogDB.id.desc()).limit(limit)
            )
            return [self._to_dict(l) for l in reversed(result.scalars().all())]

    async def append_vps_health_check(self, dep_id: str, hc_data: dict[str, Any]) -> None:
        async with self.session_factory() as session:
            session.add(VPSHealthCheckDB(deployment_id=dep_id, **hc_data))
            await session.commit()

    async def get_vps_health_checks(self, dep_id: str) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(VPSHealthCheckDB).where(VPSHealthCheckDB.deployment_id == dep_id)
            )
            return [self._to_dict(h) for h in result.scalars().all()]

    # --- Utility ---

    @staticmethod
    def _to_dict(obj: Any) -> dict[str, Any]:
        """Convert SQLAlchemy model to dict."""
        if obj is None:
            return {}
        return {
            c.name: getattr(obj, c.name)
            for c in obj.__table__.columns
        }
