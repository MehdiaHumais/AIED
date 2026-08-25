"""Redis Memory Layer - Queue, Cache, Sessions, Running Agents."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from shared.config import RedisConfig

logger = logging.getLogger(__name__)


class RedisStore:
    """Redis store for queues, cache, and sessions."""

    def __init__(self, config: RedisConfig) -> None:
        self.config = config
        self.client: aioredis.Redis | None = None

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        self.client = aioredis.from_url(
            self.config.url,
            max_connections=self.config.max_connections,
            decode_responses=True,
        )
        logger.info("Redis store initialized")

    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()

    # --- Queue Operations ---

    async def enqueue_task(
        self,
        queue_name: str,
        task_data: dict[str, Any],
        priority: int = 0,
    ) -> str:
        """Add a task to a priority queue."""
        if not self.client:
            raise RuntimeError("Redis not initialized")

        task_id = task_data.get("id", "")
        data = json.dumps(task_data)

        # Use sorted set for priority queue (lower score = higher priority)
        await self.client.zadd(f"queue:{queue_name}", {data: priority})
        logger.info(f"Task {task_id} enqueued to {queue_name} with priority {priority}")
        return task_id

    async def dequeue_task(self, queue_name: str) -> dict[str, Any] | None:
        """Get the highest priority task from a queue."""
        if not self.client:
            raise RuntimeError("Redis not initialized")

        # Get the task with lowest score (highest priority)
        results = await self.client.zpopmin(f"queue:{queue_name}", count=1)
        if results:
            data, _ = results[0]
            return json.loads(data)
        return None

    async def get_queue_length(self, queue_name: str) -> int:
        """Get the number of tasks in a queue."""
        if not self.client:
            return 0
        return await self.client.zcard(f"queue:{queue_name}")

    async def peek_queue(self, queue_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Preview tasks in a queue without removing them."""
        if not self.client:
            return []

        results = await self.client.zrange(f"queue:{queue_name}", 0, limit - 1, withscores=True)
        return [{"task": json.loads(data), "priority": score} for data, score in results]

    # --- Cache Operations ---

    async def cache_set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 3600,
    ) -> None:
        """Set a cached value with TTL."""
        if not self.client:
            return
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await self.client.setex(f"cache:{key}", ttl_seconds, serialized)

    async def cache_get(self, key: str) -> Any | None:
        """Get a cached value."""
        if not self.client:
            return None
        value = await self.client.get(f"cache:{key}")
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def cache_delete(self, key: str) -> None:
        """Delete a cached value."""
        if not self.client:
            return
        await self.client.delete(f"cache:{key}")

    # --- Session Operations ---

    async def create_session(
        self,
        session_id: str,
        data: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None:
        """Create a session."""
        if not self.client:
            return
        await self.client.setex(
            f"session:{session_id}",
            ttl_seconds,
            json.dumps(data),
        )

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session data."""
        if not self.client:
            return None
        data = await self.client.get(f"session:{session_id}")
        return json.loads(data) if data else None

    async def update_session(self, session_id: str, updates: dict[str, Any]) -> None:
        """Update session data."""
        data = await self.get_session(session_id)
        if data:
            data.update(updates)
            await self.client.setex(
                f"session:{session_id}",
                86400,
                json.dumps(data),
            )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        if not self.client:
            return
        await self.client.delete(f"session:{session_id}")

    # --- Running Agents ---

    async def set_agent_running(
        self,
        agent_id: str,
        task_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mark an agent as running a task."""
        if not self.client:
            return
        data = {
            "agent_id": agent_id,
            "task_id": task_id,
            "metadata": metadata or {},
        }
        await self.client.hset("agents:running", agent_id, json.dumps(data))

    async def set_agent_idle(self, agent_id: str) -> None:
        """Mark an agent as idle."""
        if not self.client:
            return
        await self.client.hdel("agents:running", agent_id)

    async def get_running_agents(self) -> dict[str, dict[str, Any]]:
        """Get all currently running agents."""
        if not self.client:
            return {}
        data = await self.client.hgetall("agents:running")
        return {k: json.loads(v) for k, v in data.items()}

    async def is_agent_running(self, agent_id: str) -> bool:
        """Check if an agent is currently running."""
        if not self.client:
            return False
        return await self.client.hexists("agents:running", agent_id)

    # --- Pub/Sub for Real-time Updates ---

    async def publish_event(self, channel: str, event: dict[str, Any]) -> None:
        """Publish an event to a channel."""
        if not self.client:
            return
        await self.client.publish(channel, json.dumps(event))

    async def subscribe_events(self, *channels: str) -> Any:
        """Subscribe to event channels."""
        if not self.client:
            return None
        pubsub = self.client.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub
