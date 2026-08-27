"""
AIED Local Agent Communication Server
WebSocket server that manages connections from Local Agents running on user PCs.
VPS sends commands to agents, agents execute locally and report back.
"""

import asyncio
import json
import time
import uuid
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect


class AgentConnection:
    """Represents a connected Local Agent."""

    def __init__(self, user_id: str, ws: WebSocket, token: str):
        self.user_id = user_id
        self.ws = ws
        self.token = token
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.project_folder = ""
        self.platform = ""
        self.python_version = ""
        self.agent_version = ""
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def send_command(self, command: str, params: dict, timeout: float = 120) -> dict:
        """Send a command to the local agent and wait for the result."""
        cmd_id = str(uuid.uuid4())[:8]
        future = asyncio.get_event_loop().create_future()

        async with self._lock:
            self._pending[cmd_id] = future

        msg = {
            "type": "command",
            "command_id": cmd_id,
            "command": command,
            "params": params,
        }

        try:
            await self.ws.send_json(msg)
        except Exception as e:
            async with self._lock:
                self._pending.pop(cmd_id, None)
            return {"success": False, "error": f"Failed to send command: {e}"}

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            async with self._lock:
                self._pending.pop(cmd_id, None)
            return {"success": False, "error": f"Agent did not respond within {timeout}s"}

    def resolve_result(self, cmd_id: str, result: dict):
        """Resolve a pending command with its result."""
        future = self._pending.get(cmd_id)
        if future and not future.done():
            future.set_result(result)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "connected": True,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "project_folder": self.project_folder,
            "platform": self.platform,
            "agent_version": self.agent_version,
        }


class AgentManager:
    """Manages all connected Local Agents."""

    def __init__(self):
        self.agents: dict[str, AgentConnection] = {}
        self._tokens: dict[str, str] = {}  # token -> user_id

    def register_token(self, token: str, user_id: str):
        """Register an auth token for a user."""
        self._tokens[token] = user_id

    def get_user_id_for_token(self, token: str) -> Optional[str]:
        return self._tokens.get(token)

    def connect(self, user_id: str, ws: WebSocket, token: str) -> AgentConnection:
        agent = AgentConnection(user_id, ws, token)
        self.agents[user_id] = agent
        return agent

    def disconnect(self, user_id: str):
        self.agents.pop(user_id, None)

    def get_agent(self, user_id: str) -> Optional[AgentConnection]:
        agent = self.agents.get(user_id)
        if agent:
            agent.last_seen = time.time()
        return agent

    def is_connected(self, user_id: str) -> bool:
        return user_id in self.agents

    def get_all_status(self) -> list[dict]:
        return [a.to_dict() for a in self.agents.values()]

    async def write_file(self, user_id: str, path: str, content: str, project_folder: str = "") -> dict:
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        params = {"path": path, "content": content}
        if project_folder:
            params["project_folder"] = project_folder
        return await agent.send_command("write_file", params)

    async def delete_file(self, user_id: str, path: str, project_folder: str = "") -> dict:
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        params = {"path": path}
        if project_folder:
            params["project_folder"] = project_folder
        return await agent.send_command("delete_file", params)

    async def read_file(self, user_id: str, path: str, project_folder: str = "") -> dict:
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        params = {"path": path}
        if project_folder:
            params["project_folder"] = project_folder
        return await agent.send_command("read_file", params)

    async def list_files(self, user_id: str, path: str = "", project_folder: str = "") -> dict:
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        params = {"path": path}
        if project_folder:
            params["project_folder"] = project_folder
        return await agent.send_command("list_files", params)

    async def read_tree(self, user_id: str, project_folder: str = "") -> dict:
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        params = {}
        if project_folder:
            params["project_folder"] = project_folder
        return await agent.send_command("read_tree", params)

    async def run_command(self, user_id: str, command: str, timeout: int = 120, env: dict = None, project_folder: str = "") -> dict:
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        params = {"command": command, "timeout": timeout}
        if env:
            params["env"] = env
        if project_folder:
            params["project_folder"] = project_folder
        return await agent.send_command("run_command", params, timeout=timeout + 10)

    async def update_project_folder(self, user_id: str, folder: str) -> dict:
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        try:
            await agent.ws.send_json({
                "type": "config_update",
                "config": {"project_folder": folder},
            })
            agent.project_folder = folder
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def select_folder(self, user_id: str) -> dict:
        """Ask the Local Agent to open a native folder picker on the user's machine."""
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        return await agent.send_command("select_folder", {}, timeout=180)

    async def list_root_folders(self, user_id: str) -> dict:
        """Ask the Local Agent to list drives/folders on the user's machine."""
        agent = self.get_agent(user_id)
        if not agent:
            return {"success": False, "error": "Local Agent not connected"}
        return await agent.send_command("list_root_folders", {}, timeout=30)

    def handle_message(self, user_id: str, msg: dict):
        msg_type = msg.get("type", "")

        if msg_type == "command_result":
            cmd_id = msg.get("command_id", "")
            agent = self.get_agent(user_id)
            if agent:
                agent.resolve_result(cmd_id, msg)

        elif msg_type == "status":
            agent = self.get_agent(user_id)
            if agent:
                agent.project_folder = msg.get("project_folder", "")
                agent.platform = msg.get("platform", "")
                agent.python_version = msg.get("python_version", "")
                agent.agent_version = msg.get("agent_version", "")
                agent.last_seen = time.time()

        elif msg_type == "pong":
            agent = self.get_agent(user_id)
            if agent:
                agent.last_seen = time.time()


agent_manager = AgentManager()
