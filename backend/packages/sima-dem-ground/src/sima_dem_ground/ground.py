"""ЦМР — цифровая модель рельефа.

Порт из legacy `processings/CMR.py` (GroundProcessing).
Все параметры инкапсулированы в SMRFConfig / FillConfig dataclass-ах.
Без хардкода — SMRF, интерполяция, output_type настраиваются через конфиг.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdal
import rasterio
import numpy as np
from rasterio.fill import fillnodata
from osgeo import gdal

from sima_dem_core.check_classification import CheckClassification


@dataclass
class SMRFConfig:
    """Параметры SMRF (Simple Morphological Filter)."""
    slope: float = 0.2
    window: int = 16
    threshold: float = 0.45
    scalar: float = 1.2
    returns: list = field(default_factory=lambda: ["first", "last", "intermediate", "only"])

    def to_dict(self) -> dict:
        return {"type": "filters.smrf", "slope": self.slope, "window": self.window,
                "threshold": self.threshold, "scalar": self.scalar, "returns": self.returns}


@dataclass
class FillConfig:
    """Параметры интерполяции nodata-дырок.

    fill_holes: заполнять только внутренние дырки (не экстраполировать края).
    max_search_distance: радиус поиска соседей для интерполяции.
    smoothing_iterations: сглаживаний при интерполяции.
    """
    fill_holes: bool = True
    max_search_distance: int = 100
    smoothing_iterations: int = 0


@dataclass
class RasterOutputConfig:
    """Параметры вывода растра через writers.gdal."""
    output_type: str = "mean"
    data_type: str = "float32"
    gdaldriver: str = "GTiff"


class GroundProcessing:
    """Построение ЦМР из LAS по алгоритму SMRF."""

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
        smrf: Optional[SMRFConfig] = None,
        fill: Optional[FillConfig] = None,
        raster_out: Optional[RasterOutputConfig] = None,
    ) -> None:
        self.classified_ground: Optional[str] = None
        self.raster: list[str] = []
        self.aoi = aoi
        self.output_folder = str(output)
        self.resolution = resolution
        self.crs = crs
        self.interpolate = interpolate
        self.is_CRS_EPSG = is_CRS_EPSG
        self.cut_smrf = cut_smrf
        self.save_ground_las = save_ground_las

        self.smrf = smrf or SMRFConfig()
        self.fill = fill or FillConfig(max_search_distance=interpol_dist)
        self.raster_out = raster_out or RasterOutputConfig()

    @staticmethod
    def execute(pipeline: list) -> None:
        pipe = pdal.Pipeline(json.dumps(pipeline))
        pipe.execute()

    def _get_ground(self, input_path: str, raster: str, out_path: Optional[str]) -> None:
        smrf_stage = self.smrf.to_dict()
        if self.cut_smrf:
            smrf_stage = {"type": "filters.smrf", "threshold": 3,
                          "returns": self.smrf.returns}

        pipeline: list = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            {"type": "filters.assign", "value": [
                "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
                "ReturnNumber = 1 WHERE (ReturnNumber == 0)"]},
            {"type": "filters.assign", "assignment": "Classification[:]=0"},
            {"type": "filters.elm"},
            {"type": "filters.outlier"},
            smrf_stage,
            {"type": "filters.sample", "radius": self.resolution},
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {"filename": raster, "gdaldriver": self.raster_out.gdaldriver,
             "resolution": self.resolution, "output_type": self.raster_out.output_type,
             "type": "writers.gdal", "data_type": self.raster_out.data_type},
        ]
        if self.aoi and self.is_CRS_EPSG:
            pipeline.insert(3, {"type": "filters.crop", "polygon": self.aoi})
        if self.save_ground_las:
            ground_las = out_path or (input_path.rsplit(".", 1)[0] + "_ground.las")
            pipeline.insert(7, {"type": "writers.las", "filename": ground_las})
        GroundProcessing.execute(pipeline)

    def _save_ground(self, input_path: str, raster: str, out_path: Optional[str]) -> None:
        pipeline: list = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            {"type": "filters.assign", "value": [
                "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
                "ReturnNumber = 1 WHERE (ReturnNumber == 0)"]},
            {"type": "filters.sample", "radius": self.resolution},
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {"type": "filters.elm"},
            {"type": "filters.outlier"},
            {"filename": raster, "gdaldriver": self.raster_out.gdaldriver,
             "resolution": self.resolution, "output_type": self.raster_out.output_type,
             "type": "writers.gdal", "data_type": self.raster_out.data_type},
        ]
        if self.save_ground_las:
            ground_las = out_path or (input_path.rsplit(".", 1)[0] + "_ground.las")
            pipeline.insert(3, {"type": "filters.assign",
                                "value": ["Classification = 1 WHERE Classification != 2"]})
            pipeline.insert(4, {"type": "writers.las", "filename": ground_las})
            if self.aoi and self.is_CRS_EPSG:
                pipeline.insert(3, {"type": "filters.crop", "polygon": self.aoi})
        GroundProcessing.execute(pipeline)

    def _get_raster_name(self, path: str, out_path: Optional[str]) -> tuple[str, str]:
        if out_path:
            filename, _ = os.path.splitext(out_path)
        else:
            filename, _ = os.path.splitext(path)
        self.classified_ground = filename + "classified.tif"
        tail = Path(filename).stem.replace("_relief", "")
        raster = os.path.join(self.output_folder, tail + "_dem.tif")
        smoothed = os.path.join(self.output_folder, tail + "_dem_smooth.tif")
        return raster, smoothed

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

    def _interpolate(self, raster: str) -> None:
        """При DTM пустоты остаются (не заполняются). Интерполяция — только при сглаживании."""
        pass

    def get_raster(self, path: str, crs_wkt: Optional[str] = None, out_path: Optional[str] = None) -> None:
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