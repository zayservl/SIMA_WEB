"""ЦМР — цифровая модель рельефа.

Порт из legacy `processings/CMR.py` (GroundProcessing).
Алгоритм: PDAL SMRF → elm → outlier → sample → range(Classification[2:2])
→ writers.gdal output_type:"mean" → (опц.) fillnodata интерполяция.
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

from .check_classification import CheckClassification


class GroundProcessing:
    """Построение ЦМР из LAS по алгоритму SMRF (Simple Morphological Filter)."""

    def __init__(
        self,
        output: str | Path,
        resolution: float,
        crs: str,
        aoi: Optional[str] = None,
        interpolate: bool = False,
        interpol_dist: int = 100,
        cut_smrf: bool = False,
        save_ground_las: bool = False,
        is_CRS_EPSG: bool = True,
    ) -> None:
        self.classified_ground: Optional[str] = None
        self.raster: list[str] = []
        self.aoi = aoi
        self.output_folder = str(output)
        self.resolution = resolution
        self.crs = crs
        self.interpolate = interpolate
        self.is_CRS_EPSG = is_CRS_EPSG
        self.interpol_dist = interpol_dist
        self.cut_smrf = cut_smrf
        self.save_ground_las = save_ground_las

    @staticmethod
    def execute(pipeline: list) -> None:
        pipe = pdal.Pipeline(json.dumps(pipeline))
        pipe.execute()

    def _get_ground(self, input_path: str, raster: str, out_path: Optional[str]) -> None:
        """SMRF + классификация → ЦМР (mean) из неклассифицированных точек."""
        pipeline: list = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            {
                "type": "filters.assign",
                "value": [
                    "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
                    "ReturnNumber = 1 WHERE (ReturnNumber == 0)",
                ],
            },
            {"type": "filters.assign", "assignment": "Classification[:]=0"},
            {"type": "filters.elm"},
            {"type": "filters.outlier"},
            {
                "type": "filters.smrf",
                "slope": 0.2,
                "window": 16,
                "threshold": 0.45,
                "scalar": 1.2,
                "returns": ["first", "last", "intermediate", "only"],
            },
            {"type": "filters.sample", "radius": self.resolution},
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {
                "filename": raster,
                "gdaldriver": "GTiff",
                "resolution": self.resolution,
                "output_type": "mean",
                "type": "writers.gdal",
                "data_type": "float32",
            },
        ]
        if self.aoi and self.is_CRS_EPSG:
            pipeline.insert(3, {"type": "filters.crop", "polygon": self.aoi})
        if self.cut_smrf:
            pipeline[5] = {
                "type": "filters.smrf",
                "threshold": 3,
                "returns": ["first", "last", "intermediate", "only"],
            }
        if self.save_ground_las:
            if out_path:
                ground_las = out_path
            else:
                path, ext = input_path.split(".")
                ground_las = path + "_ground." + ext
            pipeline.insert(7, {"type": "writers.las", "filename": ground_las})
        GroundProcessing.execute(pipeline)

    def _save_ground(self, input_path: str, raster: str, out_path: Optional[str]) -> None:
        """Построить ЦМР из уже классифицированных ground-точек (класс 2)."""
        pipeline: list = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            {
                "type": "filters.assign",
                "value": [
                    "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
                    "ReturnNumber = 1 WHERE (ReturnNumber == 0)",
                ],
            },
            {"type": "filters.sample", "radius": self.resolution},
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {"type": "filters.elm"},
            {"type": "filters.outlier"},
            {
                "filename": raster,
                "gdaldriver": "GTiff",
                "resolution": self.resolution,
                "output_type": "mean",
                "type": "writers.gdal",
                "data_type": "float32",
            },
        ]
        if self.save_ground_las:
            if out_path:
                ground_las = out_path
            else:
                path, ext = input_path.split(".")
                ground_las = path + "_ground." + ext
            pipeline.insert(
                3,
                {
                    "type": "filters.assign",
                    "value": ["Classification = 1 WHERE Classification != 2"],
                },
            )
            pipeline.insert(4, {"type": "writers.las", "filename": ground_las})
            if self.aoi and self.is_CRS_EPSG:
                pipeline.insert(3, {"type": "filters.crop", "polygon": self.aoi})
        GroundProcessing.execute(pipeline)

    def _get_raster_name(self, path: str, out_path: Optional[str]) -> tuple[str, str]:
        if out_path:
            filename, file_extension = os.path.splitext(out_path)
        else:
            filename, file_extension = os.path.splitext(path)
        self.classified_ground = filename + "classified" + file_extension
        tail = Path(filename).stem.replace("_relief", "")
        raster = os.path.join(self.output_folder, tail + "_dem" + ".tif")
        smoothed = os.path.join(self.output_folder, tail + "_dem_smooth" + ".tif")
        return raster, smoothed

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

    def get_raster(self, path: str, crs_wkt: Optional[str] = None, out_path: Optional[str] = None) -> None:
        """Главная точка входа: построить ЦМР из LAS-файла."""
        check_class = CheckClassification(path)
        raster, smoothed = self._get_raster_name(path, out_path)
        if check_class.is_ground:
            self._save_ground(path, raster, out_path)
        else:
            self._get_ground(path, raster, out_path)
        if self.interpolate:
            self._interpolate(raster)
        self.raster.append(raster)
        if crs_wkt:
            self._set_projection(raster, crs_wkt)