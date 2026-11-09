"""Authenticated encryption for bounded files and JSON. Development keys stay local."""
import base64
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from cryptography.fernet import Fernet
from app.core.config import settings


@lru_cache(maxsize=8)
def key_bytes(root: str, configured_key: str | None, environment: str):
    if configured_key:
        key = configured_key.encode()
    elif environment != "development":
        raise RuntimeError("ENCRYPTION_KEY is required outside development")
    else:
        directory = Path(root).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        key_path = directory / ".development-key"
        try:
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            key = key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(key)
    Fernet(key)  # Validate before serving requests.
    return key


def vault():
    return Fernet(key_bytes(str(settings.storage_dir), settings.encryption_key, settings.environment))


def signing_key():
    return hashlib.sha256(b"health-auth-v1:" + base64.urlsafe_b64decode(
        key_bytes(str(settings.storage_dir), settings.encryption_key, settings.environment))).digest()


def seal(data):
    return vault().encrypt(json.dumps(data, ensure_ascii=False, allow_nan=False).encode()).decode()


def unseal(data):
    return json.loads(vault().decrypt(data.encode()))


def blob_path(document_id):
    from uuid import UUID
    normalized = str(UUID(document_id))
    root = settings.storage_dir.resolve() / "documents"
    root.mkdir(parents=True, exist_ok=True)
    return root / (normalized + ".enc")
