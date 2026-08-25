"""Secure SSH connection layer for VPS deployments."""

from __future__ import annotations

import asyncio
import base64
import io
import os
import socket
import threading
import time
from typing import Any, Optional

from cryptography.fernet import Fernet
import paramiko

from deployment.models import VPSServer, AuthMethod

# Encryption key - generated once, stored in env or file
_ENCRYPTION_KEY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", ".deploy_key")


def _get_or_create_key() -> bytes:
    """Get or create encryption key for credentials."""
    key_path = os.path.abspath(_ENCRYPTION_KEY_FILE)
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
    return key


_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_get_or_create_key())
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret value."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a secret value."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def mask_secret(value: str, show_chars: int = 4) -> str:
    """Mask a secret for display."""
    if not value or len(value) <= show_chars * 2:
        return "****"
    return value[:show_chars] + "*" * (len(value) - show_chars * 2) + value[-show_chars:]


class SSHConnection:
    """Managed SSH connection to a VPS."""

    def __init__(self, server: VPSServer, log_callback=None):
        self.server = server
        self.client: Optional[paramiko.SSHClient] = None
        self.log = log_callback or (lambda msg, **kw: None)
        self._connected = False
        self._lock = threading.Lock()
        self._password: Optional[str] = None  # Decrypted password for sudo

    async def connect(self, timeout: int = 30) -> bool:
        """Establish SSH connection."""
        self.log(f"Connecting to {self.server.host}:{self.server.port} as {self.server.username}...", severity="info")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict[str, Any] = {
            "hostname": self.server.host,
            "port": self.server.port,
            "username": self.server.username,
            "timeout": timeout,
            "banner_timeout": timeout,
            "auth_timeout": timeout,
        }

        if self.server.auth_method == AuthMethod.SSH_KEY and self.server.encrypted_private_key:
            try:
                private_key_str = decrypt_secret(self.server.encrypted_private_key)
                pkey = paramiko.RSAKey.from_private_key(io.StringIO(private_key_str))
                connect_kwargs["pkey"] = pkey
            except Exception as e:
                self.log(f"Failed to parse SSH key: {e}", severity="error")
                raise

        elif self.server.auth_method == AuthMethod.PASSWORD and self.server.encrypted_password:
            connect_kwargs["password"] = decrypt_secret(self.server.encrypted_password)

        # Always store password for sudo use (regardless of auth method)
        if self.server.encrypted_password:
            try:
                self._password = decrypt_secret(self.server.encrypted_password)
            except Exception:
                pass

        try:
            await asyncio.get_event_loop().run_in_executor(None, lambda: self.client.connect(**connect_kwargs))
            self._connected = True
            self.log(f"Connected to {self.server.host}", severity="success")
            return True
        except paramiko.AuthenticationException:
            self.log(f"Authentication failed for {self.server.username}@{self.server.host}", severity="error")
            raise
        except socket.timeout:
            self.log(f"Connection timeout to {self.server.host}:{self.server.port}", severity="error")
            raise
        except Exception as e:
            self.log(f"Connection failed: {e}", severity="error")
            raise

    def exec_command(self, command: str, timeout: int = 300, sudo: bool = False) -> dict[str, Any]:
        """Execute a command on the remote server. Returns {stdout, stderr, returncode}."""
        if not self._connected or not self.client:
            raise RuntimeError("Not connected")

        if sudo and not command.startswith("sudo "):
            command = f"sudo -n {command}"

        # Replace ALL sudo -n with sudo -S and pipe password for authentication
        if self._password and "sudo -n " in command:
            escaped_pw = self._password.replace("'", "'\\''")
            command = command.replace("sudo -n ", f"echo '{escaped_pw}' | sudo -S ")

        self.log(f"$ {command[:200]}", severity="debug")
        with self._lock:
            try:
                stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
                exit_code = stdout.channel.recv_exit_status()
                out = stdout.read().decode("utf-8", errors="replace")
                err = stderr.read().decode("utf-8", errors="replace")
                self.log(f"exit={exit_code} out={len(out)} err={len(err)}", severity="debug")
                return {"stdout": out, "stderr": err, "returncode": exit_code}
            except socket.timeout:
                self.log(f"Command timed out after {timeout}s: {command[:100]}", severity="error")
                return {"stdout": "", "stderr": "Command timed out", "returncode": -1}
            except Exception as e:
                self.log(f"Command error: {e}", severity="error")
                return {"stdout": "", "stderr": str(e), "returncode": -1}

    def exec_sudo(self, command: str, timeout: int = 300) -> dict[str, Any]:
        """Execute a command with sudo."""
        return self.exec_command(command, timeout=timeout, sudo=True)

    def read_file(self, remote_path: str) -> str:
        """Read a file from the remote server."""
        with self._lock:
            sftp = self.client.open_sftp()
            try:
                with sftp.open(remote_path, "r") as f:
                    return f.read().decode("utf-8", errors="replace")
            except FileNotFoundError:
                return ""
            finally:
                sftp.close()

    def write_file(self, remote_path: str, content: str, sudo: bool = False):
        """Write content to a file on the remote server."""
        if sudo:
            # Write to temp then move
            tmp = f"/tmp/.aied_deploy_{os.path.basename(remote_path)}"
            with self._lock:
                sftp = self.client.open_sftp()
                try:
                    with sftp.open(tmp, "w") as f:
                        f.write(content)
                finally:
                    sftp.close()
            self.exec_sudo(f"cp {tmp} {remote_path} && rm -f {tmp}")
        else:
            with self._lock:
                sftp = self.client.open_sftp()
                try:
                    with sftp.open(remote_path, "w") as f:
                        f.write(content)
                finally:
                    sftp.close()

    def disconnect(self):
        """Close the SSH connection."""
        if self.client:
            self.client.close()
            self._connected = False
            self.log(f"Disconnected from {self.server.host}", severity="info")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.disconnect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        self.disconnect()


def create_vps_server(
    host: str,
    username: str,
    port: int = 22,
    private_key: str = "",
    password: str = "",
    name: str = "",
) -> VPSServer:
    """Create a VPSServer with encrypted credentials."""
    server = VPSServer(
        name=name or host,
        host=host,
        port=port,
        username=username,
        auth_method=AuthMethod.SSH_KEY if private_key else AuthMethod.PASSWORD,
    )
    if private_key:
        server.encrypted_private_key = encrypt_secret(private_key)
    if password:
        server.encrypted_password = encrypt_secret(password)
    return server
