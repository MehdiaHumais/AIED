"""Layer 1 - CEO Agent.

The CEO is the client-facing first point of contact. The CEO:
1. Listens to the client's project request
2. Asks clarifying questions
3. Summarizes the plan
4. When the client says "start" / "build" / "go", forwards the request to Layer 2 (Workflow Engine)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CEOMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user" | "assistant"
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    action: Optional[str] = None  # "forwarded_to_layer2" | "sent_to_dev_team" | None
    task_id: Optional[str] = None  # pipeline task id when sent to dev team


class CEOConversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str = ""
    project_name: str = ""
    messages: list[CEOMessage] = Field(default_factory=list)
    status: str = "active"  # "active" | "forwarded" | "completed"
    workflow_run_id: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ceo")
_DATA_FILE = os.path.join(_DATA_DIR, "conversations.json")

_SYSTEM_PROMPT_TEMPLATE = """You are the CEO of {company_name}.

## ABOUT THE COMPANY

{company_info}

## YOUR ROLE

You are the FIRST point of contact for every client.
- You listen to what the client wants to build
- You ask smart clarifying questions to understand their vision
- You summarize the plan back to them
- You hand off to the right team based on what the client needs

## RULES — READ CAREFULLY

1. FIRST MESSAGE ONLY: Greet the client briefly and ask what they want to build. Do NOT dump company info, project lists, or tech stacks. Just say hi and ask about their idea.
2. SUBSEQUENT MESSAGES: Focus ONLY on what the client is asking. Do NOT repeat company information, project lists, or capabilities unless the client specifically asks.
3. If the client's idea relates to an existing company project, briefly mention it ONCE — then move on to their idea.
4. NEVER start a response with "Welcome to {company_name}" or a company pitch unless it is the very first message in the conversation.
5. Plain text only — do NOT use markdown formatting like **, #, *, _, `, or any special characters.

## GATHERING REQUIREMENTS BEFORE HANDOFF

Your job is to understand what the client wants and hand it off QUICKLY. Do NOT over-ask or annoy the client with too many questions.

RULES:
- If the client tells you what to do, JUST DO IT. Hand off immediately.
- Only ask clarifying questions when the request is TRULY vague — like "fix the thing" with zero context.
- If the client says "fix build errors", "analyze and solve issues", "update the project", or any similar clear instruction — that is ENOUGH. Hand off NOW.
- The development team has their own agents to analyze, investigate, and solve problems. You do NOT need to ask the client for error messages or technical details. The team will figure it out.
- NEVER ask for error messages, logs, or technical details. The dev team handles that.
- NEVER ask "which project" if the client already mentioned a project name or if there is only one project in context.
- The ONLY time you ask a question is when you genuinely cannot tell WHAT to build or WHICH project. If you can tell, just proceed.

When you hand off, summarize what the client wants in 2-3 sentences so the team knows what to do.

## TWO WAYS TO HAND OFF

You have TWO different actions depending on what the client wants:

### OPTION A — Send to Executive Board & Layers (Full Pipeline)
Use this when the client wants to BUILD A NEW PROJECT from scratch.
Trigger phrases: "send to layers", "start building", "go ahead", "lets go", "send to the team", "kick off", "begin development", "proceed", "ship it", "do it", "make it happen", "start now", "forward to engineering", "approve the plan"

When triggered, include this EXACT marker:
[ACTION:START_BUILD]

### OPTION B — Send Directly to Development Team (Quick Fix/Update)
Use this when the client wants to FIX, UPDATE, or ADD FEATURES to an EXISTING project and wants it done FAST without going through the full review pipeline.
Trigger phrases: "fix this project", "update this", "add this to the project", "send to dev team", "direct to developers", "quick fix", "just fix it", "send to development", "have the team fix this", "modify the project"

When triggered, include this EXACT marker:
[ACTION:SEND_TO_DEV]

## IMPORTANT
- For NEW projects → use OPTION A (START_BUILD)
- For FIXES/UPDATES to existing projects → use OPTION B (SEND_TO_DEV)
- The system detects these markers automatically. You do NOT need to ask for confirmation — just include the marker and confirm what will happen.

