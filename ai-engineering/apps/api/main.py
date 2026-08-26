"""AIED API - FastAPI Application Entry Point."""

from __future__ import annotations

import asyncio
import logging
import socket
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

# Force UTF-8 stdout/stderr so agent output with unicode (e.g. arrows, em-dashes)
# never crashes the process with a cp1252 'charmap' UnicodeEncodeError on Windows.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Force IPv4 for localhost only - some local DNS returns IPv6 which Python can't connect to
_original_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in ("localhost", "127.0.0.1", "::1"):
        return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

# Force unverified SSL context globally to bypass certificate expiration/clock sync errors
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
from fastapi import FastAPI, File, Form, UploadFile, Body
from fastapi.responses import JSONResponse

from fastapi.middleware.cors import CORSMiddleware

from agents.hermes.orchestrator import HermesOrchestrator
from agents.openclaw.engine import OpenClawEngine
from llms.manager import LLMManager
from pipeline.engine import Pipeline
from memory.postgres.database import MemoryStore
from memory.redis.queue import RedisStore
from shared.config import config

logger = logging.getLogger(__name__)

# --- Application State ---

app_state: dict[str, any] = {}


def _persist_both(hermes, pipeline):
    try:
        from agents.hermes.orchestrator import _persist_hermes
        _persist_hermes(hermes)
    except Exception as e:
        logger.error(f"Failed to persist hermes: {e}")
    try:
        pipeline._persist()
    except Exception as e:
        logger.error(f"Failed to persist pipeline: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan - startup and shutdown."""
    logger.info("Starting AIED API...")

    # Initialize LLM Manager (Hybrid approach)
    llm_manager = LLMManager(config.llm)
    try:
        await llm_manager.initialize()
        logger.info("LLM Manager initialized")
    except Exception as e:
        logger.warning(f"LLM Manager init failed (non-fatal): {e}")
    app_state["llm_manager"] = llm_manager

    # Initialize Pipeline Engine
    hermes = HermesOrchestrator(config, llm_manager)
    await hermes.initialize()
    app_state["hermes"] = hermes

    pipeline = Pipeline(hermes)
    app_state["pipeline"] = pipeline

    # Initialize OpenClaw Engine
    try:
        openclaw = OpenClawEngine(config, llm_manager)
        await openclaw.initialize()
        app_state["openclaw"] = openclaw
        logger.info("OpenClaw Engine initialized")
    except Exception as e:
        logger.warning(f"OpenClaw init failed (non-fatal): {e}")

    # Initialize PostgreSQL (Neon)
    try:
        from memory.postgres.database import MemoryStore
        from shared.config import DatabaseConfig
        memory = MemoryStore(DatabaseConfig())
        await memory.initialize()
        app_state["memory"] = memory
        logger.info("PostgreSQL (Neon) connected")
        # Wire memory store to VPS engine
        vps_engine.set_memory_store(memory)
        await vps_engine.load_from_db()
    except Exception as e:
        app_state["memory"] = None
        logger.warning(f"PostgreSQL init failed (non-fatal): {e}")

    # Skip Redis
    app_state["redis"] = None

    # Initialize Layer 1 - Foundation Knowledge Base (9 product repositories)
    try:
        from knowledge import KnowledgeStore
        kb = KnowledgeStore()
        app_state["kb"] = kb
        hermes.set_knowledge_source(kb)
        logger.info(f"Knowledge Base initialized ({len(kb.repositories)} repositories, {kb.stats()['items']} items)")
    except Exception as e:
        app_state["kb"] = None
        logger.warning(f"Knowledge Base init failed (non-fatal): {e}")

    # Initialize Layer 2 - Executive Product Board
    try:
        from board.engine import ExecutiveProductBoard
        board = ExecutiveProductBoard(config, llm_manager, kb=app_state.get("kb"))
        app_state["board"] = board
        logger.info(f"Executive Product Board initialized ({len(board.members())} members)")
    except Exception as e:
        app_state["board"] = None
        logger.warning(f"Executive Product Board init failed (non-fatal): {e}")

    # Initialize Layer 3 - Product Research & Discovery Division
    try:
        from research.engine import ResearchDivision
        research = ResearchDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["research"] = research
        logger.info(f"Product Research & Discovery Division initialized ({len(research.departments())} departments)")
    except Exception as e:
        app_state["research"] = None
        logger.warning(f"Product Research & Discovery Division init failed (non-fatal): {e}")

    # Initialize Layer 4 - UX & Human Experience Division
    try:
        from ux.engine import UXDivision
        ux = UXDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["ux"] = ux
        logger.info(f"UX & Human Experience Division initialized ({len(ux.departments())} departments)")
    except Exception as e:
        app_state["ux"] = None
        logger.warning(f"UX & Human Experience Division init failed (non-fatal): {e}")

    # Initialize Layer 5 - Visual Design & Design System Division
    try:
        from design.engine import DesignDivision
        design = DesignDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["design"] = design
        logger.info(f"Visual Design & Design System Division initialized ({len(design.departments())} departments)")
    except Exception as e:
        app_state["design"] = None
        logger.warning(f"Visual Design & Design System Division init failed (non-fatal): {e}")

    # Initialize Layer 6 - Growth, Conversion & Customer Success Division
    try:
        from growth.engine import GrowthDivision
        growth = GrowthDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["growth"] = growth
        logger.info(f"Growth, Conversion & Customer Success Division initialized ({len(growth.departments())} departments)")
    except Exception as e:
        app_state["growth"] = None
        logger.warning(f"Growth, Conversion & Customer Success Division init failed (non-fatal): {e}")

    # Initialize Layer 7 - Quality, Security & Release Excellence Division
    try:
        from quality.engine import QualityDivision
        quality = QualityDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["quality"] = quality
        logger.info(f"Quality, Security & Release Excellence Division initialized ({len(quality.departments())} departments)")
    except Exception as e:
        app_state["quality"] = None
        logger.warning(f"Quality, Security & Release Excellence Division init failed (non-fatal): {e}")

    # Initialize Layer 8 - Intelligence, Learning & Continuous Improvement Division
    try:
        from intelligence.engine import IntelligenceDivision
        intelligence = IntelligenceDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["intelligence"] = intelligence
        logger.info(f"Intelligence, Learning & Continuous Improvement Division initialized ({len(intelligence.departments())} departments)")
    except Exception as e:
        app_state["intelligence"] = None
        logger.warning(f"Intelligence, Learning & Continuous Improvement Division init failed (non-fatal): {e}")

    # Initialize Layer 9 - Enterprise AI Governance & Orchestration Division
    try:
        from governance.engine import GovernanceDivision
        governance = GovernanceDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["governance"] = governance
        logger.info(f"Enterprise AI Governance & Orchestration Division initialized ({len(governance.departments())} departments)")
    except Exception as e:
        app_state["governance"] = None
        logger.warning(f"Enterprise AI Governance & Orchestration Division init failed (non-fatal): {e}")

    # Initialize Layer 10 - Enterprise Knowledge & Digital Twin Platform
    try:
        from ekdt.engine import EkdtDivision
        ekdt = EkdtDivision(config, llm_manager, kb=app_state.get("kb"))
        app_state["ekdt"] = ekdt
        logger.info(f"Enterprise Knowledge & Digital Twin Platform initialized ({len(ekdt.departments())} knowledge systems)")
    except Exception as e:
        app_state["ekdt"] = None
        logger.warning(f"Enterprise Knowledge & Digital Twin Platform init failed (non-fatal): {e}")

    # Initialize Layer 0 - Company Information
    try:
        from company.store import CompanyStore
        company_store = CompanyStore()
        app_state["company"] = company_store
        logger.info(f"Layer 0 Company Information initialized ({len(company_store.data.projects)} projects)")
    except Exception as e:
        app_state["company"] = None
        logger.warning(f"Layer 0 Company Information init failed (non-fatal): {e}")

    # Initialize Cross-Layer Workflow Orchestration (Board -> Research -> UX -> Design -> Growth -> Quality)
    try:
        from workflow.engine import WorkflowEngine
        workflow = WorkflowEngine(
            config,
            llm_manager,
            board=app_state.get("board"),
            research=app_state.get("research"),
            ux=app_state.get("ux"),
            design=app_state.get("design"),
            growth=app_state.get("growth"),
            quality=app_state.get("quality"),
            intelligence=app_state.get("intelligence"),
            governance=app_state.get("governance"),
            ekdt=app_state.get("ekdt"),
            kb=app_state.get("kb"),
        )
        app_state["workflow"] = workflow
        logger.info(f"Cross-Layer Workflow Orchestration initialized ({len(workflow.stage_defs())} gated stages)")
    except Exception as e:
        app_state["workflow"] = None
        logger.warning(f"Cross-Layer Workflow Orchestration init failed (non-fatal): {e}")

    logger.info("AIED API started successfully")

    # Initialize auth system
    memory = app_state.get("memory")
    if memory:
        await init_auth(memory)
        logger.info("Auth system initialized (Neon DB)")
    else:
        logger.warning("Auth skipped (no database)")

    yield

    # Shutdown
    logger.info("Shutting down AIED API...")
    try:
        await llm_manager.close()
    except Exception:
        pass
    memory = app_state.get("memory")
    if memory:
        try:
            await memory.close()
        except Exception:
            pass
    logger.info("AIED API shut down")


# --- FastAPI App ---

app = FastAPI(
    title="AIED API",
    description="Britsync AI Engineering Department - Autonomous Multi-Agent Software Engineering Platform",
    version=config.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health ---

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": config.version,
        "agents": len(app_state.get("hermes", HermesOrchestrator.__new__(HermesOrchestrator)).agents) if "hermes" in app_state else 0,
    }


# --- Auth ---

from apps.api.auth import (
    init_auth, create_user, login_user, get_user_from_token,
    approve_user, reject_user, delete_user, get_pending_users, get_all_users,
    send_approval_email, send_admin_notification,
)

@app.post("/api/auth/signup")
async def auth_signup(data: dict):
    """Register a new user (goes to pending status)."""
    memory = app_state.get("memory")
    if not memory:
        return JSONResponse({"error": "Database not available"}, status_code=503)
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    company_name = data.get("company_name", "")
    company_role = data.get("company_role", "")
    company_size = data.get("company_size", "")
    company_website = data.get("company_website", "")

    if not name or not email or not password:
        return JSONResponse({"error": "Name, email, and password are required"}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"error": "Password must be at least 6 characters"}, status_code=400)

    result = await create_user(memory, name, email, password, company_name, company_role, company_size, company_website)
    if "error" in result:
        return JSONResponse(result, status_code=400)

    send_admin_notification(name, email, company_name)

    pipeline = app_state.get("pipeline")
    if pipeline:
        pipeline._add_notification(
            "New User Pending Approval",
            f"{name} ({email}) has signed up and is waiting for admin approval.",
            "",
            "approval",
            for_admin=True,
        )

    if company_name:
        try:
            cs = app_state.get("company")
            if cs:
                cs.add_user_company(name, email, company_name, company_role, company_size, company_website)
        except Exception:
            pass

    return result


@app.post("/api/auth/login")
async def auth_login(data: dict):
    """Login with email/password."""
    memory = app_state.get("memory")
    if not memory:
        return JSONResponse({"error": "Database not available"}, status_code=503)
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return JSONResponse({"error": "Email and password are required"}, status_code=400)

    result = await login_user(memory, email, password)
    if "error" in result:
        return JSONResponse(result, status_code=401)
    return result


@app.get("/api/auth/me")
async def auth_me(token: str = ""):
    """Get current user from token."""
    memory = app_state.get("memory")
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    user_id = get_user_from_token(token)
    if not user_id:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=401)
    if memory:
        user = await memory.get_user_by_id(user_id)
        if user:
            if user.get("status") == "pending":
                return JSONResponse({"error": "Account pending admin approval"}, status_code=403)
            if user.get("status") == "rejected":
                return JSONResponse({"error": "Account has been rejected"}, status_code=403)
            safe = {k: v for k, v in user.items() if k != "password_hash"}
            if hasattr(safe.get("created_at"), "isoformat"):
                safe["created_at"] = safe["created_at"].isoformat()
            return {"user": safe}
    return JSONResponse({"error": "User not found"}, status_code=404)


@app.post("/api/auth/update-profile")
async def auth_update_profile(data: dict):
    """Update user profile (name only)."""
    memory = app_state.get("memory")
    token = data.get("token", "")
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    user_id = get_user_from_token(token)
    if not user_id:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=401)
    name = data.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Name is required"}, status_code=400)
    result = await memory.update_user(user_id, {"name": name})
    if not result:
        return JSONResponse({"error": "User not found"}, status_code=404)
    safe = {k: v for k, v in result.items() if k != "password_hash"}
    if hasattr(safe.get("created_at"), "isoformat"):
        safe["created_at"] = safe["created_at"].isoformat()
    return {"user": safe}


@app.get("/api/auth/pending-users")
async def auth_pending_users():
    """Get all pending user requests (admin)."""
    memory = app_state.get("memory")
    if not memory:
        return {"users": []}
    return {"users": await get_pending_users(memory)}


@app.get("/api/auth/all-users")
async def auth_all_users():
    """Get all users (admin)."""
    memory = app_state.get("memory")
    if not memory:
        return {"users": []}
    return {"users": await get_all_users(memory)}


@app.post("/api/auth/approve/{user_id}")
async def auth_approve(user_id: str):
    """Approve a user (admin)."""
    memory = app_state.get("memory")
    if not memory:
        return JSONResponse({"error": "Database not available"}, status_code=503)
    result = await approve_user(memory, user_id)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    user = result.get("user", {})
    send_approval_email(user.get("email", ""), user.get("name", ""))
    pipeline = app_state.get("pipeline")
    if pipeline:
        pipeline._add_notification("User Approved", f"{user.get('name', 'User')} ({user.get('email', '')}) has been approved.", "", "success", for_admin=True)
    return result


