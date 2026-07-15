"""Оркестрация конвейера рельефа.

Все параметры инкапсулированы в PipelineConfig.
Склоны/экспозиции строятся по сглаженной DTM/DEM (#4 правка эксперта).
Интерполяция дырок при сглаживании (#3). Без экстраполяции краёв (#2).
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from sima_dem_ground.ground import GroundProcessing, SMRFConfig, FillConfig, RasterOutputConfig
from sima_dem_core.curvature import CurvatureProcessing
from sima_dem_core.raster.smooth import gauss_smooth
from sima_dem_core.raster.median import med_filter
from sima_dem_core.raster.tpi import calculate_tpi, TPIConfig
from sima_dem_core.raster.contours import generate_contours
from sima_dem_core.filters import ManualFilter, StatFilter, RangeFilter, OutlierFilter
from sima_dem_core.crop import Crop
from sima_dem_core.height import get_every_nth


@dataclass
class PipelineConfig:
    """Конфигурация конвейера рельефа — все параметры инкапсулированы."""
    las_catalog: str
    output_dir: str
    resolution: float
    crs: str
    aoi: Optional[str] = None

    # Фильтрация LAS
    filter_type: Optional[str] = None
    z_min: float = 0.0
    z_max: float = 1000.0
    stat_m: float = 2.0
    range_min_pct: float = 0.0
    range_max_pct: float = 1.0
    outlier_neighbours: int = 8
    outlier_multiplier: float = 2.0

    # SMRF
    smrf: SMRFConfig = field(default_factory=SMRFConfig)

    # Интерполяция дырок (без экстраполяции краёв)
    interpolate: bool = True
    fill_holes: bool = True
    interpol_dist: int = 100
    fallback_to_min_z: bool = True

    # Сглаживание
    smoothing_method: str = "gauss"
    gauss_sigma: Optional[float] = None
    gauss_order: int = 0
    gauss_window: int = 5
    gauss_fill_holes: bool = True
    median_window: int = 5

    # TPI
    do_tpi: bool = False
    tpi: TPIConfig = field(default_factory=TPIConfig)

    # Уклоны/экспозиции (строятся по сглаженной DTM если есть, иначе по сырой)
    do_slopes: bool = False
    do_aspects: bool = False

    # Высоты
    do_heights: bool = False
    height_step: int = 10

    # Горизонтали (изолинии)
    do_contours: bool = False
    contour_intervals: list = field(default_factory=lambda: [0.5, 2, 5, 10])

    save_ground_las: bool = True


@dataclass
class PipelineResult:
    dem_rasters: list[str] = field(default_factory=list)
    smoothed_rasters: list[str] = field(default_factory=list)
    tpi_rasters: list[str] = field(default_factory=list)
    slope_rasters: list[str] = field(default_factory=list)
    aspect_rasters: list[str] = field(default_factory=list)
    height_files: list[str] = field(default_factory=list)
    ground_las: list[str] = field(default_factory=list)


class ReliefPipeline:
    """Конвейер: crop → filter → ЦМР → smooth (с интерполяцией дырок) → TPI → slopes → aspects."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.result = PipelineResult()

    def _get_las_files(self) -> list[str]:
        catalog = Path(self.config.las_catalog)
        files = sorted(list(catalog.glob("*.las")) + list(catalog.glob("*.laz")))
        return [str(f) for f in files]

    def _apply_filter(self, las_path: str) -> str:
        if self.config.filter_type is None:
            return las_path
        out_dir = Path(self.config.output_dir)
        stem = Path(las_path).stem
        out_path = str(out_dir / (stem + "_filtered.las"))
        if self.config.filter_type == "manual":
            f = ManualFilter(las_path, self.config.resolution, self.config.z_min, self.config.z_max, out_path)
        elif self.config.filter_type == "stat":
            f = StatFilter(las_path, self.config.resolution, self.config.stat_m, out_path)
        elif self.config.filter_type == "range":
            f = RangeFilter(las_path, self.config.resolution, self.config.range_min_pct, self.config.range_max_pct, out_path)
        elif self.config.filter_type == "outlier":
            f = OutlierFilter(las_path, self.config.resolution, self.config.outlier_neighbours, self.config.outlier_multiplier, out_path)
        else:
            return las_path
        f.filter()
        return out_path

    def _crop_las(self, las_path: str) -> str:
        if self.config.aoi is None:
            return las_path
        out_dir = Path(self.config.output_dir)
        stem = Path(las_path).stem
        out_path = str(out_dir / (stem + "_cropped.las"))
        Crop(vls_cropped=out_path, vls_path=las_path, shapefile=self.config.aoi).cropCalc()
        return out_path

    def run(self) -> PipelineResult:
        os.makedirs(self.config.output_dir, exist_ok=True)
        las_files = self._get_las_files()

        ground = GroundProcessing(
            output=self.config.output_dir,
            resolution=self.config.resolution,
            crs=self.config.crs,
            interpolate=self.config.interpolate,
            interpol_dist=self.config.interpol_dist,
            save_ground_las=self.config.save_ground_las,
            smrf=self.config.smrf,
            fill=FillConfig(
                fill_holes=self.config.fill_holes,
                max_search_distance=self.config.interpol_dist,
                fallback_to_min_z=self.config.fallback_to_min_z,
            ),
        )

        curvature = CurvatureProcessing()

        for las_path in las_files:
            cropped = self._crop_las(las_path)
            filtered = self._apply_filter(cropped)

            ground_path = None
            if self.config.save_ground_las:
                stem = Path(las_path).stem
                ground_path = str(Path(self.config.output_dir) / (stem + "_ground.las"))
            ground.get_raster(filtered, crs_wkt=self.config.crs, out_path=ground_path)

            smoothed_raster = None
            if self.config.smoothing_method == "gauss" and self.config.gauss_sigma is not None:
                for raster in ground.raster[-1:]:
                    stem = Path(raster).stem.replace("_dem", "")
                    smoothed_raster = os.path.join(self.config.output_dir, stem + "_dem_smooth.tif")
                    gauss_smooth(
                        raster=raster, smoothed=smoothed_raster,
                        sigma=self.config.gauss_sigma * self.config.resolution,
                        order=self.config.gauss_order, window_size=self.config.gauss_window,
                        fill_holes=self.config.gauss_fill_holes,
                        max_search_distance=self.config.interpol_dist,
                    )
                    self.result.smoothed_rasters.append(smoothed_raster)
            elif self.config.smoothing_method == "median" and self.config.median_window > 0:
                for raster in ground.raster[-1:]:
                    smoothed_raster = os.path.join(self.config.output_dir,
                                                  Path(raster).stem + "_dem_smooth.tif")
                    import shutil
                    shutil.copy2(raster, smoothed_raster)
                    med_filter(smoothed_raster, self.config.median_window)
                    self.result.smoothed_rasters.append(smoothed_raster)

            # Базовый растр для slopes/aspect — сглаженный если есть, иначе сырой (#4)
            base_raster = smoothed_raster if smoothed_raster else ground.raster[-1]

            # TPI — по сглаженной DTM
            if self.config.do_tpi:
                tpi_out = calculate_tpi(
                    dem_path=base_raster,
                    crs=self.config.crs,
                    output_folder=self.config.output_dir,
                    input_res=self.config.resolution,
                    res=self.config.tpi.res,
                    config=self.config.tpi,
                )
                self.result.tpi_rasters.append(tpi_out)

            # Уклоны — по сглаженной DTM (#4)
            if self.config.do_slopes:
                slope = curvature.calculate_slope(
                    base_raster, self.config.crs,
                    self.config.resolution, self.config.resolution, self.config.output_dir)
                self.result.slope_rasters.append(slope)

            # Экспозиции — по сглаженной DTM (#4)
            if self.config.do_aspects:
                aspect = curvature.calculate_aspect(
                    base_raster, self.config.crs,
                    self.config.resolution, self.config.resolution, self.config.output_dir)
                self.result.aspect_rasters.append(aspect)

            # Высоты
            if self.config.do_heights and ground_path:
                stem = Path(las_path).stem
                heights_path = os.path.join(self.config.output_dir, stem + "_alt.geojson")
                get_every_nth(ground_path, self.config.height_step, heights_path, self.config.crs)
                self.result.height_files.append(heights_path)

            if self.config.do_contours and base_raster:
                stem = Path(las_path).stem
                for interval in self.config.contour_intervals:
                    contour_path = os.path.join(self.config.output_dir,
                                                f"{stem}_contours_{interval}.gpkg")
                    generate_contours(
                        raster_path=base_raster,
                        interval=interval,
                        output_path=contour_path,
                        crs_wkt=self.config.crs,
                    )

        self.result.dem_rasters = ground.raster
        return self.result