Keep responses concise — 2-4 paragraphs max unless the client asks for detail.
Never make up technical details you don't know. If the client hasn't specified something, ask.
"""


class CEOAgent:
    """Layer 1 CEO - Client-facing conversational agent."""

    def __init__(self, llm_manager, data_file: str | None = None, company_store=None, ekdt_store=None):
        self.llm = llm_manager
        self.conversations: dict[str, CEOConversation] = {}
        self._data_file = data_file or _DATA_FILE
        self._company = company_store
        self._ekdt = ekdt_store
        self._load()

    def _load(self):
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("conversations", []):
                conv = CEOConversation.model_validate(raw)
                self.conversations[conv.id] = conv
        except Exception:
            pass

    def persist(self):
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump(
                {"conversations": [c.model_dump() for c in self.conversations.values()]},
                f, ensure_ascii=False, indent=2,
            )

    def list_conversations(self) -> list[dict]:
        return [
            {
                "id": c.id,
                "client_name": c.client_name,
                "project_name": c.project_name,
                "status": c.status,
                "message_count": len(c.messages),
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "workflow_run_id": c.workflow_run_id,
            }
            for c in sorted(self.conversations.values(), key=lambda x: x.updated_at, reverse=True)
        ]

    def get_conversation(self, conv_id: str) -> CEOConversation | None:
        return self.conversations.get(conv_id)

    def delete_conversation(self, conv_id: str) -> bool:
        if conv_id in self.conversations:
            del self.conversations[conv_id]
            self.persist()
            return True
        return False

    def rename_conversation(self, conv_id: str, project_name: str) -> bool:
        conv = self.conversations.get(conv_id)
        if not conv:
            return False
        conv.project_name = project_name
        self.persist()
        return True

    def create_conversation(self, client_name: str = "", project_name: str = "") -> CEOConversation:
        conv = CEOConversation(client_name=client_name, project_name=project_name)
        self.conversations[conv.id] = conv
        self.persist()
        return conv

    async def chat(self, conv_id: str, message: str) -> dict[str, Any]:
        """Send a message to the CEO. Returns the CEO's response and whether build was started."""
        conv = self.conversations.get(conv_id)
        if not conv:
            return {"error": "Conversation not found"}

        user_msg = CEOMessage(role="user", content=message)
        conv.messages.append(user_msg)

        # Build system prompt with company info from Layer 0
        company_name = "the company"
        company_info = ""
        project_context = ""

        if self._company:
            try:
                company_name = self._company.data.profile.name or "the company"
                company_info = self._company.get_all_text()
            except Exception:
                pass

        # If user is asking about a specific project, look it up
        if self._company and message:
            project_match = self._company.find_project_by_name(message)
            if project_match:
                project_context = (
                    f"\n\n## Client is asking about project: {project_match.name}\n"
                    f"Description: {project_match.description}\n"
                    f"Status: {project_match.status}\n"
                    f"Tech: {project_match.tech_stack}\n"
                    f"Deployed at: {project_match.deployment_url}\n"
                    f"Folder: {project_match.folder_path}\n"
                )

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            company_name=company_name,
            company_info=company_info + project_context,
        )

        # Build conversation history for the LLM
        history = [{"role": "system", "content": system_prompt}]
        for msg in conv.messages[-20:]:
            history.append({"role": msg.role, "content": msg.content})

        try:
            response = await self.llm.chat(history)
        except Exception as e:
            return {"error": f"CEO agent error: {e}"}

        # Strip any markdown formatting the LLM might still produce
        import re
        response = re.sub(r'\*\*(.+?)\*\*', r'\1', response)  # **bold** -> bold
        response = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', response)  # *italic* -> italic
        response = re.sub(r'^#{1,6}\s+', '', response, flags=re.MULTILINE)  # headings
        response = re.sub(r'`(.+?)`', r'\1', response)  # inline code
        response = re.sub(r'```[\s\S]*?```', '', response)  # code blocks

        # Detect if the CEO decided to start building by checking its response for the marker
        # Also fallback: check user message for clear build intent phrases
        start_build = "[ACTION:START_BUILD]" in response
        send_to_dev = "[ACTION:SEND_TO_DEV]" in response

        if not start_build and not send_to_dev:
            # Fallback: if user explicitly asks to send/proceed, force the build
            low_msg = message.lower().strip()
            _BUILD_TRIGGERS = [
                "send to layer", "send to the team", "send to engineering",
                "go ahead", "lets go", "let's go", "start building",
                "start the work", "begin building", "proceed", "do it",
                "ship it", "make it happen", "green light", "start now",
                "im ready", "i'm ready", "kick off", "forward to",
                "send it", "execute", "commence", "start development",
            ]
            _DEV_TRIGGERS = [
                "fix this project", "update this project", "add to the project",
                "send to dev team", "direct to dev", "quick fix", "just fix it",
                "send to development", "have the team fix", "modify the project",
                "fix the project", "update the project", "add features to",
                "send to devs", "direct to developers", "send to dev",
            ]
            # Broader intent detection: if user mentions a path OR fix/intent words
            _has_drive_path = bool(re.search(r'[A-Z]:[/\\]', message))
            _has_unix_path = bool(re.search(r'/(?:home|usr|var|opt|tmp|etc|sir|Users)', message))
            _has_path = _has_drive_path or _has_unix_path
            _fix_words = ["issue", "issues", "bug", "bugs", "error", "errors",
                          "problem", "problems", "fix", "broken", "crash",
                          "not working", "doesn't work", "doesnt work",
                          "failed", "failure", "wrong", "solve"]
            _update_words = ["update", "upgrade", "change", "modify", "add",
                             "remove", "delete", "improve", "refactor",
                             "build error", "build issue", "build fail"]
            _has_fix_intent = any(w in low_msg for w in _fix_words)
            _has_update_intent = any(w in low_msg for w in _update_words)

            if any(phrase in low_msg for phrase in _BUILD_TRIGGERS):
                start_build = True
                response += "\n\n" + "[ACTION:START_BUILD]"
            elif any(phrase in low_msg for phrase in _DEV_TRIGGERS):
                send_to_dev = True
                response += "\n\n" + "[ACTION:SEND_TO_DEV]"
            elif _has_path and (_has_fix_intent or _has_update_intent):
                # User gave a path + intent words -> auto send to dev
                send_to_dev = True
                response += "\n\n" + "[ACTION:SEND_TO_DEV]"
            elif _has_fix_intent and len(low_msg.split()) <= 15:
                # Short message with fix intent -> likely wants the team to handle it
                send_to_dev = True
                response += "\n\n" + "[ACTION:SEND_TO_DEV]"

        action = None
        workflow_run_id = None
        dev_team_task_id = None

        if start_build:
            response = response.replace("[ACTION:START_BUILD]", "").strip()
            action = "forwarded_to_layer2"
            conv.status = "forwarded"
            workflow_run_id = f"pending-{conv.id}"

        elif send_to_dev:
            response = response.replace("[ACTION:SEND_TO_DEV]", "").strip()
            action = "sent_to_dev_team"
            conv.status = "forwarded"
            dev_team_task_id = f"pending-dev-{conv.id}"

        assistant_msg = CEOMessage(role="assistant", content=response, action=action)
        conv.messages.append(assistant_msg)
        conv.updated_at = datetime.utcnow().isoformat() + "Z"
        self.persist()

        return {
            "response": response,
            "action": action,
            "workflow_run_id": workflow_run_id,
            "dev_team_task_id": dev_team_task_id,
            "conversation_status": conv.status,
        }

    async def _build_project_description(self, conv: CEOConversation) -> str:
        """Use the LLM to summarize the conversation into a clean project brief for Layer 2."""
        # Build the full conversation transcript
        transcript = []
        for msg in conv.messages:
            role = "Client" if msg.role == "user" else "CEO"
            transcript.append(f"{role}: {msg.content}")
        full_transcript = "\n".join(transcript)

        summary_prompt = [
            {"role": "system", "content": (
                "You are the CEO summarizing a client conversation into a clean project brief "
                "for the engineering team. Extract the key requirements, features, tech stack, "
                "and constraints. Be specific and actionable. Do NOT include conversation filler. "
                "Output a structured brief with: Project Name, Description, Key Features, "
                "Tech Stack (if mentioned), and any Constraints or Notes."
            )},
            {"role": "user", "content": f"Summarize this conversation into a project brief:\n\n{full_transcript}"},
        ]
        try:
            brief = await self.llm.chat(summary_prompt)
            return brief
        except Exception:
            # Fallback: just use the user messages
            parts = [msg.content for msg in conv.messages if msg.role == "user"]
            return "\n\n".join(parts)

    async def _forward_to_layer2(self, project_description: str, conv: CEOConversation) -> str:
        """Forward the project request to Layer 2 (Workflow Engine)."""
        # The workflow engine will be accessed via app_state in the API layer.
        # Store the request for the API to pick up.
        conv.context["pending_workflow_request"] = project_description
        self.persist()
        return f"pending-{conv.id}"

    async def _forward_to_dev_team(self, project_description: str, conv: CEOConversation) -> str:
        """Forward the request directly to the dev team (skip layers)."""
        conv.context["pending_dev_team_request"] = project_description
        self.persist()
        return f"pending-dev-{conv.id}"