@app.post("/api/auth/reject/{user_id}")
async def auth_reject(user_id: str):
    """Reject a user (admin)."""
    memory = app_state.get("memory")
    if not memory:
        return JSONResponse({"error": "Database not available"}, status_code=503)
    result = await reject_user(memory, user_id)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result


@app.post("/api/auth/delete/{user_id}")
async def auth_delete(user_id: str):
    """Delete a user (admin)."""
    memory = app_state.get("memory")
    if not memory:
        return JSONResponse({"error": "Database not available"}, status_code=503)
    result = await delete_user(memory, user_id)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result


# --- Projects ---

@app.get("/api/projects")
async def list_projects(user_id: str = ""):
    """List projects for a user."""
    hermes: HermesOrchestrator = app_state["hermes"]
    projects = hermes.projects.values()
    if user_id:
        projects = [p for p in projects if getattr(p, "user_id", "") == user_id]
    else:
        projects = []
    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "codename": p.codename,
                "description": p.description,
                "status": p.status.value,
                "tech_stack": p.tech_stack,
                "tasks_count": len(p.tasks),
                "created_at": p.created_at.isoformat(),
                "mode": getattr(p, "mode", "scratch"),
                "folder": getattr(p, "folder", ""),
            }
            for p in projects
        ]
    }


@app.post("/api/projects")
async def create_project(data: dict):
    """Create a new project."""
    hermes: HermesOrchestrator = app_state["hermes"]
    project = await hermes.create_project(
        name=data["name"],
        codename=data["codename"],
        description=data.get("description", ""),
        tech_stack=data.get("tech_stack", []),
        user_id=data.get("user_id", ""),
    )
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "codename": project.codename,
            "description": project.description,
            "status": project.status.value,
            "tech_stack": project.tech_stack,
            "tasks_count": len(project.tasks),
            "created_at": project.created_at.isoformat(),
            "mode": getattr(project, "mode", "scratch"),
            "folder": getattr(project, "folder", ""),
            "user_id": getattr(project, "user_id", ""),
        }
    }


# --- Tasks ---

@app.get("/api/tasks")
async def list_tasks(project_id: str | None = None, status: str | None = None, task_mode: str | None = None):
    """List tasks with optional filters."""
    hermes: HermesOrchestrator = app_state["hermes"]
    tasks = list(hermes.tasks.values())

    if project_id:
        tasks = [t for t in tasks if t.project_id == project_id]
    if status:
        tasks = [t for t in tasks if t.status.value == status]
    if task_mode:
        tasks = [t for t in tasks if (t.metadata or {}).get("task_mode") == task_mode]

    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status.value,
                "priority": t.priority.value,
                "assigned_to": t.assigned_agent_id,
                "project_id": t.project_id,
                "result": t.result[:500] if t.result else None,
                "error": t.error,
                "task_mode": (t.metadata or {}).get("task_mode", "developer"),
                "created_at": t.created_at.isoformat(),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]
    }


@app.post("/api/tasks")
async def create_task(data: dict):
    """Create a new task."""
    hermes: HermesOrchestrator = app_state["hermes"]
    from shared.models import TaskPriority
    task_mode = data.get("task_mode", "developer")
    if task_mode not in ("developer", "tester"):
        task_mode = "developer"
    metadata = dict(data.get("metadata") or {})
    metadata["task_mode"] = task_mode
    task = await hermes.create_task(
        title=data["title"],
        description=data.get("description", ""),
        project_id=data.get("project_id"),
        priority=TaskPriority(data.get("priority", "medium")),
        assigned_agent_id=data.get("assigned_agent_id"),
        metadata=metadata,
    )
    return {
        "task": {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority.value,
            "assigned_to": task.assigned_agent_id,
            "project_id": task.project_id,
            "task_mode": task_mode,
        }
    }


@app.post("/api/tasks/{task_id}/execute")
async def execute_task(task_id: str):
    """Execute a task using its assigned agent's LLM."""
    hermes: HermesOrchestrator = app_state["hermes"]
    result = await hermes.execute_task(task_id)
    return result


@app.post("/api/projects/{project_id}/execute")
async def execute_project(project_id: str):
    """Execute all pending tasks in a project."""
    hermes: HermesOrchestrator = app_state["hermes"]
    result = await hermes.execute_project_tasks(project_id)
    return result


# --- Agents ---

@app.get("/api/agents")
async def list_agents():
    """List all agents."""
    hermes: HermesOrchestrator = app_state["hermes"]
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "role": a.role.value,
                "department": a.department,
                "model": a.model_name,
                "capabilities": a.capabilities,
                "status": hermes.agent_states[a.id].status.value if a.id in hermes.agent_states else "offline",
                "tasks_completed": hermes.agent_states[a.id].tasks_completed if a.id in hermes.agent_states else 0,
                "tasks_failed": hermes.agent_states[a.id].tasks_failed if a.id in hermes.agent_states else 0,
                "current_task": hermes.agent_states[a.id].current_task_id if a.id in hermes.agent_states else None,
            }
            for a in hermes.agents.values()
        ]
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details."""
    hermes: HermesOrchestrator = app_state["hermes"]
    if agent_id not in hermes.agents:
        return {"error": "Agent not found"}

    agent = hermes.agents[agent_id]
    state = hermes.agent_states.get(agent_id)
    return {
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role.value,
            "department": agent.department,
            "model": agent.model_name,
            "capabilities": agent.capabilities,
            "status": state.status.value if state else "offline",
            "tasks_completed": state.tasks_completed if state else 0,
            "tasks_failed": state.tasks_failed if state else 0,
            "current_task": state.current_task_id if state else None,
        }
    }


@app.post("/api/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, data: dict):
    """Chat directly with an agent."""
    hermes: HermesOrchestrator = app_state["hermes"]
    result = await hermes.chat_with_agent(
        agent_id=agent_id,
        message=data["message"],
        project_id=data.get("project_id"),
        context=data.get("context"),
    )
    return result


# --- Orchestrator ---

@app.post("/api/orchestrate")
async def orchestrate(data: dict):
    """Submit a business request to Hermes for orchestration."""
    hermes: HermesOrchestrator = app_state["hermes"]
    result = await hermes.process_request(
        request=data["request"],
        project_id=data.get("project_id"),
        context=data.get("context"),
    )
    return result


# --- OpenClaw ---

@app.post("/api/openclaw/execute")
async def openclaw_execute(data: dict):
    """Execute a task with OpenClaw."""
    openclaw: OpenClawEngine = app_state["openclaw"]
    from shared.models import Task, TaskPriority, TaskStatus
    task = Task(
        title=data.get("title", "Execute Task"),
        description=data.get("description", ""),
        priority=TaskPriority(data.get("priority", "medium")),
    )
    result = await openclaw.execute_task(
        task=task,
        repository_url=data.get("repository_url"),
        context=data.get("context"),
    )
    return result


@app.post("/api/openclaw/review")
async def openclaw_review(data: dict):
    """Review code with OpenClaw."""
    openclaw: OpenClawEngine = app_state["openclaw"]
    result = await openclaw.review_code(
        code=data["code"],
        language=data.get("language", "python"),
        focus=data.get("focus", "general"),
    )
    return result


# --- Dashboard ---

@app.get("/api/dashboard")
async def dashboard(user_id: str = ""):
    """Get dashboard data."""
    hermes: HermesOrchestrator = app_state["hermes"]
    return await hermes.get_dashboard_data(user_id=user_id)


# --- Memory ---

@app.get("/api/memory/projects")
async def list_memory_projects():
    """List projects from persistent memory."""
    memory: MemoryStore = app_state["memory"]
    projects = await memory.list_projects()
    return {"projects": projects}


@app.get("/api/memory/tasks")
async def list_memory_tasks(project_id: str | None = None):
    """List tasks from persistent memory."""
    memory: MemoryStore = app_state["memory"]
    tasks = await memory.list_tasks(project_id=project_id)
    return {"tasks": tasks}


@app.get("/api/memory/logs")
async def list_agent_logs(agent_id: str | None = None):
    """List agent logs."""
    memory: MemoryStore = app_state["memory"]
    logs = await memory.get_agent_logs(agent_id=agent_id)
    return {"logs": logs}


# --- File Operations ---

import os

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "projects")


@app.post("/api/files/write")
async def write_files(data: dict):
    """Write files extracted from agent responses to disk."""
    files = data.get("files", [])
    project = data.get("project", "default")

    project_dir = os.path.join(PROJECTS_DIR, project)
    os.makedirs(project_dir, exist_ok=True)

    written = []
    errors = []

    for file_info in files:
        filename = file_info.get("filename", "")
        content = file_info.get("content", "")

        if not filename or not content:
            continue

        # Clean up filename
        filename = filename.lstrip("/").lstrip("\\")
        filepath = os.path.join(project_dir, filename)

        try:
            # Create subdirectories if needed
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            written.append({"path": os.path.relpath(filepath, project_dir), "size": len(content)})
            logger.info(f"File written: {filepath}")
        except Exception as e:
            errors.append({"path": filename, "error": str(e)})
            logger.error(f"Failed to write {filepath}: {e}")

    return {
        "status": "ok" if not errors else "partial",
        "project_dir": project_dir,
        "files": written,
        "errors": errors,
    }


@app.get("/api/files/list")
async def list_files(project: str = "default"):
    """List files in a project directory."""
    project_dir = os.path.join(PROJECTS_DIR, project)
    if not os.path.exists(project_dir):
        return {"files": []}

    files = []
    for root, dirs, filenames in os.walk(project_dir):
        for fn in filenames:
            filepath = os.path.join(root, fn)
            rel_path = os.path.relpath(filepath, project_dir)
            files.append({
                "path": rel_path,
                "size": os.path.getsize(filepath),
            })

    return {"files": files, "project_dir": project_dir}


@app.post("/api/files/read")
async def read_file(data: dict):
    """Read a file from a project."""
    project = data.get("project", "default")
    filepath = data.get("path", "")

    full_path = os.path.join(PROJECTS_DIR, project, filepath)
    if not os.path.exists(full_path):
        return {"error": "File not found"}

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    return {"content": content, "path": filepath}


@app.get("/api/files/browse")
async def browse_folders(path: str = ""):
    """List folders at a given path so the user can browse their filesystem."""
    import platform

    if not path:
        if platform.system() == "Windows":
            path = "C:\\"
        else:
            path = os.path.expanduser("~")

    path = os.path.normpath(path)

    if not os.path.exists(path):
        return {"error": "Path does not exist", "folders": [], "current_path": path, "parent": ""}

    folders = []
    try:
        for item in os.listdir(path):
            full = os.path.join(path, item)
            if os.path.isdir(full) and not item.startswith("."):
                folders.append({"name": item, "path": full, "is_dir": True})
    except PermissionError:
        return {"error": "Permission denied", "folders": [], "current_path": path, "parent": os.path.dirname(path)}

    folders.sort(key=lambda x: x["name"].lower())
    parent = os.path.dirname(path) if path and path != os.path.dirname(path) else ""

    return {"folders": folders, "current_path": path, "parent": parent}


@app.post("/api/files/validate-path")
async def validate_path(data: dict):
    """Check if a path exists and is a directory."""
    path = data.get("path", "")
    if not path:
        return {"valid": False, "error": "No path provided"}
    if not os.path.exists(path):
        return {"valid": False, "error": "Path does not exist"}
    if not os.path.isdir(path):
        return {"valid": False, "error": "Path is not a directory"}
    return {"valid": True, "path": path}


@app.get("/api/system/select-folder")
async def system_select_folder():
    """Open a native OS dialog to select a folder and return the absolute path."""
    import asyncio
    
    script = (
        "import tkinter as tk, os\n"
        "from tkinter import filedialog\n"
        "try:\n"
        "    root = tk.Tk()\n"
        "    root.withdraw()\n"
        "    root.attributes('-topmost', True)\n"
        "    folder = filedialog.askdirectory(parent=root, title='Select Project Folder')\n"
        "    root.destroy()\n"
        "    if folder:\n"
        "        print(os.path.normpath(folder))\n"
        "except Exception as e:\n"
        "    pass\n"
    )
    
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        folder_path = stdout.decode('utf-8', errors='replace').strip()
        return {"path": folder_path}
    except Exception as e:
        return {"error": str(e), "path": ""}

# --- Pipeline ---

@app.get("/api/pipeline/{task_id}")
async def get_pipeline(task_id: str):
    """Get pipeline status for a task."""
    pipeline: Pipeline = app_state["pipeline"]
    status = pipeline.get_pipeline_status(task_id)
    if not status:
        return {"error": "No pipeline for this task"}
    return status


@app.get("/api/pipelines")
async def get_all_pipelines():
    """Get status of all active pipelines."""
    pipeline: Pipeline = app_state["pipeline"]
    pipelines = {}
    for tid, task in pipeline.tasks.items():
        pipelines[tid] = task.to_dict()
    return {"pipelines": pipelines}


@app.post("/api/pipeline/{task_id}/start")
async def start_pipeline(task_id: str):
    """Start the build pipeline for a task."""
    pipeline: Pipeline = app_state["pipeline"]
    hermes: HermesOrchestrator = app_state["hermes"]

    # Check if pipeline already exists and is not idle/failed/completed
    existing = pipeline.get_task(task_id)
    if existing and existing.stage.value not in ("idle", "failed", "completed"):
        return {"error": "Pipeline already running", "stage": existing.stage.value}

    # If an existing task was already created (e.g. by CEO chat flow), reuse it
    if existing:
        existing._persist_callback = pipeline._persist
        pipeline._persist()
        task_mode = existing.task_mode or "developer"
        if task_mode == "tester":
            pipeline._spawn_task(pipeline.start_testing(task_id), task_id)
        else:
            pipeline._spawn_task(pipeline.start_building(task_id), task_id)
        return {"status": "started", "task_id": task_id, "task_mode": task_mode}

    hermes_task = hermes.tasks.get(task_id)
    if not hermes_task:
        return {"error": "Task not found"}

    project = hermes.projects.get(hermes_task.project_id) if hermes_task.project_id else None
    project_desc = project.description if project else ""
    project_name = project.name if project else ""

    # Find project folder from project or request
    project_folder = ""
    if project:
        # Check if project has folder attribute
        project_folder = getattr(project, "folder", "") or ""

    from pipeline.engine import PipelineTask
    task_mode = (hermes_task.metadata or {}).get("task_mode", "developer")
    pt = PipelineTask(
        task_id=task_id,
        project_id=hermes_task.project_id or "",
        title=hermes_task.title,
        description=hermes_task.description,
        project_mode=getattr(project, "mode", "scratch") if project else "scratch",
        project_folder=project_folder,
        project_description=project_desc,
        project_name=project_name,
        task_mode=task_mode,
    )
    pipeline.tasks[task_id] = pt
    pt._persist_callback = pipeline._persist
    pipeline._persist()

    if task_mode == "tester":
        pipeline._spawn_task(pipeline.start_testing(task_id), task_id)
    else:
        pipeline._spawn_task(pipeline.start_building(task_id), task_id)
    return {"status": "started", "task_id": task_id, "task_mode": task_mode}


@app.post("/api/pipeline/{task_id}/start-testing")
async def start_testing(task_id: str):
    """Start (or re-run) the Tester Agent flow for a task. Test-only, never fixes."""
    pipeline: Pipeline = app_state["pipeline"]
    hermes: HermesOrchestrator = app_state["hermes"]

    existing = pipeline.get_task(task_id)
    if existing and existing.stage.value in ("testing", "fixing"):
        return {"error": "Task is already running", "stage": existing.stage.value}

    if not existing:
        hermes_task = hermes.tasks.get(task_id)
        if not hermes_task:
            return {"error": "Task not found"}
        project = hermes.projects.get(hermes_task.project_id) if hermes_task.project_id else None
        project_folder = getattr(project, "folder", "") if project else ""
        from pipeline.engine import PipelineTask
        pt = PipelineTask(
            task_id=task_id,
            project_id=hermes_task.project_id or "",
            title=hermes_task.title,
            description=hermes_task.description,
            project_mode=getattr(project, "mode", "scratch") if project else "scratch",
            project_folder=project_folder,
            project_description=project.description if project else "",
            project_name=project.name if project else "",
            task_mode="tester",
        )
        pipeline.tasks[task_id] = pt
        pt._persist_callback = pipeline._persist
        pipeline._persist()

    pipeline._spawn_task(pipeline.start_testing(task_id), task_id)
    return {"status": "testing_started", "task_id": task_id}


@app.post("/api/pipeline/{task_id}/fix-with-dev-team")
async def fix_with_dev_team(task_id: str):
    """Send the Tester Agent's findings to the Development Team to fix."""
    pipeline: Pipeline = app_state["pipeline"]
    task = pipeline.get_task(task_id)
    if not task:
        return {"error": "No pipeline for this task"}
    pipeline._spawn_task(pipeline.fix_with_dev_team(task_id), task_id)
    return {"status": "fixing_started", "task_id": task_id}


