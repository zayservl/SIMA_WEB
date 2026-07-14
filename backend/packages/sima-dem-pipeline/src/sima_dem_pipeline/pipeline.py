"""Оркестрация конвейера рельефа.

Порт из legacy `relief_analysis/relief.py::pipeline()`. Без QGIS/PyQt.
Управляет последовательностью: crop → filter → ЦМР → smooth → TPI → slopes → aspects.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from sima_dem_ground.ground import GroundProcessing
from sima_dem_core.curvature import CurvatureProcessing
from sima_dem_core.raster.smooth import gauss_smooth
from sima_dem_core.raster.tpi import calculate_tpi
from sima_dem_core.filters import ManualFilter, StatFilter, RangeFilter, OutlierFilter
from sima_dem_core.crop import Crop
from sima_dem_core.height import get_every_nth


@dataclass
class PipelineConfig:
    """Конфигурация конвейера рельефа."""
    las_catalog: str
    output_dir: str
    resolution: float
    crs: str
    aoi: Optional[str] = None
    filter_type: Optional[str] = None  # "manual", "stat", "range", "outlier", None
    z_min: float = 0.0
    z_max: float = 1000.0
    stat_m: float = 2.0
    range_min_pct: float = 0.0
    range_max_pct: float = 1.0
    outlier_neighbours: int = 8
    outlier_multiplier: float = 2.0
    gauss_sigma: Optional[float] = None
    gauss_order: int = 0
    gauss_window: int = 5
    interpolate: bool = False
    interpol_dist: int = 100
    do_tpi: bool = False
    tpi_res: float = 10.0
    do_slopes: bool = False
    do_aspects: bool = False
    do_heights: bool = False
    height_step: int = 10
    save_ground_las: bool = True


@dataclass
class PipelineResult:
    """Результат конвейера рельефа."""
    dem_rasters: list[str] = field(default_factory=list)
    smoothed_rasters: list[str] = field(default_factory=list)
    tpi_rasters: list[str] = field(default_factory=list)
    slope_rasters: list[str] = field(default_factory=list)
    aspect_rasters: list[str] = field(default_factory=list)
    height_files: list[str] = field(default_factory=list)
    ground_las: list[str] = field(default_factory=list)


class ReliefPipeline:
    """Конвейер рельефа: crop → filter → ЦМР → smooth → TPI → slopes → aspects → heights."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.result = PipelineResult()

    def _get_las_files(self) -> list[str]:
        """Найти все .las/.laz файлы в каталоге."""
        catalog = Path(self.config.las_catalog)
        files = sorted(list(catalog.glob("*.las")) + list(catalog.glob("*.laz")))
        return [str(f) for f in files]

    def _apply_filter(self, las_path: str) -> str:
        """Применить выбранный фильтр к LAS-файлу, вернуть путь к отфильтрованному."""
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
        """Обрезать LAS по AOI, если задан."""
        if self.config.aoi is None:
            return las_path
        out_dir = Path(self.config.output_dir)
        stem = Path(las_path).stem
        out_path = str(out_dir / (stem + "_cropped.las"))
        crop = Crop(vls_cropped=out_path, vls_path=las_path, shapefile=self.config.aoi)
        crop.cropCalc()
        return out_path

    def run(self) -> PipelineResult:
        """Запустить конвейер рельефа."""
        os.makedirs(self.config.output_dir, exist_ok=True)
        las_files = self._get_las_files()

        ground = GroundProcessing(
            output=self.config.output_dir,
            resolution=self.config.resolution,
            crs=self.config.crs,
            interpolate=self.config.interpolate,
            interpol_dist=self.config.interpol_dist,
            save_ground_las=self.config.save_ground_las,
        )

        curvature = CurvatureProcessing()

        for las_path in las_files:
            # 1. Crop по AOI
            cropped = self._crop_las(las_path)

            # 2. Фильтрация
            filtered = self._apply_filter(cropped)

            # 3. ЦМР
            ground_path = None
            if self.config.save_ground_las:
                stem = Path(las_path).stem
                ground_path = str(Path(self.config.output_dir) / (stem + "_ground.las"))
            ground.get_raster(filtered, crs_wkt=self.config.crs, out_path=ground_path)

            # 4. Сглаживание
            if self.config.gauss_sigma is not None:
                for raster in ground.raster[-1:]:
                    stem = Path(raster).stem.replace("_dem", "")
                    smoothed = os.path.join(self.config.output_dir, stem + "_dem_smooth.tif")
                    gauss_smooth(
                        raster=raster,
                        smoothed=smoothed,
                        sigma=self.config.gauss_sigma * self.config.resolution,
                        order=self.config.gauss_order,
                        window_size=self.config.gauss_window,
                    )
                    self.result.smoothed_rasters.append(smoothed)

            # 5. TPI
            if self.config.do_tpi:
                for raster in ground.raster[-1:]:
                    tpi_out = calculate_tpi(
                        dem_path=raster,
                        crs=self.config.crs,
                        output_folder=self.config.output_dir,
                        input_res=self.config.resolution,
                        res=self.config.tpi_res,
                    )
                    self.result.tpi_rasters.append(tpi_out)

            # 6. Уклоны
            if self.config.do_slopes:
                for raster in ground.raster[-1:]:
                    slope = curvature.calculate_slope(
                        raster, self.config.crs, self.config.resolution, self.config.resolution, self.config.output_dir
                    )
                    self.result.slope_rasters.append(slope)

            # 7. Экспозиции
            if self.config.do_aspects:
                for raster in ground.raster[-1:]:
                    aspect = curvature.calculate_aspect(
                        raster, self.config.crs, self.config.resolution, self.config.resolution, self.config.output_dir
                    )
                    self.result.aspect_rasters.append(aspect)

            # 8. Отметки высот
            if self.config.do_heights and ground_path:
                stem = Path(las_path).stem
                heights_path = os.path.join(self.config.output_dir, stem + "_alt.geojson")
                get_every_nth(ground_path, self.config.height_step, heights_path, self.config.crs)
                self.result.height_files.append(heights_path)

        self.result.dem_rasters = ground.raster
        return self.result