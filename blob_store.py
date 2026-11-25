"""Archive uploaded CAS PDFs to Azure Blob Storage.

Enabled only when both ``AZURE_STORAGE_CONNECTION_STRING`` and
``AZURE_BLOB_CONTAINER`` are set; otherwise every call is a no-op.
Uploads run on a background thread pool and never fail the request:
errors are logged and swallowed. Passwords are never stored.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

log = logging.getLogger("blob_store")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="blob")
_lock = threading.Lock()
_container = None  # azure ContainerClient, created lazily


def _config() -> tuple[str, str]:
    return (
        os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip(),
        os.environ.get("AZURE_BLOB_CONTAINER", "").strip(),
    )


def enabled() -> bool:
    conn, container = _config()
    return bool(conn and container)


def safe_filename(name: str | None) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "statement"
    if not base.lower().endswith(".pdf"):
        base = base[:96] + ".pdf"
    elif len(base) > 100:
        base = base[:96] + ".pdf"
    return base


def _ascii(value: str) -> str:
    return value.encode("ascii", "replace").decode("ascii")[:256]


def blob_folder(status: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{status}/{now:%Y/%m/%d}/{now:%H%M%S}_{uuid.uuid4().hex[:8]}"


def _get_container():
    global _container
    with _lock:
        if _container is None:
            from azure.core.exceptions import ResourceExistsError
            from azure.storage.blob import BlobServiceClient

            conn, name = _config()
            client = BlobServiceClient.from_connection_string(conn).get_container_client(name)
            try:
                client.create_container()
            except ResourceExistsError:
                pass
            except Exception as exc:  # e.g. a SAS without create rights
                log.warning("Could not create container %r: %s", name, exc)
            _container = client
        return _container


def _content_settings():
    from azure.storage.blob import ContentSettings

    return ContentSettings(content_type="application/pdf")


def _upload(path: str, data: bytes, original: str, kind: str) -> None:
    try:
        _get_container().upload_blob(
            name=path,
            data=data,
            overwrite=False,
            content_settings=_content_settings(),
            metadata={"kind": kind, "original_name": _ascii(original)},
        )
        log.info("Archived %s (%d bytes)", path, len(data))
    except Exception:
        log.exception("Azure Blob upload failed for %s", path)


def save(files: list[tuple[str | None, bytes]], status: str, kind: str) -> list[str]:
    """Queue ``files`` for upload under one folder; returns the blob paths."""
    if not enabled() or not files:
        return []
    folder = blob_folder(status)
    paths: list[str] = []
    used: set[str] = set()
    for i, (original, data) in enumerate(files):
        name = safe_filename(original)
        if name in used:
            name = f"{i + 1}_{name}"
        used.add(name)
        path = f"{folder}/{name}"
        paths.append(path)
        try:
            _executor.submit(_upload, path, data, original or name, kind)
        except Exception:
            log.exception("Could not queue Azure Blob upload for %s", path)
    return paths