@app.post("/api/pipeline/{task_id}/approve-plan")
async def approve_plan(task_id: str):
    """Approve the plan."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline._spawn_task(pipeline.approve_plan(task_id), task_id)
    return {"status": "approved"}


@app.post("/api/pipeline/{task_id}/reject-plan")
async def reject_plan(task_id: str, data: dict = {}):
    """Reject the plan with feedback."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline._spawn_task(pipeline.reject_plan(task_id, data.get("feedback", "")), task_id)
    return {"status": "rejected"}


@app.post("/api/pipeline/{task_id}/stop")
async def stop_pipeline(task_id: str):
    """Stop a running pipeline."""
    pipeline: Pipeline = app_state["pipeline"]
    task = pipeline.get_task(task_id)
    if not task:
        return {"error": "No pipeline for this task"}
    from pipeline.engine import PipelineStage
    pipeline.cancel_task(task_id)
    task.stage = PipelineStage.FAILED
    task.error = "Stopped by user"
    task.current_agent = ""
    task.current_action = ""
    task.add_history("stopped", "Pipeline stopped by user")
    pipeline._add_notification("Pipeline Stopped", f"Build for '{task.title}' was stopped.", task_id, "warning")
    return {"status": "stopped"}


@app.post("/api/pipeline/{task_id}/restart")
async def restart_pipeline(task_id: str, data: dict = {}):
    """Restart a task from Layer 1 (Planning) regardless of project mode or stage."""
    pipeline: Pipeline = app_state["pipeline"]
    hermes: HermesOrchestrator = app_state["hermes"]
    
    title = data.get("title", "")
    description = data.get("description", "")
    
    # Sync hermes task store if title/description updated
    hermes_task = hermes.tasks.get(task_id)
    if hermes_task:
        if title.strip():
            hermes_task.title = title.strip()
        if description.strip():
            hermes_task.description = description.strip()

    ok = await pipeline.restart_pipeline(task_id, updated_title=title, updated_description=description)
    if not ok:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    _persist_both(hermes, pipeline)
    return {"status": "restarted", "task_id": task_id}


@app.post("/api/pipeline/{task_id}/approve-deploy")
async def approve_deploy(task_id: str):
    """Approve build for deployment."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline._spawn_task(pipeline.approve_for_deploy(task_id), task_id)
    return {"status": "deploying"}


@app.post("/api/pipeline/{task_id}/prebuilt-action")
async def prebuilt_action(task_id: str, data: dict):
    """Start a pre-built project action."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline._spawn_task(pipeline.start_prebuilt_action(task_id, data.get("action", "analyze"), data.get("description", "")), task_id)
    return {"status": "started"}


@app.post("/api/pipeline/{task_id}/solve-issues")
async def solve_issues(task_id: str, data: dict = {}):
    """Solve issues found in pre-built project."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline._spawn_task(pipeline.solve_issues(task_id, data.get("description", "")), task_id)
    return {"status": "fixing"}


@app.post("/api/pipeline/{task_id}/submit-issue")
async def submit_issue(task_id: str, data: dict = {}):
    """Submit a user issue/feedback for a running pipeline task."""
    pipeline: Pipeline = app_state["pipeline"]
    desc = data.get("description", "").strip()
    if not desc:
        return JSONResponse({"error": "description is required"}, status_code=400)
    ok = pipeline.submit_issue(task_id, desc)
    if not ok:
        return JSONResponse({"error": "task not found"}, status_code=404)
    return {"status": "submitted"}


@app.post("/api/pipeline/{task_id}/deploy-to-store")
async def deploy_to_store(task_id: str, data: dict = {}):
    """Deploy APK to BritStore via pipeline task. Modes:
    - update: apk_path, package_name, version, version_code, release_notes
    - new: apk_path + agent generates content. User adds icon/screenshots via store dashboard.
    """
    pipeline: Pipeline = app_state["pipeline"]
    apk_path = data.get("apk_path", "").strip()
    package_name = data.get("package_name", "").strip()
    version = data.get("version", "").strip()
    version_code = data.get("version_code", 1)
    release_notes = data.get("release_notes", "")
    app_name = data.get("app_name", "")
    mode = data.get("mode", "auto")  # auto, update, new

    if not apk_path:
        return JSONResponse({"error": "apk_path is required"}, status_code=400)

    pipeline._spawn_task(pipeline.deploy_to_store(
        task_id, apk_path, package_name, version, int(version_code), release_notes, app_name, mode
    ), task_id)
    return {"status": "deploying"}


@app.post("/api/deploy-apk")
async def deploy_apk_standalone(data: dict = {}):
    """Standalone APK deploy - no pipeline task needed. Uploads directly to BritStore."""
    apk_path = data.get("apk_path", "").strip()
    package_name = data.get("package_name", "").strip()
    version = data.get("version", "1.0.0").strip()
    version_code = data.get("version_code", 1)
    release_notes = data.get("release_notes", "")
    app_name = data.get("app_name", "").strip()
    mode = data.get("mode", "auto")
    short_description = data.get("short_description", "").strip()
    full_description = data.get("full_description", "").strip()
    category = data.get("category", "").strip()
    price_type = data.get("price_type", "free").strip()
    published = data.get("published", True)
    featured = data.get("featured", False)

    if not apk_path:
        return JSONResponse({"error": "apk_path is required"}, status_code=400)

    import os
    from tools.britstore.publisher import BritStoreTool
    publisher = BritStoreTool(config.britstore)

    # Pre-upload validation
    if not os.path.isfile(apk_path):
        await publisher.close()
        return JSONResponse({"error": f"APK file not found: {apk_path}"}, status_code=400)

    file_size = os.path.getsize(apk_path)
    if file_size < 1024:
        await publisher.close()
        return JSONResponse({"error": f"APK file too small ({file_size} bytes). This doesn't look like a valid APK."}, status_code=400)

    ext = os.path.splitext(apk_path)[1].lower()
    if ext not in (".apk", ".xapk"):
        await publisher.close()
        return JSONResponse({"error": f"File must be .apk or .xapk, got '{ext}'"}, status_code=400)

    try:
        pipeline: Pipeline = app_state.get("pipeline")

        # Extract real metadata from APK using androguard
        apk_info = {}
        try:
            from androguard.core.apk import APK
            apk = APK(apk_path)
            apk_info = {
                "package_name": apk.get_package(),
                "app_name": apk.get_app_name(),
                "version_name": apk.get_androidversion_name(),
                "version_code": apk.get_androidversion_code(),
                "min_sdk": apk.get_min_sdk_version(),
                "target_sdk": apk.get_target_sdk_version(),
                "permissions": apk.get_permissions()[:10],
                "description": apk.get_summary() or apk.get_android_app_desc() or "",
            }
            print(f"[DEPLOY-APK] APK metadata: pkg={apk_info['package_name']}, name={apk_info['app_name']}, ver={apk_info['version_name']}", )
        except Exception as e:
            print(f"[DEPLOY-APK] APK parse failed (not a valid APK?): {e}", )

        # Use extracted metadata as defaults — user-provided values override
        if not package_name and apk_info.get("package_name"):
            package_name = apk_info["package_name"]
        elif not package_name:
            basename = os.path.splitext(os.path.basename(apk_path))[0]
            package_name = basename.replace(" ", ".").replace("-", ".").lower()

        if not app_name and apk_info.get("app_name"):
            app_name = apk_info["app_name"]

        if not version or version == "1.0.0":
            if apk_info.get("version_name"):
                version = apk_info["version_name"]

        if not version_code or version_code == 1:
            if apk_info.get("version_code"):
                version_code = apk_info["version_code"]

        print(f"[DEPLOY-APK] apk={apk_path}, package={package_name}, name={app_name}, mode={mode}", )

        # Check if package exists
        exists = await publisher.check_package_exists(package_name)
        print(f"[DEPLOY-APK] Package {package_name} exists={exists}", )

        if mode == "auto":
            mode = "update" if exists else "new"

        if mode == "update" and not exists:
            await publisher.close()
            return JSONResponse({"error": f"Package '{package_name}' not found in store. Use 'new' mode to create it."}, status_code=400)

        # Auto-generate metadata using LLM if not provided
        needs_gen = mode == "new" and not (short_description and full_description and category and release_notes)
        if needs_gen:
            print(f"[DEPLOY-APK] Auto-generating metadata via LLM...", )
            try:
                from pipeline.engine import _extract_field
                apk_perms = ", ".join(apk_info.get("permissions", [])[:5])
                apk_desc = apk_info.get("description", "")
                gen_prompt = f"""Generate a brief store listing for an Android app based on its REAL metadata.

Package name: {package_name}
App name: {app_name or package_name.split(".")[-1].title()}
Version: {version}
Min Android: {apk_info.get("min_sdk", "unknown")}
Permissions: {apk_perms or "none detected"}
APK description (if any): {apk_desc or "not available"}

Based on the REAL info above, generate ONLY:
1. Short Description (max 80 chars, based on what this app actually does)
2. Full Description (2-3 paragraphs, professional, based on real permissions and metadata)
3. Release Notes (for this initial version)
4. Category (choose ONE from: AI Tools, Business, Education, Automation, Productivity, Utilities)

DO NOT change the app name or package name. Use them exactly as provided above.
DO NOT invent features that aren't supported by the permissions list.

