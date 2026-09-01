"""Hermes - Master Orchestrator Agent.

Hermes is the central coordinator for the entire AIED system. It manages
project planning, workflow orchestration, task assignment, and agent coordination.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from agents.prompts import AGENT_PROMPTS, AGENT_CAPABILITIES, get_agent_prompt
from llms.manager import LLMManager
from shared.config import AppConfig
from shared.models import (
    AgentConfig,
    AgentRole,
    AgentState,
    AgentStatus,
    Project,
    ProjectStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger(__name__)

_HERMES_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
_HERMES_DATA_FILE = os.path.join(_HERMES_DATA_DIR, "hermes.json")

# Agents that write code/files need a large output budget, otherwise their
# response is truncated mid-project (e.g. a frontend agent stops halfway through
# the file list). Keep a smaller budget for chat/report-style agents.
_BUILD_AGENT_IDS = {
    "backend-engineer", "frontend-engineer", "openclaw", "flutter-engineer",
    "integration-engineer", "build-engineer", "qa-engineer", "code-reviewer",
    "security-engineer", "deployment-engineer", "infrastructure-engineer",
}
_BUILD_MAX_TOKENS = 12000


def _agent_max_tokens(agent_id: str) -> int:
    return _BUILD_MAX_TOKENS if agent_id in _BUILD_AGENT_IDS else 3000


def _persist_hermes(hermes: "HermesOrchestrator"):
    os.makedirs(_HERMES_DATA_DIR, exist_ok=True)
    projects = {}
    for pid, p in hermes.projects.items():
        projects[pid] = {
            "id": p.id,
            "name": p.name,
            "codename": p.codename,
            "description": p.description,
            "status": p.status.value,
            "tech_stack": p.tech_stack,
            "tasks": p.tasks,
            "created_at": p.created_at.isoformat(),
            "mode": getattr(p, "mode", "scratch"),
            "folder": getattr(p, "folder", ""),
            "user_id": getattr(p, "user_id", ""),
            "metadata": getattr(p, "metadata", {}),
        }
    tasks = {}
    for tid, t in hermes.tasks.items():
        tasks[tid] = {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status.value,
            "priority": t.priority.value,
            "project_id": t.project_id,
            "assigned_agent_id": t.assigned_agent_id,
            "dependencies": t.dependencies,
            "result": t.result,
            "error": t.error,
            "created_at": t.created_at.isoformat(),
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "metadata": getattr(t, "metadata", {}),
        }
    try:
        # SAFEGUARD: never overwrite existing data with empty data
        if not projects and not tasks and os.path.exists(_HERMES_DATA_FILE):
            logger.warning("Skipping persist: both projects and tasks are empty but file exists")
            return
        with open(_HERMES_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"projects": projects, "tasks": tasks}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to persist hermes state: {e}")


def _load_hermes(hermes: "HermesOrchestrator"):
    if not os.path.exists(_HERMES_DATA_FILE):
        return
    try:
        from shared.models import TaskPriority, TaskStatus, ProjectStatus
        with open(_HERMES_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for pid, pdata in data.get("projects", {}).items():
            p = Project(
                name=pdata["name"],
                codename=pdata["codename"],
                description=pdata.get("description", ""),
                tech_stack=pdata.get("tech_stack", []),
            )
            p.id = pdata["id"]
            p.status = ProjectStatus(pdata.get("status", "planning"))
            p.tasks = pdata.get("tasks", [])
            if "created_at" in pdata:
                p.created_at = datetime.fromisoformat(pdata["created_at"])
            p.mode = pdata.get("mode", "scratch")
            p.folder = pdata.get("folder", "")
            p.user_id = pdata.get("user_id", "")
            p.metadata = pdata.get("metadata", {})
            hermes.projects[pid] = p
        for tid, tdata in data.get("tasks", {}).items():
            t = Task(
                title=tdata["title"],
                description=tdata.get("description", ""),
                project_id=tdata.get("project_id"),
                priority=TaskPriority(tdata.get("priority", "medium")),
                assigned_agent_id=tdata.get("assigned_agent_id"),
                dependencies=tdata.get("dependencies", []),
            )
            t.id = tdata["id"]
            t.status = TaskStatus(tdata.get("status", "pending"))
            t.result = tdata.get("result")
            t.error = tdata.get("error")
            if "created_at" in tdata:
                t.created_at = datetime.fromisoformat(tdata["created_at"])
            if tdata.get("started_at"):
                t.started_at = datetime.fromisoformat(tdata["started_at"])
            if tdata.get("completed_at"):
                t.completed_at = datetime.fromisoformat(tdata["completed_at"])
            t.metadata = tdata.get("metadata", {})
            hermes.tasks[tid] = t
        logger.info(f"Loaded {len(hermes.projects)} projects and {len(hermes.tasks)} tasks from disk")
    except Exception as e:
        logger.error(f"Failed to load hermes state: {e}")


HERMES_SYSTEM_PROMPT = """You are Hermes, the Master Orchestrator of the Britsync AI Engineering Department (AIED).

