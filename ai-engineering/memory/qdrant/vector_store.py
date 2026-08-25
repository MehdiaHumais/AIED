"""Qdrant Vector Memory Layer - Documentation, Knowledge, Code Embeddings."""

from __future__ import annotations

import logging
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from shared.config import QdrantConfig

logger = logging.getLogger(__name__)


class VectorStore:
    """Qdrant vector store for semantic search and memory."""

    # Collection names
    COLLECTION_DOCS = "aied_documentation"
    COLLECTION_CODE = "aied_code_embeddings"
    COLLECTION_KNOWLEDGE = "aied_knowledge"
    COLLECTION_PROJECTS = "aied_project_memory"

    def __init__(self, config: QdrantConfig) -> None:
        self.config = config
        self.client: QdrantClient | None = None

    async def initialize(self) -> None:
        """Initialize Qdrant client and create collections."""
        self.client = QdrantClient(
            url=self.config.url,
            api_key=self.config.api_key or None,
        )

        # Create collections if they don't exist
        collections = [
            (self.COLLECTION_DOCS, 1536),
            (self.COLLECTION_CODE, 1536),
            (self.COLLECTION_KNOWLEDGE, 1536),
            (self.COLLECTION_PROJECTS, 1536),
        ]

        existing = [c.name for c in self.client.get_collections().collections]

        for name, size in collections:
            if name not in existing:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=size, distance=Distance.COSINE),
                )
                logger.info(f"Created Qdrant collection: {name}")

        logger.info("Qdrant vector store initialized")

    async def close(self) -> None:
        """Close Qdrant client."""
        if self.client:
            self.client.close()

    async def upsert_points(
        self,
        collection: str,
        points: list[dict[str, Any]],
    ) -> None:
        """Upsert vector points into a collection."""
        if not self.client:
            raise RuntimeError("Qdrant not initialized")

        qdrant_points = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {}),
            )
            for p in points
        ]
        self.client.upsert(collection_name=collection, points=qdrant_points)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors."""
        if not self.client:
            raise RuntimeError("Qdrant not initialized")

        query_filter = None
        if filter_conditions:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_conditions.items()
            ]
            query_filter = Filter(must=conditions)

        results = self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results
        ]

    async def delete_points(
        self,
        collection: str,
        point_ids: list[str],
    ) -> None:
        """Delete points by ID."""
        if not self.client:
            return
        self.client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=point_ids),
        )

    # --- Documentation ---

    async def store_documentation(
        self,
        doc_id: str,
        content: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store documentation with embedding."""
        await self.upsert_points(
            self.COLLECTION_DOCS,
            [{
                "id": doc_id,
                "vector": embedding,
                "payload": {
                    "content": content,
                    **(metadata or {}),
                },
            }],
        )

    async def search_documentation(
        self,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search documentation by semantic similarity."""
        return await self.search(self.COLLECTION_DOCS, query_embedding, limit)

    # --- Code Embeddings ---

    async def store_code_embedding(
        self,
        code_id: str,
        code: str,
        embedding: list[float],
        file_path: str,
        language: str,
    ) -> None:
        """Store code embedding."""
        await self.upsert_points(
            self.COLLECTION_CODE,
            [{
                "id": code_id,
                "vector": embedding,
                "payload": {
                    "code": code,
                    "file_path": file_path,
                    "language": language,
                },
            }],
        )

    async def search_code(
        self,
        query_embedding: list[float],
        limit: int = 5,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search code by semantic similarity."""
        filters = {"language": language} if language else None
        return await self.search(self.COLLECTION_CODE, query_embedding, limit, filters)

    # --- Company Knowledge ---

    async def store_knowledge(
        self,
        knowledge_id: str,
        content: str,
        embedding: list[float],
        category: str,
        tags: list[str] | None = None,
    ) -> None:
        """Store company knowledge."""
        await self.upsert_points(
            self.COLLECTION_KNOWLEDGE,
            [{
                "id": knowledge_id,
                "vector": embedding,
                "payload": {
                    "content": content,
                    "category": category,
                    "tags": tags or [],
                },
            }],
        )

    async def search_knowledge(
        self,
        query_embedding: list[float],
        limit: int = 5,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search company knowledge."""
        filters = {"category": category} if category else None
        return await self.search(self.COLLECTION_KNOWLEDGE, query_embedding, limit, filters)

    # --- Project Memory ---

    async def store_project_memory(
        self,
        memory_id: str,
        content: str,
        embedding: list[float],
        project_id: str,
        memory_type: str,
    ) -> None:
        """Store project-specific memory."""
        await self.upsert_points(
            self.COLLECTION_PROJECTS,
            [{
                "id": memory_id,
                "vector": embedding,
                "payload": {
                    "content": content,
                    "project_id": project_id,
                    "memory_type": memory_type,
                },
            }],
        )

    async def search_project_memory(
        self,
        query_embedding: list[float],
        project_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search project-specific memory."""
        return await self.search(
            self.COLLECTION_PROJECTS,
            query_embedding,
            limit,
            {"project_id": project_id},
        )