Output format:
SHORT_DESCRIPTION: [text]
FULL_DESCRIPTION: [text]
RELEASE_NOTES: [text]
CATEGORY: [category]"""

                if hasattr(pipeline, 'hermes') and pipeline.hermes:
                    gen_result = await pipeline.hermes.chat_with_agent(
                        agent_id="deployment-engineer",
                        message=gen_prompt,
                        context={"project_name": package_name},
                    )
                    if gen_result.get("status") == "success":
                        response_text = gen_result.get("response", "")
                        print(f"[DEPLOY-APK] LLM generated metadata", )
                        # Only fill in EMPTY fields — never override user-provided values
                        if not short_description:
                            short_description = _extract_field(response_text, "SHORT_DESCRIPTION") or ""
                        if not full_description:
                            full_description = _extract_field(response_text, "FULL_DESCRIPTION") or ""
                        if not release_notes:
                            release_notes = _extract_field(response_text, "RELEASE_NOTES") or ""
                        if not category:
                            category = _extract_field(response_text, "CATEGORY") or ""
                    else:
                        print(f"[DEPLOY-APK] LLM failed: {gen_result.get('error', 'unknown')}", )
            except Exception as gen_err:
                print(f"[DEPLOY-APK] LLM generation failed: {gen_err}", )

        # Upload
        result = await publisher.publish_app(
            apk_path=apk_path,
            package_name=package_name,
            version=version,
            version_code=int(version_code),
            release_notes=release_notes or f"Version {version}",
            app_name=app_name or package_name.split(".")[-1].title(),
            short_description=short_description,
            full_description=full_description,
            category=category,
            price_type=price_type,
            published=published,
            featured=featured,
        )

        print(f"[DEPLOY-APK] Result: {result}", )
        await publisher.close()

        if result.get("success"):
            next_steps = ""
            if mode == "new":
                next_steps = (
                    f"\n\nNEXT STEPS: App '{package_name}' created in store.\n"
                    f"1. Go to https://store.britsyncai.com/dashboard/apps/ to add icon and screenshots\n"
                    f"2. Review and publish the listing"
                )
            return {
                "success": True,
                "message": result.get("message", "Uploaded successfully") + next_steps,
                "package_name": package_name,
                "version": version,
                "mode": mode,
            }
        else:
            return JSONResponse({"error": result.get("error", "Upload failed")}, status_code=500)

    except Exception as e:
        print(f"[DEPLOY-APK] Error: {e}", )
        try:
            await publisher.close()
        except Exception:
            pass
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/store/check-package/{package_name}")
async def check_store_package(package_name: str):
    """Check if a package name exists in the BritStore."""
    from tools.britstore.publisher import BritStoreTool
    publisher = BritStoreTool(config.britstore)
    try:
        exists = await publisher.check_package_exists(package_name)
        update_info = {}
        if exists:
            update_info = await publisher.check_update(package_name)
        await publisher.close()
        return {"exists": exists, "update_info": update_info}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/browse-apk")
async def browse_apk_files(directory: str = ""):
    """List APK files in a directory. Returns files and current path."""
    import os
    if not directory:
        directory = os.path.expanduser("~") + "\\Downloads"
    directory = os.path.normpath(directory)

    if not os.path.isdir(directory):
        return JSONResponse({"error": f"Directory not found: {directory}"}, status_code=400)

    apk_files = []
    parent = os.path.dirname(directory)
    try:
        for entry in os.scandir(directory):
            if entry.name.lower().endswith(".apk") and entry.is_file():
                stat = entry.stat()
                apk_files.append({
                    "name": entry.name,
                    "path": entry.path,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            elif entry.is_dir() and not entry.name.startswith("."):
                apk_files.append({
                    "name": entry.name + "/",
                    "path": entry.path,
                    "is_dir": True,
                })
    except PermissionError:
        return JSONResponse({"error": f"Permission denied: {directory}"}, status_code=403)

    apk_files.sort(key=lambda x: (not x.get("is_dir", False), x["name"]))
    return {"directory": directory, "parent": parent, "files": apk_files}


@app.post("/api/store/upload-media")
async def upload_store_media(
    package_name: str = Form(""),
    short_description: str = Form(""),
    full_description: str = Form(""),
    icon: Optional[UploadFile] = None,
    mobile_screenshots: list[UploadFile] = File(default=[]),
    tablet_screenshots: list[UploadFile] = File(default=[]),
):
    """Upload icon + screenshots to BritStore for an existing app."""
    if not package_name:
        return JSONResponse({"error": "package_name is required"}, status_code=400)

    import httpx
    from shared.config import config

    store_url = config.britstore.api_url
    api_key = config.britstore.api_key

    try:
        form_data = {"package_name": package_name}
        if short_description:
            form_data["short_description"] = short_description
        if full_description:
            form_data["full_description"] = full_description

        files = []
        temp_files = []

        if icon:
            icon_bytes = await icon.read()
            if icon_bytes:
                files.append(("icon", (icon.filename or "icon.png", icon_bytes, icon.content_type or "image/png")))

        for ss in mobile_screenshots:
            ss_bytes = await ss.read()
            if ss_bytes:
                files.append(("mobile_screenshots", (ss.filename or "screenshot.png", ss_bytes, ss.content_type or "image/png")))

        for ss in tablet_screenshots:
            ss_bytes = await ss.read()
            if ss_bytes:
                files.append(("tablet_screenshots", (ss.filename or "screenshot.png", ss_bytes, ss.content_type or "image/png")))

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{store_url}/api/update-app-media/",
                headers={"Authorization": f"Bearer {api_key}"},
                data=form_data,
                files=files,
            )

        if resp.status_code in (200, 201):
            return resp.json()
        else:
            return JSONResponse({"error": f"Store returned {resp.status_code}: {resp.text[:500]}"}, status_code=resp.status_code)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/notifications")
async def get_notifications(user_id: str = ""):
    """Get notifications for a user."""
    pipeline: Pipeline = app_state["pipeline"]
    is_admin = False
    if user_id:
        memory = app_state.get("memory")
        if memory:
            u = await memory.get_user_by_id(user_id)
            if u:
                is_admin = u.get("is_admin", False)
    return {"notifications": pipeline.get_notifications(user_id=user_id, is_admin=is_admin)}


@app.get("/api/notifications/unread")
async def get_unread_notifications(user_id: str = ""):
    """Get unread notifications for a user."""
    pipeline: Pipeline = app_state["pipeline"]
    is_admin = False
    if user_id:
        memory = app_state.get("memory")
        if memory:
            u = await memory.get_user_by_id(user_id)
            if u:
                is_admin = u.get("is_admin", False)
    return {"notifications": pipeline.get_notifications(unread_only=True, user_id=user_id, is_admin=is_admin)}


@app.post("/api/notifications/{index}/read")
async def mark_notification_read(index: int):
    """Mark a notification as read."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline.mark_notification_read(index)
    return {"status": "ok"}


@app.delete("/api/notifications")
async def clear_notifications():
    """Clear all notifications."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline.clear_notifications()
    return {"status": "cleared"}


@app.delete("/api/notifications/task/{task_id}")
async def clear_notifications_for_task(task_id: str):
    """Clear notifications for a specific task."""
    pipeline: Pipeline = app_state["pipeline"]
    pipeline.clear_notifications_for_task(task_id)
    return {"status": "cleared"}


@app.post("/api/projects/{project_id}/set-folder")
async def set_project_folder(project_id: str, data: dict):
    """Set the folder for a project."""
    hermes: HermesOrchestrator = app_state["hermes"]
    pipeline: Pipeline = app_state["pipeline"]

    project = hermes.projects.get(project_id)
    if not project:
        return {"error": "Project not found"}

    project.folder = data.get("folder", "")

    _persist_both(hermes, pipeline)

    return {
        "status": "ok",
        "folder": project.folder,
    }


@app.post("/api/projects/{project_id}/set-mode")
async def set_project_mode(project_id: str, data: dict):
    """Set the mode for a project (scratch or prebuilt)."""
    hermes: HermesOrchestrator = app_state["hermes"]
    pipeline: Pipeline = app_state["pipeline"]

    project = hermes.projects.get(project_id)
    if not project:
        return {"error": "Project not found"}

    project.mode = data.get("mode", "scratch")

    _persist_both(hermes, pipeline)

    return {
        "status": "ok",
        "mode": project.mode,
    }


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and all its tasks."""
    hermes: HermesOrchestrator = app_state["hermes"]
    pipeline: Pipeline = app_state["pipeline"]
    if project_id not in hermes.projects:
        return {"error": "Project not found"}
    project_tasks = [t.id for t in hermes.tasks.values() if t.project_id == project_id]
    for tid in project_tasks:
        hermes.tasks.pop(tid, None)
        pipeline.tasks.pop(tid, None)
        pipeline.notifications = [n for n in pipeline.notifications if n.get("task_id") != tid]
    del hermes.projects[project_id]
    _persist_both(hermes, pipeline)
    return {"status": "deleted"}


@app.put("/api/projects/{project_id}")
async def edit_project(project_id: str, data: dict):
    """Edit a project."""
    hermes: HermesOrchestrator = app_state["hermes"]
    pipeline: Pipeline = app_state["pipeline"]
    project = hermes.projects.get(project_id)
    if not project:
        return {"error": "Project not found"}
    if "name" in data:
        project.name = data["name"]
    if "codename" in data:
        project.codename = data["codename"]
    if "description" in data:
        project.description = data["description"]
    if "tech_stack" in data:
        project.tech_stack = data["tech_stack"]
    _persist_both(hermes, pipeline)
    return {"status": "ok"}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    try:
        hermes: HermesOrchestrator = app_state["hermes"]
        pipeline: Pipeline = app_state["pipeline"]
        try:
            pipeline.cancel_task(task_id)
        except Exception:
            pass  # Task might not exist in pipeline
        task = hermes.tasks.pop(task_id, None)
        pipeline.tasks.pop(task_id, None)
        if not task:
            return {"status": "deleted", "note": "Task not found but cleaned up"}
        if task.project_id and task.project_id in hermes.projects:
            proj = hermes.projects[task.project_id]
            if hasattr(proj, 'tasks') and task_id in proj.tasks:
                proj.tasks.remove(task_id)
        _persist_both(hermes, pipeline)
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Delete task error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.put("/api/tasks/{task_id}")
async def edit_task(task_id: str, data: dict):
    """Edit a task."""
    hermes: HermesOrchestrator = app_state["hermes"]
    task = hermes.tasks.get(task_id)
    if not task:
        return {"error": "Task not found"}
    if "title" in data:
        task.title = data["title"]
    if "description" in data:
        task.description = data["description"]
    if "priority" in data:
        from shared.models import TaskPriority
        task.priority = TaskPriority(data["priority"])
    return {"status": "ok"}


@app.post("/api/terminal/exec")
async def exec_command(data: dict):
    """Execute a terminal command."""
    import asyncio as _asyncio
    command = data.get("command", "")
    cwd = data.get("cwd", PROJECTS_DIR)

    try:
        proc = await _asyncio.create_subprocess_shell(
            command,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await _asyncio.wait_for(proc.communicate(), timeout=120)
        except _asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"error": "Command timed out after 120 seconds"}
        return {
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/agents/{agent_id}/auto-execute")
async def agent_auto_execute(agent_id: str, data: dict):
    """Chat with an agent, extract files, write them, and run commands — all in one shot."""
    import re
    import asyncio

    message = data.get("message", "")
    project_dir = data.get("project_dir", os.path.join(PROJECTS_DIR, "current"))

    hermes: HermesOrchestrator = app_state["hermes"]

    # Step 1: Get agent response with timeout
    try:
        agent_result = await asyncio.wait_for(
            hermes.chat_with_agent(
                agent_id=agent_id,
                message=message,
                context={"project_directory": project_dir},
            ),
            timeout=300,
        )
    except asyncio.TimeoutError:
        return {"status": "error", "error": "Agent took too long (300s timeout). The model may be overloaded. Try again."}

    if agent_result.get("status") != "success":
        return {"status": "error", "error": agent_result.get("error", "Agent failed")}

    response_text = agent_result["response"]

    # Step 2: Extract files from response
    files_written = []
    errors = []

    # Match: optional ### + filename + optional whitespace + ```lang\n code\n ```
    file_pattern = r'(?:###\s*|\n)([^\n]+\.(?:tsx?|ts|py|css|html|json|yaml|yml|sql|dart|sh|env|toml|cfg|js|jsx))\s*\n\s*```\w*\s*\n(.*?)```'
    matches = re.findall(file_pattern, response_text, re.DOTALL)

    for filename, content in matches:
        filename = filename.strip().lstrip("/").lstrip("\\")
        filepath = os.path.join(project_dir, filename)

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content.strip())
            files_written.append({"path": filename, "size": len(content.strip())})
            logger.info(f"Auto-written: {filepath}")
        except Exception as e:
            errors.append({"path": filename, "error": str(e)})

    logger.info(f"Auto-extract: found {len(matches)} files, {len(files_written)} written")

    # Step 3: Extract and run commands
    commands_run = []
    cmd_pattern = r'```(?:bash|sh|shell|terminal|cmd)\n(.*?)```'
    cmd_matches = re.findall(cmd_pattern, response_text, re.DOTALL)

    for cmd_block in cmd_matches:
        for line in cmd_block.strip().split("\n"):
            cmd = line.strip()
            if not cmd or cmd.startswith("#"):
                continue

            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=project_dir,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.communicate()
                    commands_run.append({"command": cmd, "error": "Timed out"})
                    continue
                commands_run.append({
                    "command": cmd,
                    "stdout": stdout.decode(errors="replace")[:2000],
                    "stderr": stderr.decode(errors="replace")[:2000],
                    "returncode": proc.returncode,
                })
            except Exception as e:
                commands_run.append({"command": cmd, "error": str(e)})

    return {
        "status": "success",
        "response": response_text,
        "files_written": files_written,
        "commands_run": commands_run,
        "errors": errors,
        "project_dir": project_dir,
    }


# --- Layer 2: Executive Product Board ---

def _board() -> "ExecutiveProductBoard":
    b = app_state.get("board")
    if b is None:
        raise RuntimeError("Executive Product Board is not initialized")
    return b


