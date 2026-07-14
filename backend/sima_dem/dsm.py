"""DSM — Digital Surface Model (цифровая модель поверхности).

Строит растр поверхности из LAS-точек (все классы или first return).
Использует PDAL writers.gdal с output_type="max" для получения DSM.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import pdal
import rasterio
from rasterio.fill import fillnodata
from osgeo import gdal


class DSMBuilder:
    """Построение DSM (цифровая модель поверхности) из LAS."""

    def __init__(
        self,
        output: str | Path,
        resolution: float,
        crs: str,
        aoi: Optional[str] = None,
        interpolate: bool = True,
        interpol_dist: int = 100,
        output_type: str = "max",
    ) -> None:
        self.raster: list[str] = []
        self.aoi = aoi
        self.output_folder = str(output)
        self.resolution = resolution
        self.crs = crs
        self.interpolate = interpolate
        self.interpol_dist = interpol_dist
        self.output_type = output_type

    @staticmethod
    def execute(pipeline: list) -> None:
        pipe = pdal.Pipeline(json.dumps(pipeline))
        pipe.execute()

    def _build_dsm(self, input_path: str, raster: str) -> None:
        """Построить DSM через PDAL writers.gdal output_type=max."""
        pipeline: list = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            {
                "type": "filters.assign",
                "value": [
                    "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
                    "ReturnNumber = 1 WHERE (ReturnNumber == 0)",
                ],
            },
            {"type": "filters.elm"},
            {"type": "filters.outlier"},
            {"type": "filters.sample", "radius": self.resolution},
            {
                "filename": raster,
                "gdaldriver": "GTiff",
                "resolution": self.resolution,
                "output_type": self.output_type,
                "type": "writers.gdal",
                "data_type": "float32",
            },
        ]
        if self.aoi:
            pipeline.insert(2, {"type": "filters.crop", "polygon": self.aoi})
        DSMBuilder.execute(pipeline)

    def _interpolate(self, raster: str) -> None:
        with rasterio.open(raster) as src:
            profile = src.profile
            arr = src.read(1)
            arr_filled = fillnodata(
                arr,
                mask=src.read_masks(1),
                max_search_distance=self.interpol_dist,
                smoothing_iterations=0,
            )
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
        except Exception as ee:  # noqa: BLE001
            print("gdal SetProjection failed:", ee)

    def build(self, las_path: str, crs_wkt: Optional[str] = None, out_path: Optional[str] = None) -> str:
        """Построить DSM из LAS. Возвращает путь к выходному GeoTIFF."""
        if out_path:
            raster = out_path
        else:
            tail = Path(las_path).stem
            raster = os.path.join(self.output_folder, tail + "_dsm.tif")
        self._build_dsm(las_path, raster)
        if self.interpolate:
            self._interpolate(raster)
        self.raster.append(raster)
        if crs_wkt:
            self._set_projection(raster, crs_wkt)
        return raster