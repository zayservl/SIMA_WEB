"""СИМА — сервисный слой рельефа.

Библиотека, инкапсулирующая функционал блока «Анализ рельефа» из Q3-концепции:
оценка материалов (LAS/TIFF), расчёт ЦМР/ЦМД, производные (уклон/экспозиция/TPI),
векторные слои (горизонтали .shp, отметки высот .shp, TIN .dxf), сессионное
хранение, модель статусов по тайлам, детерминизм. Пригодна для Jupyter-демо и
переиспользования; структурно готова к обёртке в реальный backend-сервис
(FastAPI/Celery/S3) — но сама HTTP/Celery/S3 не реализует.
"""

from __future__ import annotations

from .contract import (
    ReliefParams, ReliefRequest, TileInput,
    FilterParams, SmrfParams, SmoothingParams, DtmParams, DsmParams, DerivativesParams,
    HeightsParams, VectorsParams,
)
from .status import Job, Tile, TileStep, OutputArtifact, FailedTile
from .storage import Storage, LocalFSStorage, Session
from .assessment import (
    MaterialAssessment, AfsReport, VlsReport, CrsCheck,
    assess_materials, assess_las, assess_tiff, check_pair_crs, crs_equivalent,
)
from .service import ReliefService, ReliefResult
from .determinism import DeterminismContext

__all__ = [
    "ReliefService", "ReliefResult", "ReliefRequest", "ReliefParams", "TileInput",
    "FilterParams", "SmrfParams", "SmoothingParams", "DtmParams", "DsmParams", "DerivativesParams",
    "HeightsParams", "VectorsParams",
    "Job", "Tile", "TileStep", "OutputArtifact", "FailedTile",
    "Storage", "LocalFSStorage", "Session",
    "MaterialAssessment", "AfsReport", "VlsReport", "CrsCheck",
    "assess_materials", "assess_las", "assess_tiff",
    "check_pair_crs", "crs_equivalent",
    "DeterminismContext",
]