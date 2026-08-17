"""Дискретные тестируемые шаги конвейера рельефа.

Каждый шаг — чистая функция: входной артефакт → выходной артефакт(ы).
Обёртки над вычислительным ядром sima-dem-* (GroundProcessing, DSMBuilder,
CurvatureProcessing, calculate_tpi, generate_contours, extract_heights) +
новые TIN/.shp. Шаги детерминированы и тестируются изолированно.

Последовательность (Q3 «Анализ рельефа»):
  crop → filter → ЦМР (DTM) → smooth → derivatives(slope/aspect/TPI)
  → vectors(contours .shp / TIN .dxf) → heights(.shp, las|dem)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sima_dem_core.curvature import CurvatureProcessing
from sima_dem_core.crop import Crop
from sima_dem_core.filters import ManualFilter, StatFilter, RangeFilter, OutlierFilter
from sima_dem_core.height import extract_heights
from sima_dem_core.raster.contours import generate_contours
from sima_dem_core.raster.holes import px_from_metres
from sima_dem_core.raster.tpi import calculate_tpi
from sima_dem_dsm.dsm import DSMBuilder, DSMConfig
from sima_dem_ground.ground import GroundProcessing, FillConfig, RasterOutputConfig

from .contract import ReliefParams, filter_kwargs, map_smrf_config, map_tpi_config
from .status import OutputArtifact
from .tin import build_tin_from_las


def _stem(path: str) -> str:
    return Path(path).stem


def _artifact(path: str, kind: str, layer: str) -> OutputArtifact:
    try:
        size = os.path.getsize(path)
    except OSError:
        size = None
    return OutputArtifact(path=path, kind=kind, layer=layer, size_bytes=size)


# --- 1. Crop ------------------------------------------------------------

def step_crop(las_path: str, aoi: Optional[str], out_dir: str) -> str:
    """Обрезать LAS по AOI (shapefile). Если AOI нет — пропускает."""
    if not aoi:
        return las_path
    out_path = os.path.join(out_dir, _stem(las_path) + "_cropped.las")
    Crop(vls_cropped=out_path, vls_path=las_path, shapefile=aoi).cropCalc()
    return out_path


# --- 2. Filter ----------------------------------------------------------

def step_filter(las_path: str, params: ReliefParams, out_dir: str, resolution: float = 1.0) -> str:
    """Применить фильтр LAS (manual/stat/range/outlier/smrf-пропуск).

    `resolution` конструкторы фильтров принимают ради единой сигнатуры с легаси;
    сам отбор точек от него не зависит, поэтому передаём разрешение расчёта.
    """
    if params.filter_method in (None, "smrf"):
        return las_path  # SMRF выполняется внутри ground-классификации
    out_path = os.path.join(out_dir, _stem(las_path) + "_filtered.las")
    kw = filter_kwargs(params)
    res = resolution
    m = params.filter_method
    if m == "manual":
        ManualFilter(las_path, res, kw["z_min"], kw["z_max"], out_path).filter()
    elif m == "stat":
        StatFilter(las_path, res, kw["stat_m"], out_path).filter()
    elif m == "range":
        RangeFilter(las_path, res, kw["range_min_pct"], kw["range_max_pct"], out_path).filter()
    elif m in ("outlier", "kmeans"):
        # "kmeans" — историческое имя значения FilterMethod в контракте UI
        # (src/api/types.ts), которому в бэкенде соответствует OutlierFilter.
        OutlierFilter(las_path, res, kw["neighbours"], kw["multiplier"], out_path).filter()
    else:
        raise ValueError(f"Неизвестный filter_method: {m!r}")
    return out_path


# --- 3. DTM (ЦМР) -------------------------------------------------------

def step_dtm(
    las_path: str,
    params: ReliefParams,
    out_dir: str,
    crs: str,
    resolution: float,
    existing_dtm: Optional[str] = None,
    save_ground_las: bool = True,
) -> tuple[str, Optional[str]]:
    """Построить ЦМР (DTM) из LAS (SMRF) либо использовать существующую ЦМР.

    Q3 «Использование существующей ЦМР»: если existing_dtm задан — вернуть его,
    пропустив расчёт. Возвращает (dtm_path, ground_las_path|None).
    """
    if existing_dtm:
        return existing_dtm, None
    stem = _stem(las_path)
    ground_las = os.path.join(out_dir, stem + "_ground.las") if save_ground_las else None
    smrf_cfg = map_smrf_config(params.smrf)
    gp = GroundProcessing(
        output=out_dir, resolution=resolution, crs=crs,
        interpolate=params.derivatives.interpolation,
        interpol_dist=params.derivatives.inter_amp,
        save_ground_las=save_ground_las,
        smrf=smrf_cfg,
        cut_smrf=params.smrf.cut_smrf,
        elm=params.smrf.elm,
        outlier=params.smrf.outlier,
        fill=FillConfig(fill_holes=params.derivatives.interpolation,
                         max_search_distance=params.derivatives.inter_amp,
                         fallback_to_min_z=True,
                         edge_extrapolation_m=params.derivatives.edge_extrapolation_m,
                         fill_method=params.derivatives.fill_method,
                         fill_passes=params.derivatives.fill_passes,
                         hydro_flatten=params.derivatives.hydro_flatten),
        raster_out=RasterOutputConfig(output_type=params.dtm.output_type),
    )
    gp.get_raster(las_path, crs_wkt=crs, out_path=ground_las)
    dtm_path = gp.raster[-1] if gp.raster else os.path.join(out_dir, stem + "_dem.tif")
    return dtm_path, ground_las


# --- 3b. DSM (ЦММ) ------------------------------------------------------

def step_dsm(
    las_path: str,
    params: ReliefParams,
    out_dir: str,
    crs: str,
    resolution: float,
) -> str:
    """Построить ЦММ (DSM — цифровая модель поверхности) из LAS.

    Использует DSMBuilder (output_type='max') — соответствует легаси CMD.py.
    Q3: ЦММ требуется как вход для «Анализ насаждений» и «Анализ водного слоя».
    """
    stem = _stem(las_path)
    out_path = os.path.join(out_dir, stem + "_dsm.tif")
    cfg = DSMConfig(
        resolution=resolution,
        output_type=params.dsm.output_type,
        interpolate=params.dsm.interpolate,
        fill_holes=params.dsm.fill_holes,
        max_search_distance=params.dsm.max_search_distance,
        edge_extrapolation_m=params.dsm.edge_extrapolation_m,
        fill_method=params.dsm.fill_method,
        fill_passes=params.dsm.fill_passes,
        hydro_flatten=params.dsm.hydro_flatten,
    )
    builder = DSMBuilder(output=out_dir, crs=crs, config=cfg)
    dsm_path = builder.build(las_path, crs_wkt=crs, out_path=out_path)
    return dsm_path


# --- 4. Smooth ----------------------------------------------------------

def step_smooth(dtm_path: str, params: ReliefParams, out_dir: str, resolution: float) -> Optional[str]:
    """Сгладить ЦМР (гаусс). Возвращает путь сглаженного растра или None."""
    if not params.smoothing.enabled:
        return None
    from sima_dem_core.raster.smooth import gauss_smooth
    stem = _stem(dtm_path).replace("_dem", "")
    out_path = os.path.join(out_dir, stem + "_dem_smooth.tif")
    gauss_smooth(
        raster=dtm_path, smoothed=out_path,
        sigma=params.smoothing.sigma * resolution,
        order=params.smoothing.order, window_size=params.smoothing.window,
        fill_holes=params.derivatives.interpolation,
        max_search_distance=params.derivatives.inter_amp,
        max_extrapolation_px=px_from_metres(
            params.derivatives.edge_extrapolation_m, resolution),
        fill_passes=params.derivatives.fill_passes,
        fill_method=params.derivatives.fill_method,
    )
    return out_path


def resolve_base_raster(dtm_path: str, smoothed: Optional[str]) -> str:
    """Базовый растр для производных — сглаженный, если есть, иначе сырой DTM (#4 правка эксперта)."""
    return smoothed if smoothed else dtm_path


# --- 5. Derivatives ------------------------------------------------------

def step_slope(base_raster: str, crs: str, out_dir: str, res: float) -> str:
    curv = CurvatureProcessing()
    return curv.calculate_slope(base_raster, crs, res, res, out_dir)


def step_aspect(base_raster: str, crs: str, out_dir: str, res: float) -> str:
    curv = CurvatureProcessing()
    return curv.calculate_aspect(base_raster, crs, res, res, out_dir)


def step_tpi(base_raster: str, params: ReliefParams, out_dir: str, crs: str, resolution: float) -> str:
    return calculate_tpi(
        dem_path=base_raster, crs=crs, output_folder=out_dir,
        input_res=resolution, res=params.derivatives.tpi_res,
        config=map_tpi_config(params.derivatives),
    )


# --- 6. Vectors (contours .shp / TIN .dxf) ------------------------------

def step_contours(base_raster: str, intervals: list, out_dir: str, crs: str) -> list[str]:
    """Горизонтали в .shp (требование Q3)."""
    paths: list[str] = []
    stem = _stem(base_raster).replace("_dem", "").replace("_smooth", "")
    for interval in intervals:
        out_path = os.path.join(out_dir, f"{stem}_contours_{interval}.shp")
        generate_contours(raster_path=base_raster, interval=float(interval),
                          output_path=out_path, crs_wkt=crs, driver="ESRI Shapefile")
        paths.append(out_path)
    return paths


def step_tin(las_path: str, min_distance_m: float, out_dir: str, crs: str, stem: Optional[str] = None) -> str:
    """TIN-поверхность из ground-точек LAS → .dxf (требование Q3)."""
    name = stem or _stem(las_path)
    out_path = os.path.join(out_dir, f"{name}_tin.dxf")
    build_tin_from_las(las_path, out_path, min_distance_m=min_distance_m, crs_wkt=crs)
    return out_path


# --- 7. Heights (.shp, las|dem) -----------------------------------------

def step_heights(
    las_path: Optional[str],
    params: ReliefParams,
    out_dir: str,
    crs: str,
    dem_path: Optional[str] = None,
    stem: Optional[str] = None,
) -> str:
    """Отметки высот в .shp (требование Q3). Источник 'las' или 'dem'."""
    name = stem or _stem(las_path or (dem_path or "heights"))
    out_path = os.path.join(out_dir, f"{name}_alt.shp")
    source_dem = dem_path if params.heights.source == "dem" else None
    extract_heights(
        las_path=las_path or "", min_distance_m=params.heights.min_distance_m,
        result_layer_name=out_path, crs=crs, out_format="shp",
        dem_path=source_dem,
    )
    return out_path