@app.get("/api/board/members")
async def board_members():
    """List the nine executive board members."""
    try:
        return {"members": _board().members()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/board/stats")
async def board_stats():
    """Executive Product Board statistics."""
    try:
        return _board().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/board/reviews")
async def board_list_reviews():
    """List all board reviews."""
    try:
        return {"reviews": _board().list_reviews()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/board/reviews")
async def board_submit_review(data: dict):
    """Submit a product request for board review. Runs in the background.

    wait=true blocks until the review finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    board = _board()
    if data.get("wait"):
        result = await board.run_review_sync(
            request=request,
            project_id=data.get("project_id"),
        )
        return {"status": "completed", "review": result}
    result = await board.run_review(request=request, project_id=data.get("project_id"))
    return result


@app.get("/api/board/reviews/{review_id}")
async def board_get_review(review_id: str):
    """Get a single board review."""
    review = _board().get_review_dict(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {"review": review}


@app.get("/api/board/reviews/{review_id}/export")
async def board_export_review(review_id: str):
    """Export the review's decision package as markdown."""
    board = _board()
    review = board.get_review(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {
        "decision_markdown": review.decision_markdown or "",
        "decision": review.decision,
        "request": review.request,
        "total_score": review.total_score,
        "final_verdict": review.final_verdict,
    }


@app.post("/api/board/reviews/{review_id}/cancel")
async def board_cancel_review(review_id: str):
    """Cancel a running review."""
    board = _board()
    task = board._running.get(review_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Review is not running"}, status_code=400)


@app.delete("/api/board/reviews/{review_id}")
async def board_delete_review(review_id: str):
    """Delete a review."""
    board = _board()
    if not board.delete_review(review_id):
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/board/reviews/{review_id}/create-project")
async def board_create_project(review_id: str):
    """Send an approved decision package to the development agents: creates a
    Hermes project with the Decision Package attached and one task per
    approved feature."""
    board = _board()
    hermes: HermesOrchestrator = app_state["hermes"]
    package = board.build_development_package(review_id)
    if not package:
        return JSONResponse({"error": "Review not found"}, status_code=404)

    review = board.get_review(review_id)
    dec = package["decision_package"]
    description = (
        package["description"]
        or dec.get("business_goal")
        or (review.request[:200] if review else package["project_name"])
    )
    project = await hermes.create_project(
        name=package["project_name"],
        codename=package["codename"],
        description=description,
        tech_stack=package["tech_stack"],
    )
    project.metadata["board_review_id"] = review_id
    project.metadata["decision_package"] = dec
    project.metadata["decision_markdown"] = package["decision_markdown"]

    from shared.models import TaskPriority
    features = dec.get("approved_features") or []
    if not features:
        features = [f.strip("- ") for f in (review.decision_markdown or "").splitlines() if f.strip().startswith("- ")][:6]

    tasks_created = 0
    for i, feature in enumerate(features):
        await hermes.create_task(
            title=feature if len(feature) <= 90 else feature[:87] + "...",
            description=(
                f"Approved by the Executive Product Board (review {review_id}).\n\n"
                f"Feature: {feature}\n\n"
                f"{package['decision_markdown'][:4000]}"
            ),
            project_id=project.id,
            priority=TaskPriority.HIGH if i == 0 else TaskPriority.MEDIUM,
            metadata={"source": "executive_product_board", "board_review_id": review_id},
        )
        tasks_created += 1

    _persist_both(hermes, app_state["pipeline"])
    if review:
        review.project_id = project.id
        board.persist()

    return {
        "status": "created",
        "project_id": project.id,
        "project_name": project.name,
        "codename": project.codename,
        "tasks_created": tasks_created,
        "decision_markdown": package["decision_markdown"],
    }


# --- Layer 3: Product Research & Discovery Division (PRDD) ---

def _research() -> "ResearchDivision":
    r = app_state.get("research")
    if r is None:
        raise RuntimeError("Product Research & Discovery Division is not initialized")
    return r


@app.get("/api/research/departments")
async def research_departments():
    """List the ten research departments."""
    try:
        return {"departments": _research().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/research/stats")
async def research_stats():
    """Product Research & Discovery Division statistics."""
    try:
        return _research().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/research/dossiers")
async def research_list_dossiers():
    """List all research dossiers."""
    try:
        return {"dossiers": _research().list_dossiers()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/research/dossiers")
async def research_submit(data: dict):
    """Submit a subject for product research. Runs in the background.

    wait=true blocks until the research finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "new_product")
    research = _research()
    if subject_type not in research.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {research.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await research.run_research_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "dossier": result}
    result = await research.run_research(request=request, subject_type=subject_type)
    return result


@app.get("/api/research/dossiers/{dossier_id}")
async def research_get_dossier(dossier_id: str):
    """Get a single research dossier."""
    dossier = _research().get_dossier_dict(dossier_id)
    if not dossier:
        return JSONResponse({"error": "Dossier not found"}, status_code=404)
    return {"dossier": dossier}


@app.get("/api/research/dossiers/{dossier_id}/export")
async def research_export_dossier(dossier_id: str):
    """Export a research dossier as markdown."""
    research = _research()
    dossier = research.get_dossier(dossier_id)
    if not dossier:
        return JSONResponse({"error": "Dossier not found"}, status_code=404)
    return {
        "dossier_markdown": dossier.dossier_markdown or "",
        "request": dossier.request,
        "subject_type": dossier.subject_type,
        "avg_confidence": dossier.avg_confidence,
        "total_recommendations": dossier.total_recommendations,
    }


@app.post("/api/research/dossiers/{dossier_id}/cancel")
async def research_cancel_dossier(dossier_id: str):
    """Cancel a running research task."""
    research = _research()
    task = research._running.get(dossier_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Research is not running"}, status_code=400)


@app.delete("/api/research/dossiers/{dossier_id}")
async def research_delete_dossier(dossier_id: str):
    """Delete a research dossier."""
    research = _research()
    if not research.delete_dossier(dossier_id):
        return JSONResponse({"error": "Dossier not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/research/dossiers/{dossier_id}/to-board")
async def research_send_to_board(dossier_id: str):
    """Send a completed dossier to the Executive Product Board for review.

    The board runs a full review using the research subject plus the dossier
    summary as context - the 'Executive Product Board requests research
    before approving major product work' flow.
    """
    research = _research()
    dossier = research.get_dossier(dossier_id)
    if not dossier:
        return JSONResponse({"error": "Dossier not found"}, status_code=404)
    if dossier.status != "completed":
        return JSONResponse({"error": "Dossier is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = research.board_request_text(dossier)
    if app_state.get("research_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    dossier.board_review_id = result.get("review_id") or result.get("id")
    research.persist()
    return {
        "status": "sent",
        "board_review_id": dossier.board_review_id,
        "board_review": result,
    }


# --- Layer 4: UX & Human Experience Division (UXHED) ---

def _ux() -> "UXDivision":
    u = app_state.get("ux")
    if u is None:
        raise RuntimeError("UX & Human Experience Division is not initialized")
    return u


@app.get("/api/ux/departments")
async def ux_departments():
    """List the eleven UX departments."""
    try:
        return {"departments": _ux().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ux/stats")
async def ux_stats():
    """UX & Human Experience Division statistics."""
    try:
        return _ux().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ux/reviews")
async def ux_list_reviews():
    """List all UX reviews."""
    try:
        return {"reviews": _ux().list_reviews()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ux/reviews")
async def ux_submit(data: dict):
    """Submit a surface for a UX review. Runs in the background.

    wait=true blocks until the review finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "whole_product")
    ux = _ux()
    if subject_type not in ux.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {ux.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await ux.run_review_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "review": result}
    result = await ux.run_review(request=request, subject_type=subject_type)
    return result


@app.get("/api/ux/reviews/{review_id}")
async def ux_get_review(review_id: str):
    """Get a single UX review."""
    review = _ux().get_review_dict(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {"review": review}


@app.get("/api/ux/reviews/{review_id}/export")
async def ux_export_review(review_id: str):
    """Export a UX review as markdown."""
    ux = _ux()
    review = ux.get_review(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {
        "review_markdown": review.review_markdown or "",
        "request": review.request,
        "subject_type": review.subject_type,
        "overall_score": review.overall_score,
        "avg_confidence": review.avg_confidence,
        "total_recommendations": review.total_recommendations,
    }


@app.post("/api/ux/reviews/{review_id}/cancel")
async def ux_cancel_review(review_id: str):
    """Cancel a running UX review task."""
    ux = _ux()
    task = ux._running.get(review_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Review is not running"}, status_code=400)


@app.delete("/api/ux/reviews/{review_id}")
async def ux_delete_review(review_id: str):
    """Delete a UX review."""
    ux = _ux()
    if not ux.delete_review(review_id):
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/ux/reviews/{review_id}/to-board")
async def ux_send_to_board(review_id: str):
    """Send a completed UX review to the Executive Product Board for review.

    The board runs a full review using the surface subject plus the UX Review
    Report as context - the 'UX Division delivers its report before the board
    approves implementation' flow.
    """
    ux = _ux()
    review = ux.get_review(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    if review.status != "completed":
        return JSONResponse({"error": "Review is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = ux.board_request_text(review)
    if app_state.get("ux_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    review.board_review_id = result.get("review_id") or result.get("id")
    ux.persist()
    return {
        "status": "sent",
        "board_review_id": review.board_review_id,
        "board_review": result,
    }


# --- Layer 5: Visual Design & Design System Division (VDDS) ---

def _design() -> "DesignDivision":
    d = app_state.get("design")
    if d is None:
        raise RuntimeError("Visual Design & Design System Division is not initialized")
    return d


@app.get("/api/design/departments")
async def design_departments():
    """List the twelve design departments."""
    try:
        return {"departments": _design().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/design/stats")
async def design_stats():
    """Visual Design & Design System Division statistics."""
    try:
        return _design().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/design/packages")
async def design_list_packages():
    """List all Visual Design Packages."""
    try:
        return {"packages": _design().list_packages()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/design/packages")
async def design_submit(data: dict):
    """Submit a design subject for a Visual Design Package. Runs in the background.

    wait=true blocks until the design finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "screen")
    design = _design()
    if subject_type not in design.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {design.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await design.run_design_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "package": result}
    result = await design.run_design(request=request, subject_type=subject_type)
    return result


@app.get("/api/design/packages/{package_id}")
async def design_get_package(package_id: str):
    """Get a single Visual Design Package."""
    package = _design().get_package_dict(package_id)
    if not package:
        return JSONResponse({"error": "Package not found"}, status_code=404)
    return {"package": package}


@app.get("/api/design/packages/{package_id}/export")
async def design_export_package(package_id: str):
    """Export a Visual Design Package as markdown."""
    design = _design()
    package = design.get_package(package_id)
    if not package:
        return JSONResponse({"error": "Package not found"}, status_code=404)
    return {
        "package_markdown": package.package_markdown or "",
        "request": package.request,
        "subject_type": package.subject_type,
        "visual_quality_score": package.visual_quality_score,
        "avg_confidence": package.avg_confidence,
        "total_components": package.total_components,
        "total_tokens": package.total_tokens,
    }


@app.post("/api/design/packages/{package_id}/cancel")
async def design_cancel_package(package_id: str):
    """Cancel a running Visual Design Package task."""
    design = _design()
    task = design._running.get(package_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Design is not running"}, status_code=400)


@app.delete("/api/design/packages/{package_id}")
async def design_delete_package(package_id: str):
    """Delete a Visual Design Package."""
    design = _design()
    if not design.delete_package(package_id):
        return JSONResponse({"error": "Package not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/design/packages/{package_id}/to-board")
async def design_send_to_board(package_id: str):
    """Send a completed Visual Design Package to the Executive Product Board for review.

    The board runs a full review using the design subject plus the package
    summary as context - the 'Visual Design Division delivers its package
    before the board approves implementation' flow.
    """
    design = _design()
    package = design.get_package(package_id)
    if not package:
        return JSONResponse({"error": "Package not found"}, status_code=404)
    if package.status != "completed":
        return JSONResponse({"error": "Package is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = design.board_request_text(package)
    if app_state.get("design_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    package.board_review_id = result.get("review_id") or result.get("id")
    design.persist()
    return {
        "status": "sent",
        "board_review_id": package.board_review_id,
        "board_review": result,
    }


# --- Layer 6: Growth, Conversion & Customer Success Division (GCCSD) ---

def _growth() -> "GrowthDivision":
    g = app_state.get("growth")
    if g is None:
        raise RuntimeError("Growth, Conversion & Customer Success Division is not initialized")
    return g


@app.get("/api/growth/departments")
async def growth_departments():
    """List the twelve growth departments."""
    try:
        return {"departments": _growth().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/growth/stats")
async def growth_stats():
    """Growth, Conversion & Customer Success Division statistics."""
    try:
        return _growth().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/growth/reviews")
async def growth_list_reviews():
    """List all Growth Intelligence Reports."""
    try:
        return {"reviews": _growth().list_reviews()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/growth/reviews")
async def growth_submit(data: dict):
    """Submit a growth subject for a Growth Intelligence Report. Runs in the
    background.

    wait=true blocks until the review finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "landing_page")
    growth = _growth()
    if subject_type not in growth.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {growth.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await growth.run_review_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "review": result}
    result = await growth.run_review(request=request, subject_type=subject_type)
    return result


@app.get("/api/growth/reviews/{review_id}")
async def growth_get_review(review_id: str):
    """Get a single Growth Intelligence Report."""
    review = _growth().get_review_dict(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {"review": review}


@app.get("/api/growth/reviews/{review_id}/export")
async def growth_export_review(review_id: str):
    """Export a Growth Intelligence Report as markdown."""
    growth = _growth()
    review = growth.get_review(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {
        "review_markdown": review.package_markdown or "",
        "request": review.request,
        "subject_type": review.subject_type,
        "growth_score": review.growth_score,
        "avg_confidence": review.avg_confidence,
        "total_opportunities": review.total_opportunities,
        "total_metrics": review.total_metrics,
    }


@app.post("/api/growth/reviews/{review_id}/cancel")
async def growth_cancel_review(review_id: str):
    """Cancel a running growth review task."""
    growth = _growth()
    task = growth._running.get(review_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Review is not running"}, status_code=400)


@app.delete("/api/growth/reviews/{review_id}")
async def growth_delete_review(review_id: str):
    """Delete a Growth Intelligence Report."""
    growth = _growth()
    if not growth.delete_review(review_id):
        return JSONResponse({"error": "Review not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/growth/reviews/{review_id}/to-board")
async def growth_send_to_board(review_id: str):
    """Send a completed Growth Intelligence Report to the Executive Product Board
    for review.

    The board runs a full review using the growth subject plus the report
    summary as context - the 'Growth Division delivers its report before the
    board approves implementation' flow.
    """
    growth = _growth()
    review = growth.get_review(review_id)
    if not review:
        return JSONResponse({"error": "Review not found"}, status_code=404)
    if review.status != "completed":
        return JSONResponse({"error": "Review is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = growth.board_request_text(review)
    if app_state.get("growth_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    review.board_review_id = result.get("review_id") or result.get("id")
    growth.persist()
    return {
        "status": "sent",
        "board_review_id": review.board_review_id,
        "board_review": result,
    }


# --- Layer 7: Quality, Security & Release Excellence Division (QSRED) ---

def _quality() -> "QualityDivision":
    q = app_state.get("quality")
    if q is None:
        raise RuntimeError("Quality, Security & Release Excellence Division is not initialized")
    return q


@app.get("/api/quality/departments")
async def quality_departments():
    """List the thirteen quality departments."""
    try:
        return {"departments": _quality().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/quality/stats")
async def quality_stats():
    """Quality, Security & Release Excellence Division statistics."""
    try:
        return _quality().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/quality/reports")
async def quality_list_reports():
    """List all Release Excellence Reports."""
    try:
        return {"reports": _quality().list_reports()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/quality/reports")
async def quality_submit(data: dict):
    """Submit a release subject for a Release Excellence Report. Runs in the
    background.

    wait=true blocks until the review finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "release")
    quality = _quality()
    if subject_type not in quality.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {quality.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await quality.run_review_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "report": result}
    result = await quality.run_review(request=request, subject_type=subject_type)
    return result


@app.get("/api/quality/reports/{report_id}")
async def quality_get_report(report_id: str):
    """Get a single Release Excellence Report."""
    report = _quality().get_report_dict(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"report": report}


@app.get("/api/quality/reports/{report_id}/export")
async def quality_export_report(report_id: str):
    """Export a Release Excellence Report as markdown."""
    quality = _quality()
    report = quality.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {
        "report_markdown": report.report_markdown or "",
        "request": report.request,
        "subject_type": report.subject_type,
        "quality_score": report.quality_score,
        "release_version": report.release_version,
        "final_decision": report.final_decision,
        "avg_confidence": report.avg_confidence,
        "total_checks": report.total_checks,
        "total_findings": report.total_findings,
    }


@app.post("/api/quality/reports/{report_id}/cancel")
async def quality_cancel_report(report_id: str):
    """Cancel a running release review task."""
    quality = _quality()
    task = quality._running.get(report_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Review is not running"}, status_code=400)


@app.delete("/api/quality/reports/{report_id}")
async def quality_delete_report(report_id: str):
    """Delete a Release Excellence Report."""
    quality = _quality()
    if not quality.delete_report(report_id):
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/quality/reports/{report_id}/to-board")
async def quality_send_to_board(report_id: str):
    """Send a completed Release Excellence Report to the Executive Product Board
    for review.

    The board runs a full review using the release subject plus the report
    summary as context - the 'QSRED is the final gate before production' flow.
    """
    quality = _quality()
    report = quality.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    if report.status != "completed":
        return JSONResponse({"error": "Report is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = quality.board_request_text(report)
    if app_state.get("quality_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    report.board_review_id = result.get("review_id") or result.get("id")
    quality.persist()
    return {
        "status": "sent",
        "board_review_id": report.board_review_id,
        "board_review": result,
    }


# --- Layer 1: Foundation Knowledge Base (Product Knowledge Base) ---

def _kb() -> "KnowledgeStore":
    store = app_state.get("kb")
    if store is None:
        raise RuntimeError("Knowledge Base is not initialized")
    return store


@app.get("/api/kb/repositories")
async def kb_list_repositories():
    """List all Layer 1 repositories with counts."""
    try:
        store = _kb()
        return {"repositories": store.list_repositories(), "stats": store.stats()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/kb/stats")
async def kb_stats():
    """Knowledge base statistics."""
    try:
        return _kb().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/kb/repositories/{repo_id}")
async def kb_get_repository(repo_id: str):
    """Get a full repository (categories + items)."""
    store = _kb()
    repo = store.get_repository_dict(repo_id)
    if not repo:
        return JSONResponse({"error": f"Repository '{repo_id}' not found"}, status_code=404)
    return {"repository": repo}


@app.post("/api/kb/repositories/{repo_id}/categories")
async def kb_add_category(repo_id: str, data: dict):
    """Add a category to a repository."""
    store = _kb()
    cat = store.add_category(repo_id, data)
    if cat is None:
        return JSONResponse({"error": f"Repository '{repo_id}' not found"}, status_code=404)
    return {"category": cat}


@app.put("/api/kb/repositories/{repo_id}/categories/{category_id}")
async def kb_update_category(repo_id: str, category_id: str, data: dict):
    """Update a category."""
    store = _kb()
    cat = store.update_category(repo_id, category_id, data)
    if cat is None:
        return JSONResponse({"error": "Category or repository not found"}, status_code=404)
    return {"category": cat}


@app.delete("/api/kb/repositories/{repo_id}/categories/{category_id}")
async def kb_delete_category(repo_id: str, category_id: str):
    """Delete a category and its items."""
    store = _kb()
    if not store.delete_category(repo_id, category_id):
        return JSONResponse({"error": "Category or repository not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/kb/repositories/{repo_id}/categories/{category_id}/items")
async def kb_add_item(repo_id: str, category_id: str, data: dict):
    """Add an item (standard/rule/entry) to a category."""
    store = _kb()
    item = store.add_item(repo_id, category_id, data)
    if item is None:
        return JSONResponse({"error": "Repository or category not found"}, status_code=404)
    return {"item": item}


@app.put("/api/kb/repositories/{repo_id}/items/{item_id}")
async def kb_update_item(repo_id: str, item_id: str, data: dict):
    """Update an item."""
    store = _kb()
    item = store.update_item(repo_id, item_id, data)
    if item is None:
        return JSONResponse({"error": "Item not found"}, status_code=404)
    return {"item": item}


@app.delete("/api/kb/repositories/{repo_id}/items/{item_id}")
async def kb_delete_item(repo_id: str, item_id: str):
    """Delete an item."""
    store = _kb()
    if not store.delete_item(repo_id, item_id):
        return JSONResponse({"error": "Item not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/kb/repositories/{repo_id}/reset")
async def kb_reset_repository(repo_id: str):
    """Reset a repository to its factory seed content."""
    store = _kb()
    if not store.reset_repository(repo_id):
        return JSONResponse({"error": f"Repository '{repo_id}' not found or no seed available"}, status_code=404)
    return {"status": "reset", "repository": store.get_repository_dict(repo_id)}


@app.get("/api/kb/search")
async def kb_search(q: str = "", repos: str = ""):
    """Search across repositories. repos = comma-separated repo ids (optional)."""
    store = _kb()
    repo_ids = [r.strip() for r in repos.split(",") if r.strip()] or None
    results = store.search(q, repo_ids=repo_ids)
    return {"query": q, "results": results, "count": len(results)}


@app.post("/api/kb/search")
async def kb_search_post(data: dict):
    """Search across repositories (POST variant)."""
    store = _kb()
    results = store.search(
        data.get("q", ""),
        repo_ids=data.get("repos"),
        limit_per_repo=data.get("limit_per_repo", 5),
        max_total=data.get("max_total", 25),
    )
    return {"query": data.get("q", ""), "results": results, "count": len(results)}


@app.get("/api/kb/agent-briefing")
async def kb_agent_briefing(task: str = ""):
    """Layer 1 briefing for an agent task: the standards most relevant to the task."""
    store = _kb()
    brief = store.briefing(task)
    return brief


@app.post("/api/kb/agent-briefing")
async def kb_agent_briefing_post(data: dict):
    """Layer 1 briefing for an agent task (POST variant)."""
    store = _kb()
    return store.briefing(data.get("task", ""), max_items=data.get("max_items", 12))


@app.get("/api/kb/agent-briefing/markdown")
async def kb_agent_briefing_markdown(task: str = ""):
    """Layer 1 briefing as ready-to-inject markdown for an LLM prompt."""
    store = _kb()
    return {"markdown": store.briefing_markdown(task)}


# --- Layer 8: Intelligence, Learning & Continuous Improvement Division (ILCID) ---

def _intelligence() -> "IntelligenceDivision":
    d = app_state.get("intelligence")
    if d is None:
        raise RuntimeError("Intelligence, Learning & Continuous Improvement Division is not initialized")
    return d


@app.get("/api/intelligence/departments")
async def intelligence_departments():
    """List the twelve intelligence departments (Intelligence Director last)."""
    try:
        return {"departments": _intelligence().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/intelligence/stats")
async def intelligence_stats():
    """Intelligence, Learning & Continuous Improvement Division statistics."""
    try:
        return _intelligence().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/intelligence/reports")
async def intelligence_list_reports():
    """List all Project Intelligence Reports."""
    try:
        return {"reports": _intelligence().list_reports()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/intelligence/reports")
async def intelligence_submit(data: dict):
    """Submit a learning subject for a Project Intelligence Report. Runs in the
    background.

    wait=true blocks until the report finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "project")
    intelligence = _intelligence()
    if subject_type not in intelligence.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {intelligence.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await intelligence.run_review_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "report": result}
    result = await intelligence.run_review(request=request, subject_type=subject_type)
    return result


@app.get("/api/intelligence/reports/{report_id}")
async def intelligence_get_report(report_id: str):
    """Get a single Project Intelligence Report."""
    report = _intelligence().get_report_dict(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"report": report}


@app.get("/api/intelligence/reports/{report_id}/export")
async def intelligence_export_report(report_id: str):
    """Export a Project Intelligence Report as markdown."""
    intelligence = _intelligence()
    report = intelligence.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {
        "report_markdown": report.report_markdown or "",
        "request": report.request,
        "subject_type": report.subject_type,
        "intelligence_score": report.intelligence_score,
        "avg_confidence": report.avg_confidence,
        "total_lessons": report.total_lessons,
        "total_recommendations": report.total_recommendations,
        "total_standards": report.total_standards,
        "knowledge_graph": report.knowledge_graph,
    }


@app.post("/api/intelligence/reports/{report_id}/cancel")
async def intelligence_cancel_report(report_id: str):
    """Cancel a running intelligence review task."""
    intelligence = _intelligence()
    task = intelligence._running.get(report_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Review is not running"}, status_code=400)


@app.delete("/api/intelligence/reports/{report_id}")
async def intelligence_delete_report(report_id: str):
    """Delete a Project Intelligence Report."""
    intelligence = _intelligence()
    if not intelligence.delete_report(report_id):
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/intelligence/reports/{report_id}/to-board")
async def intelligence_send_to_board(report_id: str):
    """Send a completed Project Intelligence Report to the Executive Product
    Board for review.

    The board runs a full review using the learning subject plus the report
    summary as context - the 'ILCID is the organizational memory' flow.
    """
    intelligence = _intelligence()
    report = intelligence.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    if report.status != "completed":
        return JSONResponse({"error": "Report is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = intelligence.board_request_text(report)
    if app_state.get("intelligence_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    report.board_review_id = result.get("review_id") or result.get("id")
    intelligence.persist()
    return {
        "status": "sent",
        "board_review_id": report.board_review_id,
        "board_review": result,
    }


# --- Layer 9: Enterprise AI Governance & Orchestration Division (EAGOD) ---

def _governance() -> "GovernanceDivision":
    d = app_state.get("governance")
    if d is None:
        raise RuntimeError("Enterprise AI Governance & Orchestration Division is not initialized")
    return d


@app.get("/api/governance/departments")
async def governance_departments():
    """List the thirteen operations departments (Chief AI Operations Director last)."""
    try:
        return {"departments": _governance().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/governance/stats")
async def governance_stats():
    """Enterprise AI Governance & Orchestration Division statistics + executive dashboard."""
    try:
        return _governance().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/governance/reports")
async def governance_list_reports():
    """List all Division Operations Reports."""
    try:
        return {"reports": _governance().list_reports()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/governance/reports")
async def governance_submit(data: dict):
    """Submit an enterprise operation for a Division Operations Report. Runs in
    the background.

    wait=true blocks until the report finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "operation")
    governance = _governance()
    if subject_type not in governance.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {governance.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await governance.run_review_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "report": result}
    result = await governance.run_review(request=request, subject_type=subject_type)
    return result


@app.get("/api/governance/reports/{report_id}")
async def governance_get_report(report_id: str):
    """Get a single Division Operations Report."""
    report = _governance().get_report_dict(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"report": report}


@app.get("/api/governance/reports/{report_id}/export")
async def governance_export_report(report_id: str):
    """Export a Division Operations Report as markdown."""
    governance = _governance()
    report = governance.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {
        "report_markdown": report.report_markdown or "",
        "request": report.request,
        "subject_type": report.subject_type,
        "governance_score": report.governance_score,
        "final_decision": report.final_decision,
        "avg_confidence": report.avg_confidence,
        "total_checks": report.total_checks,
        "total_findings": report.total_findings,
        "total_recommendations": report.total_recommendations,
        "operations_brief": report.operations_brief,
    }


@app.post("/api/governance/reports/{report_id}/cancel")
async def governance_cancel_report(report_id: str):
    """Cancel a running operations review task."""
    governance = _governance()
    task = governance._running.get(report_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Review is not running"}, status_code=400)


@app.delete("/api/governance/reports/{report_id}")
async def governance_delete_report(report_id: str):
    """Delete a Division Operations Report."""
    governance = _governance()
    if not governance.delete_report(report_id):
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/governance/reports/{report_id}/to-board")
async def governance_send_to_board(report_id: str):
    """Send a completed Division Operations Report to the Executive Product
    Board for review.

    The board runs a full review using the operation subject plus the report
    summary as context - the 'EAGOD orchestrates, the board decides strategy'
    flow.
    """
    governance = _governance()
    report = governance.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    if report.status != "completed":
        return JSONResponse({"error": "Report is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = governance.board_request_text(report)
    if app_state.get("governance_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    report.board_review_id = result.get("review_id") or result.get("id")
    governance.persist()
    return {
        "status": "sent",
        "board_review_id": report.board_review_id,
        "board_review": result,
    }


# --- Layer 10: Enterprise Knowledge & Digital Twin Platform (EKDT) ---

def _ekdt() -> "EkdtDivision":
    d = app_state.get("ekdt")
    if d is None:
        raise RuntimeError("Enterprise Knowledge & Digital Twin Platform is not initialized")
    return d


@app.get("/api/ekdt/departments")
async def ekdt_departments():
    """List the twelve knowledge systems (Knowledge Architect last)."""
    try:
        return {"departments": _ekdt().departments()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ekdt/stats")
async def ekdt_stats():
    """Enterprise Knowledge & Digital Twin Platform statistics + intelligence dashboard."""
    try:
        return _ekdt().stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ekdt/reports")
async def ekdt_list_reports():
    """List all Digital Twin Update Reports."""
    try:
        return {"reports": _ekdt().list_reports()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ekdt/reports")
async def ekdt_submit(data: dict):
    """Submit an enterprise knowledge subject for a Digital Twin Update
    Report. Runs in the background.

    wait=true blocks until the report finishes (useful for tests/CLI).
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    subject_type = data.get("subject_type", "idea")
    ekdt = _ekdt()
    if subject_type not in ekdt.stats().get("subject_types", []):
        return JSONResponse(
            {"error": f"subject_type must be one of {ekdt.stats().get('subject_types', [])}"},
            status_code=400,
        )
    if data.get("wait"):
        result = await ekdt.run_review_sync(request=request, subject_type=subject_type)
        return {"status": "completed", "report": result}
    result = await ekdt.run_review(request=request, subject_type=subject_type)
    return result


@app.get("/api/ekdt/reports/{report_id}")
async def ekdt_get_report(report_id: str):
    """Get a single Digital Twin Update Report."""
    report = _ekdt().get_report_dict(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"report": report}


@app.get("/api/ekdt/reports/{report_id}/export")
async def ekdt_export_report(report_id: str):
    """Export a Digital Twin Update Report as markdown."""
    ekdt = _ekdt()
    report = ekdt.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {
        "report_markdown": report.report_markdown or "",
        "request": report.request,
        "subject_type": report.subject_type,
        "knowledge_score": report.knowledge_score,
        "knowledge_status": report.knowledge_status,
        "avg_confidence": report.avg_confidence,
        "total_checks": report.total_checks,
        "total_findings": report.total_findings,
        "total_recommendations": report.total_recommendations,
        "knowledge_brief": report.knowledge_brief,
    }


@app.post("/api/ekdt/reports/{report_id}/cancel")
async def ekdt_cancel_report(report_id: str):
    """Cancel a running knowledge update task."""
    ekdt = _ekdt()
    task = ekdt._running.get(report_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    return JSONResponse({"error": "Review is not running"}, status_code=400)


@app.delete("/api/ekdt/reports/{report_id}")
async def ekdt_delete_report(report_id: str):
    """Delete a Digital Twin Update Report."""
    ekdt = _ekdt()
    if not ekdt.delete_report(report_id):
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/ekdt/reports/{report_id}/to-board")
async def ekdt_send_to_board(report_id: str):
    """Send a completed Digital Twin Update Report to the Executive Product
    Board for strategy review - the 'EKDT remembers, the board decides' flow.
    """
    ekdt = _ekdt()
    report = ekdt.get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    if report.status != "completed":
        return JSONResponse({"error": "Report is not completed"}, status_code=400)
    board: "ExecutiveProductBoard" = app_state["board"]
    if board is None:
        return JSONResponse({"error": "Executive Product Board is not initialized"}, status_code=500)
    request_text = ekdt.board_request_text(report)
    if app_state.get("ekdt_wait_board"):
        result = await board.run_review_sync(request=request_text)
    else:
        result = await board.run_review(request=request_text)
    report.board_review_id = result.get("review_id") or result.get("id")
    ekdt.persist()
    return {
        "status": "sent",
        "board_review_id": report.board_review_id,
        "board_review": result,
    }


# --- Layer 0 - Company Information ---

def _company():
    s = app_state.get("company")
    if s is None:
        raise RuntimeError("Layer 0 Company Store is not initialized")
    return s


@app.get("/api/company/profile")
async def company_get_profile(user_id: str = ""):
    """Get the company profile for a user."""
    if user_id:
        return _company().get_user_profile(user_id).model_dump()
    return {}


@app.put("/api/company/profile")
async def company_update_profile(data: dict):
    """Update the company profile for a user."""
    user_id = data.pop("user_id", "")
    if user_id:
        result = _company().update_user_profile(user_id, data)
    else:
        result = _company().update_profile(data)
    return {"status": "updated", "profile": result.model_dump()}


@app.get("/api/company/projects")
async def company_list_projects(user_id: str = ""):
    """List company projects for a user."""
    if user_id:
        return {"projects": _company().list_user_projects(user_id)}
    return {"projects": []}


@app.get("/api/company/projects/{project_id}")
async def company_get_project(project_id: str, user_id: str = ""):
    """Get a single project."""
    project = _company().get_project_dict(project_id)
    if not project:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    return project


@app.post("/api/company/projects")
async def company_add_project(data: dict):
    """Add a new project for a user."""
    user_id = data.pop("user_id", "")
    if not data.get("name", "").strip():
        return JSONResponse({"error": "Project name is required"}, status_code=400)
    if user_id:
        project = _company().add_user_project(user_id, data)
    else:
        project = _company().add_project(data)
    return {"status": "created", "project": project.model_dump()}


@app.put("/api/company/projects/{project_id}")
async def company_update_project(project_id: str, data: dict):
    """Update a project."""
    user_id = data.pop("user_id", "")
    if user_id:
        project = _company().update_user_project(user_id, project_id, data)
    else:
        project = _company().update_project(project_id, data)
    if not project:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    return {"status": "updated", "project": project.model_dump()}


@app.delete("/api/company/projects/{project_id}")
async def company_delete_project(project_id: str, user_id: str = ""):
    """Delete a project."""
    if user_id:
        if _company().delete_user_project(user_id, project_id):
            return {"status": "deleted"}
    else:
        if _company().delete_project(project_id):
            return {"status": "deleted"}
    return JSONResponse({"error": "Project not found"}, status_code=404)


@app.get("/api/company/search")
async def company_search(q: str = ""):
    """Search projects by name, description, tags."""
    if not q:
        return {"projects": _company().list_projects()}
    results = _company().search_projects(q)
    return {"projects": [p.model_dump() for p in results]}


@app.get("/api/company/all")
async def company_get_all():
    """Get all Layer 0 data (profile + projects). For CEO agent."""
    return {
        "profile": _company().get_profile().model_dump(),
        "projects": _company().list_projects(),
        "text": _company().get_all_text(),
    }


# --- Layer 1 CEO Agent (Client-Facing Communication) ---

_ceo_agent = None

def _get_ceo():
    global _ceo_agent
    if _ceo_agent is None:
        from agents.ceo.agent import CEOAgent
        _ceo_agent = CEOAgent(
            app_state["llm_manager"],
            company_store=app_state.get("company"),
            ekdt_store=app_state.get("ekdt"),
        )
    return _ceo_agent


@app.get("/api/ce/conversations")
async def ceo_list_conversations():
    """List all CEO conversations."""
    return {"conversations": _get_ceo().list_conversations()}


@app.post("/api/ce/conversations")
async def ceo_create_conversation(data: dict):
    """Create a new CEO conversation."""
    conv = _get_ceo().create_conversation(
        client_name=data.get("client_name", ""),
        project_name=data.get("project_name", ""),
    )
    return {"id": conv.id, "status": conv.status}


@app.get("/api/ce/conversations/{conv_id}")
async def ceo_get_conversation(conv_id: str):
    """Get a CEO conversation with all messages."""
    conv = _get_ceo().get_conversation(conv_id)
    if not conv:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return conv.model_dump()


@app.delete("/api/ce/conversations/{conv_id}")
async def ceo_delete_conversation(conv_id: str):
    """Delete a CEO conversation."""
    ok = _get_ceo().delete_conversation(conv_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"status": "deleted"}


@app.patch("/api/ce/conversations/{conv_id}")
async def ceo_rename_conversation(conv_id: str, data: dict):
    """Rename a CEO conversation."""
    name = data.get("project_name", "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "project_name required"})
    ok = _get_ceo().rename_conversation(conv_id, name)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"status": "renamed"}


@app.post("/api/ce/conversations/{conv_id}/chat")
async def ceo_chat(conv_id: str, body: dict = Body(...)):
    """Send a message to the CEO agent."""
    import logging as _log; _log.getLogger(__name__).info(f"[CEO CHAT ENTERED] conv_id={conv_id}")
    try:
        message = body.get("message", "")
        if not message:
            return JSONResponse(status_code=400, content={"error": "message required"})
        result = await _get_ceo().chat(conv_id, message)
        print(f"[CEO CHAT] action={result.get('action')}, error={result.get('error')}, dev_id={result.get('dev_team_task_id')}")
        if "error" in result:
            print(f"[CEO CHAT ERROR] {result['error']}", )
            return JSONResponse(status_code=500, content=result)

        # If the CEO forwarded to Layer 2, actually start the workflow
        if result.get("action") == "forwarded_to_layer2" and result.get("workflow_run_id", "").startswith("pending-"):
            conv = _get_ceo().get_conversation(conv_id)
            if conv:
                try:
                    request_text = await _get_ceo()._build_project_description(conv)
                    workflow = _workflow()
                    wf_result = await workflow.start(request_text, name=conv.project_name or "Client Project")
                    run_id = wf_result.get("run_id", "")
                    conv.workflow_run_id = run_id
                    conv.context["workflow_run_id"] = run_id
                    _get_ceo().persist()
                    result["workflow_run_id"] = run_id
                    if conv.messages and conv.messages[-1].role == "assistant":
                        conv.messages[-1].content += (
                            "\n\n---\n"
                            "I've handed off your project to our Executive Board and engineering team. "
                            f"Workflow ID: {run_id}\n\n"
                            "You can track progress in the Workflow dashboard. "
                            "The board will review your project and our layers will begin working on it."
                        )
                        _get_ceo().persist()
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    result["workflow_error"] = str(e)

        # If the CEO sent directly to dev team, create task and start pipeline
        if result.get("action") == "sent_to_dev_team" and result.get("dev_team_task_id", "").startswith("pending-dev-"):
            print(f"[CEO DEV TEAM] Starting dev team flow for conv {conv_id}", )
            conv = _get_ceo().get_conversation(conv_id)
            if conv:
                try:
                    # Generate a proper project brief from the conversation
                    request_text = await _get_ceo()._build_project_description(conv)
                    hermes: HermesOrchestrator = app_state["hermes"]
                    pipeline: Pipeline = app_state["pipeline"]

                    # Try to extract project folder from conversation messages
                    import re as _re, os as _os
                    project_folder = ""
                    all_user_text = ""
                    for msg in conv.messages:
                        if msg.role == "user":
                            all_user_text += " " + msg.content
                            # Find drive-letter paths
                            candidates = _re.findall(r'([A-Z]:[/\\][^\s,;.!?]+(?:\s[^\s,;.!?]+)*)', msg.content, _re.IGNORECASE)
                            candidates += _re.findall(r'(/(?:home|usr|var|opt|tmp|etc|sir|Users)[^\s,;.!?]+)', msg.content)
                            for candidate in sorted(candidates, key=len, reverse=True):
                                candidate = candidate.strip().rstrip("\\/")
                                # Find last slash to get parent + last component
                                last_sep = max(candidate.rfind('/'), candidate.rfind('\\'))
                                if last_sep > 2:
                                    parent = candidate[:last_sep]
                                    last_part = candidate[last_sep+1:]
                                    # Trim words from last_part until parent/dir exists
                                    words = last_part.split()
                                    for i in range(len(words), 0, -1):
                                        test_path = parent + candidate[last_sep] + " ".join(words[:i])
                                        if _os.path.isdir(test_path):
                                            project_folder = test_path
                                            break
                                elif _os.path.isdir(candidate):
                                    project_folder = candidate
                                if project_folder:
                                    break

                    # Fallback: search common project directories by name/keywords
                    if not project_folder:
                        search_roots = ["D:/sir projectss", "D:/sir projects", "D:/projects", "C:/Users/Digital/Desktop"]
                        keywords = [w.lower() for w in all_user_text.split() if len(w) > 3 and w.lower() not in ("project", "issue", "issues", "build", "error", "fix", "resolve", "failed", "failure", "there", "with", "from", "that", "this", "have", "been", "some", "need", "please", "check", "look")]
                        if keywords:
                            for root in search_roots:
                                if not _os.path.isdir(root):
                                    continue
                                try:
                                    for entry in _os.listdir(root):
                                        entry_path = _os.path.join(root, entry)
                                        if not _os.path.isdir(entry_path):
                                            continue
                                        entry_lower = entry.lower()
                                        match_count = sum(1 for kw in keywords if kw in entry_lower)
                                        if match_count >= 1:
                                            project_folder = entry_path.replace("\\", "/")
                                            print(f"[CEO DEV TEAM] Found project folder via keyword search: {project_folder}")
                                            break
                                except PermissionError:
                                    continue
                                if project_folder:
                                    break

                    print(f"[CEO DEV TEAM] Project folder: {project_folder or '(not found)'}", )

                    from shared.models import TaskPriority
                    task = await hermes.create_task(
                        title=conv.project_name or "Fix/Update Project",
                        description=request_text,
                        priority=TaskPriority.HIGH,
                        metadata={"task_mode": "developer", "source": "ceo_direct"},
                    )
                    task_id = task.id
                    print(f"[CEO DEV TEAM] Created task {task_id}", )

                    from pipeline.engine import PipelineTask
                    pt = PipelineTask(
                        task_id=task_id,
                        project_id=task.project_id or "",
                        title=task.title,
                        description=task.description,
                        project_mode="fix",
                        project_folder=project_folder,
                        project_description=request_text,
                        project_name=conv.project_name or "",
                        task_mode="developer",
                    )
                    pipeline.tasks[task_id] = pt
                    pt._persist_callback = pipeline._persist
                    pipeline._persist()
                    pipeline._spawn_task(pipeline.start_building(task_id), task_id)
                    print(f"[CEO DEV TEAM] Pipeline started for task {task_id}", )

                    conv.context["dev_team_task_id"] = task_id
                    _get_ceo().persist()
                    result["dev_team_task_id"] = task_id
                    if conv.messages and conv.messages[-1].role == "assistant":
                        last_msg = conv.messages[-1]
                        last_msg.task_id = task_id
                        last_msg.content += (
                            "\n\n---\n"
                            "I've sent your request directly to the development team. "
                            f"Task ID: {task_id}\n\n"
                            "They'll start working on it right away."
                        )
                        _get_ceo().persist()
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    result["dev_team_error"] = str(e)
                    print(f"[CEO DEV TEAM ERROR] {e}", )

        print(f"[CEO CHAT DEBUG] result keys={list(result.keys())}, types={[(k, type(v).__name__) for k,v in result.items()]}", )
        return JSONResponse(content=result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[CEO CHAT CATCH-ALL] {e}", )
        return JSONResponse(status_code=500, content={"error": str(e)})


# --- Cross-Layer Workflow Orchestration (Board -> Research -> UX -> Design -> Growth -> Quality) ---

def _workflow() -> "WorkflowEngine":
    w = app_state.get("workflow")
    if w is None:
        raise RuntimeError("Cross-Layer Workflow Orchestration is not initialized")
    return w


@app.get("/api/workflow/stages")
async def workflow_stages():
    """List the gated layer chain."""
    return {"stages": _workflow().stage_defs()}


@app.get("/api/workflow/stats")
async def workflow_stats():
    """Cross-layer workflow statistics."""
    return _workflow().stats()


@app.get("/api/workflow/runs")
async def workflow_list_runs():
    """List all workflow runs."""
    return {"runs": _workflow().list_runs()}


@app.get("/api/workflow/runs/{run_id}")
async def workflow_get_run(run_id: str):
    """Get a single workflow run with its stage-by-stage gate status."""
    run = _workflow().get_run_dict(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return {"run": run}


@app.post("/api/workflow/runs")
async def workflow_start(data: dict):
    """Start a cross-layer workflow run with a project request.

    The run starts at the Executive Product Board (Layer 2) and auto-advances
    through Research, UX, Design, Growth and Quality gates on each board
    approval. wait=true blocks until the run pauses or completes.
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    name = data.get("name", "").strip()
    if data.get("wait"):
        result = await _workflow().start_sync(request=request, name=name)
        return {"status": "finished", "run": result}
    result = await _workflow().start(request=request, name=name)
    return result


@app.post("/api/workflow/runs/{run_id}/retry")
async def workflow_retry(run_id: str, data: dict):
    """Retry a paused (rejected) stage with an edited request.

    Re-runs only the current stage's board review with the edited text.
    If approved, the run auto-advances to the next layer.
    """
    request = data.get("request", "").strip()
    if not request:
        return JSONResponse({"error": "request is required"}, status_code=400)
    engine = _workflow()
    run = engine.get_run(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    if run.status != "needs_review":
        return JSONResponse({"error": "Run is not paused for review"}, status_code=400)
    if data.get("wait"):
        result = await engine.retry_sync(run_id, request)
        if isinstance(result, dict) and result.get("status") in ("not_found", "not_paused"):
            return JSONResponse({"error": "Run not found" if result.get("status") == "not_found" else "Run is not paused for review"}, status_code=404 if result.get("status") == "not_found" else 400)
        return {"status": "finished", "run": result}
    result = await engine.retry(run_id, request)
    if isinstance(result, dict) and result.get("status") in ("not_found", "not_paused"):
        return JSONResponse({"error": "Run not found" if result.get("status") == "not_found" else "Run is not paused for review"}, status_code=404 if result.get("status") == "not_found" else 400)
    return result


@app.post("/api/workflow/runs/{run_id}/resume")
async def workflow_resume(run_id: str):
    """Resume a failed workflow run from the stage where it stopped.

    Approved earlier layers are kept - only the failed gate is re-run and
    re-submitted to the board. Useful after a transient LLM outage/quota blip.
    """
    engine = _workflow()
    result = await engine.resume(run_id)
    if result.get("status") == "not_found":
        return JSONResponse({"error": "Run not found"}, status_code=404)
    if result.get("status") == "not_failed":
        return JSONResponse({"error": "Only failed runs can be resumed"}, status_code=400)
    return {"status": "resuming", "run_id": run_id}


@app.post("/api/workflow/runs/{run_id}/cancel")
async def workflow_cancel(run_id: str):
    """Cancel a running workflow."""
    engine = _workflow()
    run = engine.get_run(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    if run.status != "running":
        return JSONResponse({"error": "Run is not running"}, status_code=400)
    if not await engine.cancel(run_id):
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return {"status": "cancelled", "run": engine.get_run_dict(run_id)}


@app.delete("/api/workflow/runs/{run_id}")
async def workflow_delete(run_id: str):
    """Delete a workflow run."""
    if not _workflow().delete_run(run_id):
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return {"status": "deleted"}


@app.post("/api/workflow/runs/{run_id}/start-build")
async def workflow_start_build(run_id: str, data: dict = {}):
    """Send a completed workflow run to the development team.

    Assembles all approved layer outputs (Board, Research, UX, Design, Growth,
    Quality) into a Development Package, creates a Hermes project + build task
    with the package attached as the spec, and starts the pipeline build.
    """
    engine = _workflow()
    run = engine.get_run(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    if run.status != "completed":
        return JSONResponse({"error": "Run must be completed before starting a build"}, status_code=400)

    package = engine.build_development_package(run_id)
    if not package or package.get("stage_count", 0) == 0:
        return JSONResponse({"error": "No approved layer artifacts found for this run"}, status_code=400)

    folder = (data.get("folder") or "").strip()
    if not folder:
        return JSONResponse({"error": "folder is required - choose where the project should be built"}, status_code=400)

    hermes: HermesOrchestrator = app_state["hermes"]
    pipeline: Pipeline = app_state["pipeline"]

    project = await hermes.create_project(
        name=run.name,
        codename=(run.name[:24].strip().replace(" ", "-").lower() or "workflow-project"),
        description=(package["request"] or run.name)[:500],
        tech_stack=[],
    )
    project.folder = folder
    project.mode = "scratch"
    project.metadata["workflow_run_id"] = run_id

    task = await hermes.create_task(
        title=f"Build {run.name}",
        description=(
            f"Built from workflow run {run_id} - all layers approved.\n\n"
            f"Original request: {run.request}\n\n"
            f"{package['markdown'][:4000]}"
        ),
        project_id=project.id,
        metadata={"source": "workflow", "workflow_run_id": run_id},
    )

    from pipeline.engine import PipelineTask
    pt = PipelineTask(
        task_id=task.id,
        project_id=project.id,
        title=task.title,
        description=task.description,
        project_mode="scratch",
        project_folder=folder,
        project_description=(package["request"] or run.name)[:2000],
        project_name=run.name,
    )
    pt.dev_package = package["markdown"]
    pipeline.tasks[task.id] = pt
    pt._persist_callback = pipeline._persist
    pipeline._persist()

    pipeline._spawn_task(pipeline.start_building(task.id), task.id)
    return {
        "status": "started",
        "task_id": task.id,
        "project_id": project.id,
        "project_name": run.name,
        "stage_count": package["stage_count"],
    }


# ===================================================================
# VPS DEPLOYMENT ENDPOINTS
# ===================================================================

from deployment.engine import VPSEngine
from deployment.ssh import create_vps_server, mask_secret
from deployment.models import CreateVPSDeploymentRequest, DeployMode

vps_engine = VPSEngine()
_deploy_background_tasks: dict[str, asyncio.Task] = {}


@app.post("/api/vps-deployments")
async def create_vps_deployment(req: CreateVPSDeploymentRequest):
    """Create and start a VPS deployment."""
    try:
        dep = await vps_engine.create_deployment(req)
        task = asyncio.create_task(vps_engine.run_deployment(dep.id))
        _deploy_background_tasks[dep.id] = task
        return {
            "deployment_id": dep.id,
            "status": dep.status.value,
            "project_name": dep.project_name,
        }
    except Exception as e:
        logger.error(f"VPS deployment creation failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500


@app.get("/api/vps-deployments")
async def list_vps_deployments():
    """List all VPS deployments."""
    deployments = []
    for dep in vps_engine._deployments.values():
        d = dep.model_dump()
        # Mask sensitive fields
        d.pop("encrypted_private_key", None)
        d.pop("encrypted_password", None)
        d["steps_count"] = len(vps_engine.get_steps(dep.id))
        d["steps_passed"] = sum(1 for s in vps_engine.get_steps(dep.id) if s.status.value == "passed")
        deployments.append(d)
    deployments.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"deployments": deployments}


@app.get("/api/vps-deployments/{dep_id}")
async def get_vps_deployment(dep_id: str):
    """Get a VPS deployment with steps, logs, and health checks."""
    dep = vps_engine.get_deployment(dep_id)
    if not dep:
        return {"error": "Deployment not found"}, 404
    d = dep.model_dump()
    d.pop("encrypted_private_key", None)
    d.pop("encrypted_password", None)
    return {
        "deployment": d,
        "steps": [s.model_dump() for s in vps_engine.get_steps(dep_id)],
        "logs": [l.model_dump() for l in vps_engine.get_logs(dep_id)],
        "health_checks": [h.model_dump() for h in vps_engine.get_health_checks(dep_id)],
    }


@app.get("/api/vps-deployments/{dep_id}/logs")
async def get_vps_deployment_logs(dep_id: str, limit: int = 100):
    """Get deployment logs."""
    return {"logs": [l.model_dump() for l in vps_engine.get_logs(dep_id, limit)]}


@app.post("/api/vps-deployments/{dep_id}/approve")
async def approve_vps_deployment(dep_id: str):
    """Approve a deployment plan."""
    await vps_engine.approve_deployment(dep_id)
    return {"status": "approved"}


@app.post("/api/vps-deployments/{dep_id}/cancel")
async def cancel_vps_deployment(dep_id: str):
    """Cancel a running deployment."""
    await vps_engine.cancel_deployment(dep_id)
    return {"status": "cancelled"}


@app.post("/api/vps-deployments/{dep_id}/rollback")
async def rollback_vps_deployment(dep_id: str):
    """Rollback a deployment."""
    dep = vps_engine.get_deployment(dep_id)
    if dep and dep.rollback_available:
        await vps_engine._auto_rollback(dep)
        return {"status": "rolled_back"}
    return {"error": "No rollback available"}, 400


@app.post("/api/vps-deployments/{dep_id}/retry")
async def retry_vps_deployment(dep_id: str):
    """Retry a failed deployment."""
    await vps_engine.retry_deployment(dep_id)
    return {"status": "retrying"}


@app.post("/api/vps-deployments/{dep_id}/health")
async def check_vps_health(dep_id: str):
    """Run health checks on a deployment."""
    dep = vps_engine.get_deployment(dep_id)
    if not dep:
        return {"error": "Deployment not found"}, 404
    tools = vps_engine._tools.get(dep_id)
    if not tools:
        return {"error": "Not connected"}, 400
    result = await vps_engine._run_tool(dep_id, "health_check", lambda t: t.health_check(dep.health_check_url, dep.service_name))
    return {"health": result}


@app.get("/api/vps-servers")
async def list_vps_servers():
    """List saved VPS servers (credentials never exposed)."""
    servers = []
    for dep in vps_engine._deployments.values():
        if dep.vps_server_id:
            servers.append({
                "id": dep.vps_server_id,
                "project": dep.project_name,
            })
    return {"servers": servers}


@app.delete("/api/vps-deployments/{dep_id}")
async def delete_vps_deployment(dep_id: str):
    """Delete a VPS deployment."""
    dep = vps_engine.get_deployment(dep_id)
    if not dep:
        return JSONResponse({"error": "Deployment not found"}, status_code=404)
    try:
        await vps_engine.cancel_deployment(dep_id)
    except Exception:
        pass
    vps_engine._deployments.pop(dep_id, None)
    vps_engine._steps.pop(dep_id, None)
    vps_engine._logs.pop(dep_id, None)
    vps_engine._health_checks.pop(dep_id, None)
    vps_engine._connections.pop(dep_id, None)
    # Delete from Neon DB
    memory = app_state.get("memory")
    if memory:
        try:
            await memory.delete_vps_deployment(dep_id)
        except Exception:
            pass
    return {"status": "deleted"}


@app.delete("/api/pipeline/{task_id}")
async def delete_pipeline_task(task_id: str):
    """Delete a pipeline/build task."""
    try:
        hermes: HermesOrchestrator = app_state["hermes"]
        pipeline: Pipeline = app_state["pipeline"]
        try:
            pipeline.cancel_task(task_id)
        except Exception:
            pass
        hermes.tasks.pop(task_id, None)
        pipeline.tasks.pop(task_id, None)
        _persist_both(hermes, pipeline)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# --- Run ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "apps.api.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=False,
        workers=1,
    )
