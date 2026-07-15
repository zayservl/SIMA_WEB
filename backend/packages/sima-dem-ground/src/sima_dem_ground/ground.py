"""ЦМР — цифровая модель рельефа.

Порт из legacy `processings/CMR.py` (GroundProcessing).
Все параметры инкапсулированы в dataclass-ах: SMRFConfig, FillConfig, RasterOutputConfig.
Pipeline: readers.las → assign → [crop] → elm → outlier → SMRF → sample → range → writers.gdal
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
    slope: float = 0.2
    window: int = 16
    threshold: float = 0.45
    scalar: float = 1.2
    returns: list = field(default_factory=lambda: ["first", "last", "intermediate", "only"])

    def to_dict(self) -> dict:
        return {"type": "filters.smrf", "slope": self.slope, "window": self.window,
                "threshold": self.threshold, "scalar": self.scalar, "returns": self.returns}

    def to_cut_dict(self) -> dict:
        return {"type": "filters.smrf", "threshold": 3, "returns": self.returns}


@dataclass
class FillConfig:
    fill_holes: bool = True
    max_search_distance: int = 100
    smoothing_iterations: int = 0
    fallback_to_min_z: bool = True


@dataclass
class RasterOutputConfig:
    output_type: str = "idw"
    data_type: str = "float32"
    gdaldriver: str = "GTiff"


def _fix_returns_stage() -> dict:
    return {"type": "filters.assign", "value": [
        "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
        "ReturnNumber = 1 WHERE (ReturnNumber == 0)"]}


def _elm_outlier_stages() -> list[dict]:
    return [{"type": "filters.elm"}, {"type": "filters.outlier"}]


def _writers_gdal_stage(filename: str, cfg: RasterOutputConfig, resolution: float) -> dict:
    return {"filename": filename, "gdaldriver": cfg.gdaldriver,
            "resolution": resolution, "output_type": cfg.output_type,
            "type": "writers.gdal", "data_type": cfg.data_type}


class GroundProcessing:

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
        is_CRS_EPSG: Optional[bool] = None,
        smrf: Optional[SMRFConfig] = None,
        fill: Optional[FillConfig] = None,
        raster_out: Optional[RasterOutputConfig] = None,
    ) -> None:
        self.raster: list[str] = []
        self.classified_ground: Optional[str] = None
        self.aoi = aoi
        self.output_folder = str(output)
        self.resolution = resolution
        self.crs = crs
        self.interpolate = interpolate
        self.is_CRS_EPSG = is_CRS_EPSG if is_CRS_EPSG is not None else self._detect_crs_is_epsg(crs)
        self.cut_smrf = cut_smrf
        self.save_ground_las = save_ground_las
        self.smrf = smrf or SMRFConfig()
        self.fill = fill or FillConfig(max_search_distance=interpol_dist)
        self.raster_out = raster_out or RasterOutputConfig()

    @staticmethod
    def _detect_crs_is_epsg(crs: str) -> bool:
        if not crs:
            return False
        upper = crs.upper().strip()
        if upper.startswith("EPSG:"):
            return True
        if "LOCAL_CS" in upper:
            return False
        if "PROJCS" in upper or "GEOGCS" in upper:
            return True
        return False

    @staticmethod
    def _run_pdal(pipeline: list) -> None:
        pdal.Pipeline(json.dumps(pipeline)).execute()

    def _maybe_crop_stage(self) -> list[dict]:
        if self.aoi and self.is_CRS_EPSG:
            return [{"type": "filters.crop", "polygon": self.aoi}]
        return []

    def _build_ground_pipeline(self, input_path: str, raster: str, out_path: Optional[str]) -> list[dict]:
        smrf_stage = self.smrf.to_cut_dict() if self.cut_smrf else self.smrf.to_dict()
        pipeline = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            _fix_returns_stage(),
            {"type": "filters.assign", "assignment": "Classification[:]=0"},
        ]
        pipeline += self._maybe_crop_stage()
        pipeline += _elm_outlier_stages()
        pipeline.append(smrf_stage)
        pipeline.append({"type": "filters.sample", "radius": self.resolution})
        pipeline.append({"type": "filters.range", "limits": "Classification[2:2]"})
        if self.save_ground_las:
            ground_las = out_path or (input_path.rsplit(".", 1)[0] + "_ground.las")
            pipeline.append({"type": "writers.las", "filename": ground_las})
        pipeline.append(_writers_gdal_stage(raster, self.raster_out, self.resolution))
        return pipeline

    def _build_save_ground_pipeline(self, input_path: str, raster: str, out_path: Optional[str]) -> list[dict]:
        pipeline = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            _fix_returns_stage(),
        ]
        if self.save_ground_las:
            ground_las = out_path or (input_path.rsplit(".", 1)[0] + "_ground.las")
            pipeline.append({"type": "filters.assign", "value": ["Classification = 1 WHERE Classification != 2"]})
            pipeline.append({"type": "writers.las", "filename": ground_las})
        pipeline += self._maybe_crop_stage()
        pipeline.append({"type": "filters.sample", "radius": self.resolution})
        pipeline.append({"type": "filters.range", "limits": "Classification[2:2]"})
        pipeline += _elm_outlier_stages()
        pipeline.append(_writers_gdal_stage(raster, self.raster_out, self.resolution))
        return pipeline

    def _build_min_z_pipeline(self, input_path: str, raster_path: str) -> list[dict]:
        pipeline = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            _fix_returns_stage(),
        ]
        pipeline += self._maybe_crop_stage()
        pipeline += _elm_outlier_stages()
        min_cfg = RasterOutputConfig(output_type="min", data_type=self.raster_out.data_type,
                                     gdaldriver=self.raster_out.gdaldriver)
        pipeline.append(_writers_gdal_stage(raster_path, min_cfg, self.resolution))
        return pipeline

    def _fill_from_min_z(self, input_path: str, raster: str) -> None:
        min_z_raster = raster.replace("_dem.tif", "_minz_fallback.tif")
        self._run_pdal(self._build_min_z_pipeline(input_path, min_z_raster))

        aligned = min_z_raster.replace("_fallback.tif", "_aligned.tif")
        try:
            with rasterio.open(raster) as ref:
                ref_transform = ref.transform
                ref_w, ref_h, ref_crs = ref.width, ref.height, ref.crs
            gdal.Warp(aligned, min_z_raster, dstSRS=ref_crs,
                      xRes=self.resolution, yRes=self.resolution,
                      outputBounds=[ref_transform[2],
                                    ref_transform[5] - ref_h * self.resolution,
                                    ref_transform[2] + ref_w * self.resolution,
                                    ref_transform[5]],
                      resampleAlg="bilinear")
            min_z_source = aligned
        except Exception:
            min_z_source = min_z_raster

        with rasterio.open(raster) as src:
            profile = src.profile
            dtm = src.read(1)
            dtm_nodata = src.nodata
            dtm_mask = src.read_masks(1)

        with rasterio.open(min_z_source) as src:
            min_z = src.read(1)
            min_z_nodata = src.nodata

        if dtm_nodata is None:
            self._cleanup_temp(min_z_raster, aligned)
            return

        if dtm.shape != min_z.shape:
            min_h = min(dtm.shape[0], min_z.shape[0])
            min_w = min(dtm.shape[1], min_z.shape[1])
            dtm, min_z, dtm_mask = dtm[:min_h, :min_w], min_z[:min_h, :min_w], dtm_mask[:min_h, :min_w]

        dtm_holes = (dtm == dtm_nodata) | (dtm_mask == 0)
        min_z_valid = (min_z != min_z_nodata) if min_z_nodata is not None else np.ones_like(min_z, bool)
        fill_mask = dtm_holes & min_z_valid

        if np.any(fill_mask):
            dtm[fill_mask] = min_z[fill_mask]
            with rasterio.open(raster, "w", **profile) as dest:
                dest.write_band(1, dtm)

        self._cleanup_temp(min_z_raster, aligned)

    @staticmethod
    def _cleanup_temp(*paths: str) -> None:
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass

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
            max_search_distance=self.fill.max_search_distance,
            smoothing_iterations=self.fill.smoothing_iterations,
        )
        arr = np.where(holes, arr_filled, arr)

        with rasterio.open(raster, "w", **profile) as dest:
            dest.write_band(1, arr)

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

    def get_raster(self, path: str, crs_wkt: Optional[str] = None, out_path: Optional[str] = None) -> None:
        check = CheckClassification(path)
        raster, _ = self._get_raster_name(path, out_path)
        if check.is_ground:
            self._run_pdal(self._build_save_ground_pipeline(path, raster, out_path))
        else:
            self._run_pdal(self._build_ground_pipeline(path, raster, out_path))
        if self.fill.fallback_to_min_z:
            self._fill_from_min_z(path, raster)
        if self.interpolate:
            self._interpolate(raster)
        self.raster.append(raster)
        if crs_wkt:
            self._set_projection(raster, crs_wkt)