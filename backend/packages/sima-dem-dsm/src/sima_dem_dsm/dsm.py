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
            {"type": "filters.sample", "radius": cfg.resolution},
            {"filename": raster, "gdaldriver": cfg.gdaldriver,
             "resolution": cfg.resolution, "output_type": cfg.output_type,
             "type": "writers.gdal", "data_type": cfg.data_type},
        ]
        if self.aoi:
            pipeline.insert(2, {"type": "filters.crop", "polygon": self.aoi})
        DSMBuilder.execute(pipeline)

    def _interpolate(self, raster: str) -> None:
        """Заполнить внутренние дырки без экстраполяции краёв."""
        cfg = self.config
        if not cfg.fill_holes:
            return
        with rasterio.open(raster) as src:
            profile = src.profile
            arr = src.read(1)
            nodata = src.nodata
            if nodata is None:
                return
            mask = src.read_masks(1)
            arr_filled = fillnodata(
                arr.copy(), mask=mask,
                max_search_distance=cfg.max_search_distance,
                smoothing_iterations=cfg.smoothing_iterations)

            from scipy.ndimage import binary_dilation
            valid = mask == 255
            dilated_valid = binary_dilation(valid, iterations=1)
            border_mask = np.ones_like(mask, dtype=bool)
            border_mask[1:-1, 1:-1] = False
            was_nodata = (arr == nodata)
            holes = was_nodata & dilated_valid & ~border_mask
            keep_nodata = was_nodata & ~holes
            arr_filled = np.where(keep_nodata, nodata, arr_filled)
        with rasterio.open(raster, "w", **profile) as dest:
            dest.write_band(1, arr_filled)

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