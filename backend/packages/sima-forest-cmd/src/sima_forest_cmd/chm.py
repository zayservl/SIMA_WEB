"""Построение ЦМД — растра высот полога — из облака точек.

ЦМД отличается от ЦММ одним шагом: перед растеризацией высоты нормализуются
относительно земли (`filters.hag_delaunay` строит триангуляцию по точкам земли и
считает превышение над ней, затем `Z` заменяется на это превышение). Поэтому ЦМД
не зависит от абсолютного уровня высот: облако в нормализованных высотах (ТЛО)
даёт тот же результат, что облако в абсолютных отметках.

По той же причине ЦМД не строится вычитанием ЦМР из ЦММ и не требует их наличия:
нормализация выполняется по самому облаку, а не по растрам.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pdal
import rasterio
from osgeo import gdal

from sima_dem_core.raster.holes import fill_voids, px_from_metres

# Классы ASPRS, которыми размечается растительность по высоте над землёй.
CLASS_LOW_VEGETATION = 3
CLASS_MEDIUM_VEGETATION = 4
CLASS_HIGH_VEGETATION = 5

# Границы переклассификации по высоте над землёй, м (легаси СИМА 1.44).
LOW_VEGETATION_MAX_M = 0.5
MEDIUM_VEGETATION_MAX_M = 5.0


@dataclass
class CHMConfig:
    """Параметры построения ЦМД."""

    resolution: float = 0.5
    output_type: str = "max"          # верхняя точка полога в ячейке
    data_type: str = "float32"
    gdaldriver: str = "GTiff"
    # Заполнение пустот полога. Гидровыравнивание не применяется: на растре
    # высот над землёй вода и так близка к нулю, выравнивать нечего.
    interpolate: bool = True
    fill_holes: bool = True
    fill_method: str = "laplace"
    fill_passes: int = 3
    max_search_distance: int = 100
    edge_extrapolation_m: float = 0.0
    # Дополнительные каналы — вход будущей сегментации полога, по умолчанию не нужны.
    with_intensity: bool = False
    with_density: bool = False
    # Сохранять облако с переклассифицированной по высоте растительностью.
    save_classified_las: bool = False
    low_vegetation_max_m: float = LOW_VEGETATION_MAX_M
    medium_vegetation_max_m: float = MEDIUM_VEGETATION_MAX_M


@dataclass
class CHMResult:
    """Пути к выходным растрам и облаку."""

    chm: str
    intensity: Optional[str] = None
    density: Optional[str] = None
    classified_las: Optional[str] = None
    outputs: list = field(default_factory=list)


class CHMBuilder:
    """Построение ЦМД (растра высот полога) из LAS/LAZ."""

    def __init__(
        self,
        output: str | Path,
        crs: str,
        config: Optional[CHMConfig] = None,
        aoi: Optional[str] = None,
    ) -> None:
        self.output_folder = str(output)
        self.crs = crs
        self.config = config or CHMConfig()
        self.aoi = aoi

    @staticmethod
    def execute(pipeline: list) -> None:
        pdal.Pipeline(json.dumps(pipeline)).execute()

    def _build_pipeline(self, input_path: str, paths: CHMResult) -> list:
        """Собрать конвейер PDAL: нормализация высот и растеризация полога."""
        cfg = self.config
        # override_srs добавляется только с непустым значением: PDAL отвергает
        # пустую строку, а СК может отсутствовать — тогда берётся та, что в LAS.
        reader = {"type": "readers.las", "filename": input_path}
        if self.crs:
            reader["override_srs"] = self.crs
        pipeline: list = [
            reader,
            # Нулевые номера возвратов ломают часть фильтров PDAL.
            {"type": "filters.assign", "value": [
                "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
                "ReturnNumber = 1 WHERE (ReturnNumber == 0)"]},
            # Прореживание до разрешения растра — до отсева шума, как в легаси:
            # иначе elm/outlier считают статистику по неравномерной плотности.
            {"type": "filters.sample", "radius": cfg.resolution},
            {"type": "filters.elm"},
            {"type": "filters.outlier"},
            {"type": "filters.hag_delaunay", "allow_extrapolation": "true"},
            # Всё, что не земля, — кандидат в растительность.
            {"type": "filters.assign", "value": [
                "Classification = 1 WHERE Classification != 2"]},
            {"type": "filters.assign", "value": [
                f"Classification = {CLASS_LOW_VEGETATION} WHERE (Classification == 1 "
                f"&& HeightAboveGround > 0 && HeightAboveGround <= {cfg.low_vegetation_max_m})",
                f"Classification = {CLASS_MEDIUM_VEGETATION} WHERE (Classification == 1 "
                f"&& HeightAboveGround > {cfg.low_vegetation_max_m} "
                f"&& HeightAboveGround <= {cfg.medium_vegetation_max_m})",
                f"Classification = {CLASS_HIGH_VEGETATION} WHERE (Classification == 1 "
                f"&& HeightAboveGround > {cfg.medium_vegetation_max_m})",
                "Z = HeightAboveGround"]},
        ]
        if self.aoi:
            pipeline.insert(2, {"type": "filters.crop", "polygon": self.aoi})
        if cfg.save_classified_las and paths.classified_las:
            pipeline.append({"type": "writers.las", "filename": paths.classified_las})

        pipeline.append(self._writer(paths.chm))
        if cfg.with_intensity and paths.intensity:
            pipeline.append(self._writer(paths.intensity, dimension="intensity",
                                         output_type="mean"))
        if cfg.with_density and paths.density:
            pipeline.append({"type": "filters.nndistance", "k": 1})
            pipeline.append(self._writer(paths.density, dimension="NNDistance",
                                         output_type="mean"))
        return pipeline

    def _writer(self, filename: str, dimension: Optional[str] = None,
                output_type: Optional[str] = None) -> dict:
        cfg = self.config
        writer = {
            "type": "writers.gdal", "filename": filename,
            "gdaldriver": cfg.gdaldriver, "resolution": cfg.resolution,
            "output_type": output_type or cfg.output_type,
            "data_type": cfg.data_type,
        }
        if dimension:
            writer["dimension"] = dimension
        return writer

    def _interpolate(self, raster: str) -> None:
        """Заполнить пустоты полога, не трогая измеренные ячейки."""
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
            max_extrapolation_px=px_from_metres(cfg.edge_extrapolation_m, cfg.resolution),
            max_passes=cfg.fill_passes,
            resolution_m=cfg.resolution,
            hydro_flatten=False,
        )
        if not np.any(result.filled):
            return
        with rasterio.open(raster, "w", **profile) as dest:
            dest.write_band(1, result.array)

    def _set_projection(self, raster: str, crs_wkt: Optional[str]) -> None:
        if not raster or not crs_wkt:
            return
        ds = gdal.Open(raster, gdal.GA_Update)
        if ds is not None:
            ds.SetProjection(crs_wkt)
            ds = None

    def build(self, las_path: str, crs_wkt: Optional[str] = None,
              out_path: Optional[str] = None) -> CHMResult:
        """Построить ЦМД из облака точек.

        Args:
            las_path: путь к LAS/LAZ.
            crs_wkt: СК для записи в выходные растры.
            out_path: путь к растру ЦМД; по умолчанию `<output>/<stem>_chm.tif`.

        Returns:
            CHMResult с путями к созданным файлам.
        """
        stem = Path(las_path).stem
        os.makedirs(self.output_folder, exist_ok=True)
        chm = out_path or os.path.join(self.output_folder, stem + "_chm.tif")
        paths = CHMResult(chm=chm)
        if self.config.with_intensity:
            paths.intensity = os.path.join(self.output_folder, stem + "_its.tif")
        if self.config.with_density:
            paths.density = os.path.join(self.output_folder, stem + "_den.tif")
        if self.config.save_classified_las:
            paths.classified_las = os.path.join(self.output_folder, stem + "_veg.las")

        self.execute(self._build_pipeline(las_path, paths))

        if self.config.interpolate:
            self._interpolate(paths.chm)
        for raster in (paths.chm, paths.intensity, paths.density):
            self._set_projection(raster, crs_wkt)

        paths.outputs = [p for p in (paths.chm, paths.intensity, paths.density,
                                     paths.classified_las) if p and os.path.exists(p)]
        return paths


def read_chm(path: str) -> tuple[np.ndarray, object, float]:
    """Прочитать растр ЦМД: массив с NaN вместо nodata, трансформ, разрешение."""
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        return arr, src.transform, float(abs(src.transform.a))
