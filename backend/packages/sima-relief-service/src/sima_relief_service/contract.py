"""Контракт параметров рельефа (1:1 к src/api/types.ts::ReliefParams) и маппинг
во внутренние dataclass-конфиги sima-dem-*.

Здесь же нормализация имён полей фильтров (spm/spr/spp/mean_k/mult из UI-контракта
→ параметры фильтров: z_min/z_max/stat_m/range_pct/neighbours/multiplier).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sima_dem_ground.ground import SMRFConfig
from sima_dem_core.raster.tpi import TPIConfig


# --- ReliefParams: 1:1 к src/api/types.ts --------------------------------

FilterMethod = str  # 'manual' | 'stat' | 'range' | 'kmeans' | 'smrf'


@dataclass
class FilterParams:
    spm_min: Optional[float] = None
    spm_max: Optional[float] = None
    spr_num: Optional[int] = None
    spp_min: Optional[float] = None
    spp_max: Optional[float] = None
    mean_k: Optional[int] = None
    mult: Optional[float] = None


@dataclass
class SmrfParams:
    slope: float = 0.2
    window: int = 16
    threshold: float = 0.45
    scalar: float = 1.2
    cut_smrf: bool = False
    elm: bool = True
    outlier: bool = True


@dataclass
class SmoothingParams:
    enabled: bool = False
    sigma: float = 2.0  # legacy: GAUSS_STD(0.25) × RESOLUTION(0.25→1.0) → 2.0 при res=1.0
    order: int = 0
    window: int = 5


@dataclass
class DsmParams:
    """Параметры построения ЦММ (DSM — цифровая модель поверхности/местности).

    Q3 «Анализ рельефа» не требует ЦММ напрямую, но легаси-прототип (sima_dsm_demo)
    и модуль forest_analysis требуют ЦММ как вход. Сервис рельефа строит ЦММ
    по запросу (enabled=True), используя DSMBuilder (output_type='max').
    """
    enabled: bool = False
    output_type: str = "max"  # legacy CMD.py: writers.gdal output_type='max'
    interpolate: bool = True
    fill_holes: bool = True
    max_search_distance: int = 100


@dataclass
class DerivativesParams:
    slopes: bool = False
    slopes_res: float = 1.0
    aspect: bool = False
    aspect_res: float = 1.0
    tpi: bool = False
    tpi_radii: list = field(default_factory=lambda: [270, 810, 2430])
    interpolation: bool = True
    inter_amp: int = 100


@dataclass
class HeightsParams:
    enabled: bool = False
    source: str = "las"  # 'las' | 'dem'
    step: int = 10


@dataclass
class VectorsParams:
    horizontals: list = field(default_factory=lambda: [0.5, 2.0, 5.0, 10.0])  # legacy: 0.5/2/5/10 м
    tin: bool = False


@dataclass
class ReliefParams:
    filter_method: FilterMethod = "smrf"
    filter: FilterParams = field(default_factory=FilterParams)
    smrf: SmrfParams = field(default_factory=SmrfParams)
    smoothing: SmoothingParams = field(default_factory=SmoothingParams)
    dsm: DsmParams = field(default_factory=DsmParams)
    derivatives: DerivativesParams = field(default_factory=DerivativesParams)
    heights: HeightsParams = field(default_factory=HeightsParams)
    vectors: VectorsParams = field(default_factory=VectorsParams)
    target_crs: str = ""
    deterministic: bool = False
    seed: int = 0


# --- Контекст запроса ---------------------------------------------------

@dataclass
class TileInput:
    """Пара тайлов АФС+ВЛС или одиночный файл для обработки."""
    name: str
    vls_path: Optional[str] = None
    afs_path: Optional[str] = None
    aoi: Optional[str] = None
    existing_dtm: Optional[str] = None  # Q3 «Использование существующей ЦМР»


@dataclass
class ReliefRequest:
    """Вход сервиса рельефа: параметры + файлы + контекст сессии."""
    params: ReliefParams
    tiles: list[TileInput] = field(default_factory=list)
    project_id: str = "default"
    season: Optional[str] = None  # Q3 «Сезон съёмки»
    repository: Optional[str] = None  # Q3 «Репозиторий для сохранения результата»
    resolution: float = 1.0  # Q3 «Разрешение ЦМР»
    session_id: Optional[str] = None


# --- Маппинг контракт → внутренние конфиги -------------------------------

def map_smrf_config(p: SmrfParams) -> SMRFConfig:
    return SMRFConfig(
        slope=p.slope, window=p.window, threshold=p.threshold, scalar=p.scalar,
    )


def map_tpi_config(d: DerivativesParams) -> TPIConfig:
    radii = d.tpi_radii or [270, 810, 2430]
    return TPIConfig(radii_m=list(radii))


def filter_kwargs(p: ReliefParams) -> dict:
    """Нормализация полей фильтра UI-контракта → kwargs конструкторов фильтров.

    manual: z_min=spm_min, z_max=spm_max
    stat: stat_m=mult (σ-кратность), neighbours=spr_num
    range: range_min_pct=spp_min, range_max_pct=spp_max
    outlier: neighbours=mean_k, multiplier=mult
    """
    f = p.filter
    return {
        "z_min": f.spm_min if f.spm_min is not None else 0.0,
        "z_max": f.spm_max if f.spm_max is not None else 1000.0,
        "stat_m": f.mult if f.mult is not None else 2.0,
        "neighbours": f.mean_k if f.mean_k is not None else 8,
        "multiplier": f.mult if f.mult is not None else 2.0,
        "range_min_pct": f.spp_min if f.spp_min is not None else 0.0,
        "range_max_pct": f.spp_max if f.spp_max is not None else 1.0,
    }