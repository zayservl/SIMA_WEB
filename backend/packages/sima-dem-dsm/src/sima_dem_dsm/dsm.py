"""DSM — Digital Surface Model (цифровая модель поверхности).

Все параметры инкапсулированы. Без хардкода.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pdal
import rasterio
import numpy as np
from osgeo import gdal

from sima_dem_core.raster.holes import fill_voids, px_from_metres


@dataclass
class DSMConfig:
    """Параметры построения DSM."""
    resolution: float = 1.0
    output_type: str = "max"
    data_type: str = "float32"
    gdaldriver: str = "GTiff"
    interpolate: bool = True
    fill_holes: bool = True
    max_search_distance: int = 100
    smoothing_iterations: int = 0
    # Метод интерполяции пустот: "laplace" (гладко) или "idw" (GDALFillNodata,
    # даёт радиальные лучи внутрь крупных пустот). См. holes.fill_voids.
    fill_method: str = "laplace"
    # Проходов заполнения пустот. Водоём, сообщавшийся с внешней пустотой,
    # замыкается только после заполнения перемычки — за один проход он остаётся
    # дырой. 1 — историческое однопроходное поведение.
    fill_passes: int = 3
    # Пустоты-водоёмы получают плоскую отметку вместо интерполяции (3DEP
    # hydro-flattening). См. sima_dem_core.raster.hydro.
    hydro_flatten: bool = True
    # Допустимая экстраполяция за границу валидной области, м (0 — только
    # внутренние дыры). См. sima_dem_core.raster.holes.
    edge_extrapolation_m: float = 5.0


class DSMBuilder:
    """Построение DSM (цифровая модель поверхности) из LAS."""

    def __init__(
        self,
        output: str | Path,
        crs: str,
        config: Optional[DSMConfig] = None,
        aoi: Optional[str] = None,
    ) -> None:
        self.raster: list[str] = []
        self.water_levels: list[float] = []   # отметки гидровыравненных водоёмов, м
        self.aoi = aoi
        self.output_folder = str(output)
        self.crs = crs
        self.config = config or DSMConfig()

    @staticmethod
    def execute(pipeline: list) -> None:
        pipe = pdal.Pipeline(json.dumps(pipeline))
        pipe.execute()

    def _build_dsm(self, input_path: str, raster: str) -> None:
        cfg = self.config
        pipeline: list = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            {"type": "filters.assign", "value": [
                "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
                "ReturnNumber = 1 WHERE (ReturnNumber == 0)"]},
            {"type": "filters.elm"},
            {"type": "filters.outlier"},
            {"type": "filters.range", "limits": "Classification[1:5]"},
            {"type": "filters.sample", "radius": cfg.resolution},
            {"filename": raster, "gdaldriver": cfg.gdaldriver,
             "resolution": cfg.resolution, "output_type": cfg.output_type,
             "type": "writers.gdal", "data_type": cfg.data_type},
        ]
        if self.aoi:
            pipeline.insert(2, {"type": "filters.crop", "polygon": self.aoi})
        DSMBuilder.execute(pipeline)

    def _interpolate(self, raster: str) -> None:
        """Заполнить внутренние дырки и, опционально, приграничные пустоты.

        "Дырка" — nodata-регион, полностью окружённый валидными данными, а не
        только 1-пиксельная кайма вокруг валидной области. Дополнительно, если
        задан `edge_extrapolation_m`, заполняются пустоты не далее этого
        расстояния от валидных данных (см. sima_dem_core.raster.holes).

        Заполнение многопроходное (`fill_passes`): часть пустот замыкается в
        дыру только после заполнения соседних — характерный случай на водоёмах.
        """
        cfg = self.config
        if not cfg.fill_holes:
            return
        with rasterio.open(raster) as src:
            profile = src.profile
            arr = src.read(1)
            nodata = src.nodata
            mask = src.read_masks(1)

        if nodata is None:
            return

        result = fill_voids(
            arr, mask == 255,
            method=cfg.fill_method,
            max_search_distance=cfg.max_search_distance,
            smoothing_iterations=cfg.smoothing_iterations,
            max_extrapolation_px=px_from_metres(cfg.edge_extrapolation_m, cfg.resolution),
            max_passes=cfg.fill_passes,
            resolution_m=cfg.resolution,
            hydro_flatten=cfg.hydro_flatten)
        if not np.any(result.filled):
            return
        self.water_levels = result.water_levels

        with rasterio.open(raster, "w", **profile) as dest:
            dest.write_band(1, result.array)

    def _set_projection(self, raster: str, crs_wkt: Optional[str]) -> None:
        if raster is None or crs_wkt is None:
            return
        try:
            ds = gdal.Open(raster, gdal.GA_Update)
            if ds is not None:
                ds.SetProjection(crs_wkt)
                ds = None
        except Exception as ee:
            print("gdal SetProjection failed:", ee)

    def build(self, las_path: str, crs_wkt: Optional[str] = None, out_path: Optional[str] = None) -> str:
        if out_path:
            raster = out_path
        else:
            raster = os.path.join(self.output_folder, Path(las_path).stem + "_dsm.tif")
        self._build_dsm(las_path, raster)
        if self.config.interpolate:
            self._interpolate(raster)
        self.raster.append(raster)
        if crs_wkt:
            self._set_projection(raster, crs_wkt)
        return raster