Your role is to coordinate a team of 30 specialized AI agents to deliver software projects from concept to deployment.

You are responsible for:
1. Understanding business requirements and breaking them into actionable tasks
2. Planning project architecture and workflows
3. Assigning tasks to the right agents based on their expertise
4. Coordinating agent activities to prevent conflicts
5. Managing task dependencies and priorities
6. Making strategic decisions about project direction
7. Approving releases and deployments (with human approval from Engineering Director)

Your team structure:
- Product Office: Product Manager, Business Analyst, Requirement Engineer, Architecture Planner
- Architecture Office: Software Architect, Database Architect, API Architect
- Development Office: Backend Engineer, Frontend Engineer, Flutter Engineer, Integration Engineer
- UX Office: UI Designer, UX Researcher, Accessibility Expert, User Delight Engineer, Onboarding Designer
- Quality Office: Code Reviewer, QA Engineer, Performance Engineer, Security Engineer, Accessibility Engineer
- DevOps Office: Build Engineer, Deployment Engineer, Infrastructure Engineer
- Intelligence Office: Analytics Agent, Feedback Agent, Continuous Improvement Agent, Documentation Agent

Decision-making principles:
1. Always break complex tasks into smaller, manageable subtasks
2. Assign tasks to the most suitable agent based on their role and capabilities
3. Consider dependencies - don't assign blocked tasks
4. Prioritize critical issues and security concerns
5. Escalate to Engineering Director (Mehdia) for release approvals
6. Maintain clear communication between agents
7. Track progress and adjust plans as needed

