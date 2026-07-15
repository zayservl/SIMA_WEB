"""Сессионное хранилище результатов рельефа.

Абстракция Storage (готова к S3-реализации при обёртке в backend-сервис) +
LocalFSStorage для тестов/Jupyter. Layout:
    results/<project>/relief/session-<id>/<tile_id>/...
Повторный запуск тайла → новый tile_id (не перезаписывает, REFINEMENT_PLAN Г1).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


class Storage(Protocol):
    """Абстракция хранилища артефактов (FS сейчас, S3 позже)."""

    def tile_dir(self, project_id: str, session_id: str, tile_id: str) -> str: ...

    def session_dir(self, project_id: str, session_id: str) -> str: ...

    def ensure_dir(self, path: str) -> str: ...

    def list_artifacts(self, tile_dir: str) -> list[str]: ...

    def artifact_size(self, path: str) -> Optional[int]: ...

    def remove(self, path: str) -> None: ...


def _new_id(prefix: str) -> str:
    """Детерминированно-уникальный id без Math.random/Date.now.

    Использует счётчик + os.urandom для уникальности; для воспроизводимых тестов
    caller может передать явный session_id/tile_id.
    """
    import secrets
    return f"{prefix}-{secrets.token_hex(6)}"


class LocalFSStorage:
    """Локальная FS-реализация Storage."""

    def __init__(self, root: str) -> None:
        self.root = str(root)

    def _abs(self, *parts: str) -> str:
        p = os.path.join(self.root, *parts) if parts else self.root
        os.makedirs(p, exist_ok=True)
        return p

    def session_dir(self, project_id: str, session_id: str) -> str:
        return self._abs(project_id, "relief", f"session-{session_id}")

    def tile_dir(self, project_id: str, session_id: str, tile_id: str) -> str:
        return self._abs(project_id, "relief", f"session-{session_id}", tile_id)

    def ensure_dir(self, path: str) -> str:
        os.makedirs(path, exist_ok=True)
        return path

    def list_artifacts(self, tile_dir: str) -> list[str]:
        if not os.path.isdir(tile_dir):
            return []
        return sorted(
            os.path.join(tile_dir, f)
            for f in os.listdir(tile_dir)
            if os.path.isfile(os.path.join(tile_dir, f))
        )

    def artifact_size(self, path: str) -> Optional[int]:
        try:
            return os.path.getsize(path)
        except OSError:
            return None

    def remove(self, path: str) -> None:
        try:
            os.remove(path)
        except IsADirectoryError:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


@dataclass
class Session:
    """Контекст сессии хранения."""
    project_id: str
    session_id: str
    root: str  # корневой каталог сессии (results/<project>/relief/session-<id>)

    @classmethod
    def new(cls, storage: Storage, project_id: str, session_id: Optional[str] = None) -> "Session":
        sid = session_id or _new_id("s")
        root = storage.session_dir(project_id, sid)
        return cls(project_id=project_id, session_id=sid, root=root)

    def tile_root(self, storage: Storage, tile_id: str) -> str:
        return storage.tile_dir(self.project_id, self.session_id, tile_id)