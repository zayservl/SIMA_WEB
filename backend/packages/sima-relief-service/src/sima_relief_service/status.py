"""Модель статусов задач/тайлов/шагов рельефа.

Зеркало контракта src/api/types.ts (Job/Tile/TileStep, статусы).
Чистые dataclass-ы: трекаются в памяти Python, готовы к сериализации/персисту
(БД/Redis) при обёртке в реальный backend-сервис. Без HTTP/Celery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --- Статусы (1:1 к src/api/types.ts) ------------------------------------

JobStatus = str  # 'queued' | 'running' | 'success' | 'failed' | 'cancelled'
TileStatus = str  # 'queued' | 'running' | 'done' | 'failed' | 'skipped'
StepStatus = str  # 'pending' | 'running' | 'done' | 'failed' | 'skipped'


@dataclass
class TileStep:
    """Один шаг алгоритма внутри тайла (фильтрация → ЦМР → производные → …)."""
    name: str
    status: StepStatus = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    message: Optional[str] = None  # лог-строка / причина сбоя шага

    def mark_running(self, started_at: str) -> None:
        self.status = "running"
        self.started_at = started_at

    def mark_done(self, finished_at: str, duration_ms: int, message: Optional[str] = None) -> None:
        self.status = "done"
        self.finished_at = finished_at
        self.duration_ms = duration_ms
        if message:
            self.message = message

    def mark_failed(self, finished_at: str, duration_ms: int, reason: str) -> None:
        self.status = "failed"
        self.finished_at = finished_at
        self.duration_ms = duration_ms
        self.message = reason

    def mark_skipped(self, message: Optional[str] = None) -> None:
        self.status = "skipped"
        if message:
            self.message = message


@dataclass
class FailedTile:
    name: str
    reason: str


@dataclass
class OutputArtifact:
    """Выходной артефакт тайла (Блок Г — куда сохранено)."""
    path: str
    kind: str  # 'geotiff' | 'shp' | 'dxf' | 'las'
    layer: str  # 'dtm' | 'slope' | 'aspect' | 'tpi' | 'contours' | 'heights' | 'tin' | 'ground_las'
    size_bytes: Optional[int] = None


@dataclass
class Tile:
    """Потайловое состояние. id уникален в рамках сессии."""
    id: str
    name: str
    kind: str = "pair"  # 'afs' | 'vls' | 'pair'
    status: TileStatus = "queued"
    steps: list[TileStep] = field(default_factory=list)
    current_step: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    reason: Optional[str] = None
    retry_of: Optional[str] = None
    output_dir: Optional[str] = None
    output_files: list[OutputArtifact] = field(default_factory=list)

    def step(self, name: str) -> TileStep:
        """Найти шаг по имени или создать."""
        for s in self.steps:
            if s.name == name:
                return s
        s = TileStep(name=name)
        self.steps.append(s)
        return s


@dataclass
class Job:
    """Задача рельефа над проектом (оркестрация по парам тайлов)."""
    id: str
    project_id: str
    type: str = "relief"
    status: JobStatus = "queued"
    progress: float = 0.0
    session_id: Optional[str] = None
    tiles_total: int = 0
    tiles_done: int = 0
    tiles_failed: int = 0
    tiles_skipped: int = 0
    failed_tiles: list[FailedTile] = field(default_factory=list)
    tiles: list[Tile] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    output_dir: Optional[str] = None
    params: Optional[dict] = None

    def recompute(self) -> None:
        """Пересчитать агрегаты по tiles (done/failed/skipped/progress)."""
        self.tiles_done = sum(1 for t in self.tiles if t.status == "done")
        self.tiles_failed = sum(1 for t in self.tiles if t.status == "failed")
        self.tiles_skipped = sum(1 for t in self.tiles if t.status == "skipped")
        total = self.tiles_total or len(self.tiles)
        self.progress = round(100.0 * self.tiles_done / total, 1) if total else 0.0
        self.failed_tiles = [FailedTile(t.name, t.reason or "") for t in self.tiles if t.status == "failed"]