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
from rasterio.fill import fillnodata
from osgeo import gdal


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
        """Заполнить внутренние дырки без экстраполяции краёв.

        "Дырка" — nodata-регион, полностью окружённый валидными данными
        (scipy.ndimage.binary_fill_holes), а не только 1-пиксельная кайма
        вокруг валидной области — иначе внутренние дырки шире ~2px остаются
        незаполненными (см. корректную реализацию в sima_dem_ground.ground).
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

        from scipy.ndimage import binary_fill_holes
        valid = mask == 255
        holes = binary_fill_holes(valid) & ~valid
        if not np.any(holes):
            return

        arr_filled = fillnodata(
            arr.copy(), mask=mask,
            max_search_distance=cfg.max_search_distance,
            smoothing_iterations=cfg.smoothing_iterations)
        arr = np.where(holes, arr_filled, arr)

        with rasterio.open(raster, "w", **profile) as dest:
            dest.write_band(1, arr)

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