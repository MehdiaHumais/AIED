"""Docker Tool - Container and image management."""

from __future__ import annotations

import logging
from typing import Any

import docker

logger = logging.getLogger(__name__)


class DockerTool:
    """Docker operations for building and managing containers."""

    def __init__(self) -> None:
        self.client: docker.DockerClient | None = None

    def initialize(self) -> None:
        """Initialize Docker client."""
        try:
            self.client = docker.from_env()
            logger.info("Docker client initialized")
        except docker.errors.DockerException as e:
            logger.warning(f"Docker not available: {e}")

    def close(self) -> None:
        """Close Docker client."""
        if self.client:
            self.client.close()

    def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
    ) -> dict[str, Any]:
        """Build a Docker image."""
        if not self.client:
            raise RuntimeError("Docker not initialized")

        try:
            image, build_logs = self.client.images.build(
                path=path,
                tag=tag,
                dockerfile=dockerfile,
            )
            return {
                "success": True,
                "image_id": image.id,
                "tags": image.tags,
            }
        except docker.errors.BuildError as e:
            return {
                "success": False,
                "error": str(e),
            }

    def run_container(
        self,
        image: str,
        name: str,
        ports: dict[str, str] | None = None,
        environment: dict[str, str] | None = None,
        detach: bool = True,
    ) -> dict[str, Any]:
        """Run a Docker container."""
        if not self.client:
            raise RuntimeError("Docker not initialized")

        try:
            container = self.client.containers.run(
                image=image,
                name=name,
                ports=ports or {},
                environment=environment or {},
                detach=detach,
            )
            return {
                "success": True,
                "container_id": container.id,
                "name": container.name,
                "status": container.status,
            }
        except docker.errors.ContainerError as e:
            return {
                "success": False,
                "error": str(e),
            }

    def list_containers(self, all: bool = True) -> list[dict[str, Any]]:
        """List running containers."""
        if not self.client:
            return []

        containers = self.client.containers.list(all=all)
        return [
            {
                "id": c.id[:12],
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:12],
            }
            for c in containers
        ]

    def stop_container(self, container_id: str) -> bool:
        """Stop a container."""
        if not self.client:
            return False
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            return True
        except docker.errors.NotFound:
            return False

    def remove_container(self, container_id: str, force: bool = False) -> bool:
        """Remove a container."""
        if not self.client:
            return False
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
            return True
        except docker.errors.NotFound:
            return False

    def list_images(self) -> list[dict[str, Any]]:
        """List Docker images."""
        if not self.client:
            return []

        images = self.client.images.list()
        return [
            {
                "id": img.id[:12],
                "tags": img.tags,
                "size": img.attrs["Size"],
            }
            for img in images
        ]