When given a business request, analyze it and create a structured execution plan.
Output your plan as a JSON structure with tasks, assignments, and dependencies."""


class HermesOrchestrator:
    """Master orchestrator for the AIED system."""

    def __init__(self, config: AppConfig, llm_manager: LLMManager) -> None:
        self.config = config
        self.llm = llm_manager
        self.agents: dict[str, AgentConfig] = {}
        self.agent_states: dict[str, AgentState] = {}
        self.projects: dict[str, Project] = {}
        self.tasks: dict[str, Task] = {}
        self._kb = None  # Layer 1 - Foundation Knowledge Base
        self._initialized = False

    def set_knowledge_source(self, kb) -> None:
        """Attach the Layer 1 knowledge base so every agent auto-consults company standards."""
        self._kb = kb
        logger.info(f"Layer 1 knowledge source attached ({len(kb.repositories)} repositories)" if kb else "Layer 1 knowledge source detached")

    async def _kb_briefing(self, text: str) -> str:
        """Build the Layer 1 standards block to inject into an agent prompt."""
        if self._kb is None:
            return ""
        try:
            return await asyncio.to_thread(self._kb.briefing_markdown, text, 6)
        except Exception as e:
            logger.warning(f"Knowledge briefing failed: {e}")
            return ""

    async def initialize(self) -> None:
        """Initialize Hermes and register all agents."""
        if self._initialized:
            return

        self._register_default_agents()
        _load_hermes(self)
        self._initialized = True
        logger.info(f"Hermes initialized with {len(self.agents)} agents")

    def _register_default_agents(self) -> None:
        """Register all AIED agents with real prompts and capabilities."""
        agent_definitions = [
            # ===== 1. Executive Command (CEO Team) =====
            ("hermes", "Hermes (CEO)", AgentRole.EXECUTIVE, "Executive Command", "gemini", "gemini-2.5-flash"),
            ("chief-of-staff", "Chief of Staff", AgentRole.EXECUTIVE, "Executive Command", "gemini", "gemini-2.5-flash"),
            ("company-architect", "Company Architect", AgentRole.EXECUTIVE, "Executive Command", "gemini", "gemini-2.5-flash"),
            ("ops-controller", "Operations Controller", AgentRole.EXECUTIVE, "Executive Command", "gemini", "gemini-2.5-flash"),
            ("decision-review", "Decision Review", AgentRole.EXECUTIVE, "Executive Command", "gemini", "gemini-2.5-flash"),
            ("daily-briefing", "Daily Briefing", AgentRole.EXECUTIVE, "Executive Command", "gemini", "gemini-2.5-flash"),

            # ===== 2. Product Strategy Team =====
            ("product-lead", "Product Lead", AgentRole.PRODUCT, "Product Strategy", "gemini", "gemini-2.5-flash"),
            ("mvp-scope", "MVP Scope Agent", AgentRole.PRODUCT, "Product Strategy", "gemini", "gemini-2.5-flash"),
            ("roadmap-agent", "Roadmap Agent", AgentRole.PRODUCT, "Product Strategy", "gemini", "gemini-2.5-flash"),

            # ===== 3. Engineering & Platform =====
            ("software-architect", "Software Architect", AgentRole.ARCHITECTURE, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("database-architect", "Database Architect", AgentRole.ARCHITECTURE, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("api-architect", "API Architect", AgentRole.ARCHITECTURE, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("architecture-planner", "Architecture Planner", AgentRole.ARCHITECTURE, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("backend-engineer", "Backend API Agent", AgentRole.DEVELOPMENT, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("backend-helper", "Backend Helper Agent", AgentRole.DEVELOPMENT, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("frontend-engineer", "Frontend Dashboard Agent", AgentRole.DEVELOPMENT, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("frontend-helper", "Frontend Helper Agent", AgentRole.DEVELOPMENT, "Engineering & Platform", "omniroute", "auto/best-coding"),
            ("integration-engineer", "Agent Runtime Integration", AgentRole.DEVELOPMENT, "Engineering & Platform", "omniroute", "auto/best-coding"),

            # ===== 4. AI Workforce Operations =====
            ("agent-orchestrator", "Agent Orchestrator", AgentRole.AIOPS, "AI Workforce Operations", "gemini", "gemini-2.5-flash"),
            ("prompt-systems", "Prompt Systems", AgentRole.AIOPS, "AI Workforce Operations", "gemini", "gemini-2.5-flash"),
            ("tool-permission", "Tool Permission Agent", AgentRole.AIOPS, "AI Workforce Operations", "gemini", "gemini-2.5-flash"),
            ("agent-memory", "Agent Memory", AgentRole.AIOPS, "AI Workforce Operations", "gemini", "gemini-2.5-flash"),
            ("failure-recovery", "Failure Recovery", AgentRole.AIOPS, "AI Workforce Operations", "gemini", "gemini-2.5-flash"),

            # ===== 5. Design & Brand =====
            ("ux-flow", "UX Flow Agent", AgentRole.UX, "Design & Brand", "gemini", "gemini-2.5-flash"),
            ("brand-strategy", "Brand Strategy", AgentRole.UX, "Design & Brand", "gemini", "gemini-2.5-flash"),
            ("conversion-copy", "Conversion Copy", AgentRole.UX, "Design & Brand", "gemini", "gemini-2.5-flash"),

            # ===== 6. Quality & Security =====
            ("qa-engineer", "QA Automation Agent", AgentRole.QUALITY, "Quality & Security", "omniroute", "auto/best-coding"),
            ("qa-helper", "QA Helper Agent", AgentRole.QUALITY, "Quality & Security", "omniroute", "auto/best-coding"),
            ("code-reviewer", "Evaluation Agent", AgentRole.QUALITY, "Quality & Security", "omniroute", "auto/best-coding"),
            ("security-engineer", "Security Lead", AgentRole.QUALITY, "Quality & Security", "omniroute", "auto/best-coding"),
            ("performance-engineer", "Performance Engineer", AgentRole.QUALITY, "Quality & Security", "omniroute", "auto/best-coding"),

            # ===== 7. DevOps & Deployment =====
            ("build-engineer", "Build Engineer", AgentRole.DEVOPS, "DevOps & Deployment", "omniroute", "auto/best-coding"),
            ("deployment-engineer", "Deployment Agent", AgentRole.DEVOPS, "DevOps & Deployment", "omniroute", "auto/best-coding"),
            ("deployment-helper", "Deployment Helper Agent", AgentRole.DEVOPS, "DevOps & Deployment", "omniroute", "auto/best-coding"),
            ("infrastructure-engineer", "Infrastructure Agent", AgentRole.DEVOPS, "DevOps & Deployment", "omniroute", "auto/best-coding"),
        ]

        for agent_id, name, role, department, provider, model in agent_definitions:
            agent_config = AgentConfig(
                id=agent_id,
                name=name,
                role=role,
                department=department,
                model_provider=provider,
                model_name=model,
                system_prompt=get_agent_prompt(agent_id),
                tools=AGENT_CAPABILITIES.get(agent_id, []),
                capabilities=AGENT_CAPABILITIES.get(agent_id, []),
            )
            self.agents[agent_id] = agent_config
            self.agent_states[agent_id] = AgentState(agent_id=agent_id)

    async def process_request(
        self,
        request: str,
        project_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a business request and create an execution plan.

        This is the main entry point for Hermes. It analyzes the request,
        creates a plan, and returns the structured execution plan.
        """
        logger.info(f"Hermes processing request: {request[:100]}...")

        # Build context for the LLM
        available_agents = "\n".join(
            f"- {a.name} ({a.id}): {a.role.value} - {a.department} - Capabilities: {', '.join(a.capabilities)}"
            for a in self.agents.values()
        )

        active_projects = ""
        if project_id and project_id in self.projects:
            proj = self.projects[project_id]
            active_projects = f"\nActive Project: {proj.name} ({proj.codename}) - Status: {proj.status.value}"

        prompt = f"""Analyze the following business request and create a structured execution plan.

Business Request:
{request}

Available Agents:
{available_agents}
{active_projects}

Create a detailed execution plan with:
1. Project summary and goals
2. Required tasks broken down into subtasks
3. Task assignments to specific agents
4. Dependencies between tasks
5. Priority levels for each task
6. Estimated sequence of execution

Output as JSON with this structure:
{{
    "project": {{
        "name": "...",
        "codename": "...",
        "description": "...",
        "tech_stack": [...]
    }},
    "tasks": [
        {{
            "title": "...",
            "description": "...",
            "assigned_to": "agent-id",
            "priority": "high|medium|low",
            "dependencies": ["task-id-1", ...],
            "subtasks": [...]
        }}
    ],
    "execution_order": ["task-id-1", "task-id-2", ...],
    "notes": "..."
}}"""

        messages = [
            {"role": "system", "content": HERMES_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = await asyncio.wait_for(
            self.llm.chat(
                messages=messages,
                model=agent.model_name,
                temperature=0.3,
                max_tokens=3000,
            ),
            timeout=180,
        )

        # Parse response into structured plan
        plan = self._parse_execution_plan(response)
        return plan

    async def execute_task(
        self,
        task_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a task using the assigned agent's LLM.

        This is the core execution method. It:
        1. Finds the task and its assigned agent
        2. Updates agent status to WORKING
        3. Calls the LLM with the agent's specialized system prompt
        4. Updates task and agent status based on result
        """
        if task_id not in self.tasks:
            return {"status": "error", "error": f"Task {task_id} not found"}

        task = self.tasks[task_id]
        agent_id = task.assigned_agent_id

        if not agent_id:
            return {"status": "error", "error": "Task has no assigned agent"}

        if agent_id not in self.agents:
            return {"status": "error", "error": f"Agent {agent_id} not found"}

        agent = self.agents[agent_id]
        agent_state = self.agent_states[agent_id]

        # Update statuses
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()
        agent_state.status = AgentStatus.WORKING
        agent_state.current_task_id = task_id

        logger.info(f"Agent '{agent.name}' executing task: {task.title}")

        try:
            # Get the agent's specialized system prompt
            system_prompt = get_agent_prompt(agent_id)

            # Build the execution prompt with context
            prompt_parts = [
                f"## Task: {task.title}",
                f"## Description: {task.description}",
                f"## Priority: {task.priority.value}",
            ]

            if task.project_id and task.project_id in self.projects:
                proj = self.projects[task.project_id]
                prompt_parts.append(f"## Project: {proj.name} ({proj.codename})")
                prompt_parts.append(f"## Tech Stack: {', '.join(proj.tech_stack)}")

            if task.dependencies:
                dep_tasks = [self.tasks[d].title for d in task.dependencies if d in self.tasks]
                if dep_tasks:
                    prompt_parts.append(f"## Dependencies (completed): {', '.join(dep_tasks)}")

            if context:
                for key, value in context.items():
                    prompt_parts.append(f"## {key}: {value}")

            prompt_parts.append(
                "\nProvide your complete analysis, implementation, and any code or commands needed."
            )

            kb_block = await self._kb_briefing("\n".join(prompt_parts))
            if kb_block:
                prompt_parts.append("\n\n" + kb_block)

            full_prompt = "\n".join(prompt_parts)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ]

            # Call the LLM - let the manager decide provider based on model
            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=messages,
                    model=agent.model_name,
                    temperature=0.3,
                    max_tokens=_agent_max_tokens(agent_id),
                ),
                timeout=180,
            )

            # Update task with result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = response
            task.updated_at = datetime.utcnow()

            # Update agent state
            agent_state.status = AgentStatus.IDLE
            agent_state.current_task_id = None
            agent_state.tasks_completed += 1
            agent_state.last_active = datetime.utcnow()
            _persist_hermes(self)

            logger.info(f"Agent '{agent.name}' completed task: {task.title}")

            return {
                "status": "completed",
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_name": agent.name,
                "output": response,
                "completed_at": task.completed_at.isoformat(),
            }

        except Exception as e:
            logger.error(f"Agent '{agent.name}' failed on task: {task.title} - {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.updated_at = datetime.utcnow()

            agent_state.status = AgentStatus.ERROR
            agent_state.current_task_id = None
            agent_state.tasks_failed += 1
            agent_state.last_active = datetime.utcnow()
            _persist_hermes(self)

            return {
                "status": "failed",
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_name": agent.name,
                "error": str(e),
            }

    async def execute_project_tasks(self, project_id: str) -> dict[str, Any]:
        """Execute all pending tasks in a project, respecting dependencies.

        Returns a summary of all task execution results.
        """
        if project_id not in self.projects:
            return {"status": "error", "error": f"Project {project_id} not found"}

        project = self.projects[project_id]
        project_tasks = [t for t in self.tasks.values() if t.project_id == project_id]
        pending_tasks = [t for t in project_tasks if t.status == TaskStatus.PENDING]

        if not pending_tasks:
            return {"status": "no_tasks", "message": "No pending tasks to execute"}

        # Update project status
        project.status = ProjectStatus.IN_PROGRESS

        results = []
        executed = set()

        # Execute tasks in dependency order
        max_iterations = len(pending_tasks) * 2
        iteration = 0

        while pending_tasks and iteration < max_iterations:
            iteration += 1
            next_batch = []

            for task in pending_tasks:
                # Check if all dependencies are completed
                deps_met = all(
                    dep_id in executed
                    for dep_id in task.dependencies
                )
                if deps_met:
                    next_batch.append(task)

            if not next_batch:
                # No tasks can be executed (circular dependency or blocked)
                break

            for task in next_batch:
                result = await self.execute_task(task.id)
                results.append(result)
                executed.add(task.id)
                pending_tasks.remove(task)

        # Update project status
        completed_count = sum(1 for r in results if r.get("status") == "completed")
        failed_count = sum(1 for r in results if r.get("status") == "failed")

        if failed_count == 0 and completed_count > 0:
            project.status = ProjectStatus.TESTING
        elif failed_count > 0:
            project.status = ProjectStatus.IN_PROGRESS

        return {
            "status": "executed",
            "project_id": project_id,
            "total_tasks": len(results),
            "completed": completed_count,
            "failed": failed_count,
            "results": results,
        }

    async def chat_with_agent(
        self,
        agent_id: str,
        message: str,
        project_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Have a direct conversation with an agent.

        This allows sending a message directly to any agent without creating a task.
        """
        if agent_id not in self.agents:
            return {"status": "error", "error": f"Agent {agent_id} not found"}

        agent = self.agents[agent_id]
        agent_state = self.agent_states[agent_id]

        # Update agent status
        agent_state.status = AgentStatus.WORKING
        agent_state.last_active = datetime.utcnow()

        try:
            system_prompt = get_agent_prompt(agent_id)

            prompt_parts = [message]

            if project_id and project_id in self.projects:
                proj = self.projects[project_id]
                prompt_parts.append(f"\nContext: Project '{proj.name}' ({proj.codename}) - Tech: {', '.join(proj.tech_stack)}")

            if context:
                for key, value in context.items():
                    prompt_parts.append(f"\n{key}: {value}")

            kb_block = await self._kb_briefing("\n".join(prompt_parts))
            if kb_block:
                prompt_parts.append("\n\n" + kb_block)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(prompt_parts)},
            ]

            provider = self.llm._get_provider_for_model(agent.model_name)
            logger.info(f"Agent {agent_id} using provider={provider}, model={agent.model_name}")

            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=messages,
                    model=agent.model_name,
                    temperature=0.3,
                    max_tokens=_agent_max_tokens(agent_id),
                ),
                timeout=900,
            )

            logger.info(f"Agent {agent_id} responded ({len(response)} chars)")

            agent_state.status = AgentStatus.IDLE
            agent_state.last_active = datetime.utcnow()

            return {
                "status": "success",
                "agent_id": agent_id,
                "agent_name": agent.name,
                "response": response,
            }

        except Exception as e:
            agent_state.status = AgentStatus.ERROR
            agent_state.last_active = datetime.utcnow()
            err_msg = str(e) if str(e) else f"{type(e).__name__}: agent call timed out"
            return {
                "status": "error",
                "agent_id": agent_id,
                "agent_name": agent.name,
                "error": err_msg,
            }

    def _parse_execution_plan(self, response: str) -> dict[str, Any]:
        """Parse LLM response into a structured execution plan."""
        import json

        try:
            # Try to extract JSON from response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            logger.warning("Failed to parse execution plan as JSON, returning raw response")

        return {
            "raw_response": response,
            "tasks": [],
            "notes": "Plan requires manual review - JSON parsing failed",
        }

    async def create_project(
        self,
        name: str,
        codename: str,
        description: str,
        tech_stack: list[str] | None = None,
        user_id: str = "",
    ) -> Project:
        """Create a new project."""
        project = Project(
            name=name,
            codename=codename,
            description=description,
            tech_stack=tech_stack or [],
            user_id=user_id,
        )
        self.projects[project.id] = project
        _persist_hermes(self)
        logger.info(f"Project created: {name} ({codename})")
        return project

    async def create_task(
        self,
        title: str,
        description: str,
        project_id: str | None = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        assigned_agent_id: str | None = None,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Create a new task."""
        task = Task(
            title=title,
            description=description,
            project_id=project_id,
            priority=priority,
            assigned_agent_id=assigned_agent_id,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        self.tasks[task.id] = task

        if project_id and project_id in self.projects:
            self.projects[project_id].tasks.append(task.id)

        if assigned_agent_id:
            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.utcnow()

        _persist_hermes(self)
        logger.info(f"Task created: {title} (assigned to: {assigned_agent_id})")
        return task

    async def get_agent_status(self, agent_id: str) -> AgentState | None:
        """Get the current status of an agent."""
        return self.agent_states.get(agent_id)

    async def get_project_tasks(self, project_id: str) -> list[Task]:
        """Get all tasks for a project."""
        return [t for t in self.tasks.values() if t.project_id == project_id]

    async def get_dashboard_data(self, user_id: str = "") -> dict[str, Any]:
        """Get aggregated data for the dashboard."""
        projects = list(self.projects.values())
        if user_id:
            projects = [p for p in projects if getattr(p, "user_id", "") == user_id]
        tasks = list(self.tasks.values())
        if user_id:
            task_project_ids = {p.id for p in projects}
            tasks = [t for t in tasks if t.project_id and t.project_id in task_project_ids]
        return {
            "total_agents": len(self.agents),
            "active_agents": sum(
                1 for s in self.agent_states.values()
                if s.status == AgentStatus.WORKING
            ),
            "total_projects": len(projects),
            "active_projects": sum(
                1 for p in projects
                if p.status in (ProjectStatus.PLANNING, ProjectStatus.IN_PROGRESS)
            ),
            "total_tasks": len(tasks),
            "pending_tasks": sum(
                1 for t in tasks
                if t.status == TaskStatus.PENDING
            ),
            "completed_tasks": sum(
                1 for t in tasks
                if t.status == TaskStatus.COMPLETED
            ),
            "failed_tasks": sum(
                1 for t in tasks
                if t.status == TaskStatus.FAILED
            ),
        }
