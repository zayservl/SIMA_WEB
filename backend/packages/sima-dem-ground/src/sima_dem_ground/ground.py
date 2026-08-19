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
from osgeo import gdal

from sima_dem_core.check_classification import CheckClassification
from sima_dem_core.raster.holes import fill_voids, px_from_metres


@dataclass
class SMRFConfig:
    """Параметры фильтра SMRF для классификации точек земли."""

    slope: float = 0.2
    window: int = 16
    threshold: float = 0.45
    scalar: float = 1.2
    returns: list = field(default_factory=lambda: ["first", "last", "intermediate", "only"])
    # Порог SMRF в cut-режиме: единственный параметр, который легаси задавало
    # в упрощённом варианте (`cut_smrf`), остальные брались по умолчанию PDAL.
    cut_threshold: float = 3.0

    def to_dict(self) -> dict:
        """Словарь параметров для filters.smrf в полном режиме."""
        return {"type": "filters.smrf", "slope": self.slope, "window": self.window,
                "threshold": self.threshold, "scalar": self.scalar, "returns": self.returns}

    def to_cut_dict(self) -> dict:
        """Словарь параметров для filters.smrf в cut-режиме."""
        return {"type": "filters.smrf", "threshold": self.cut_threshold, "returns": self.returns}


@dataclass
class FillConfig:
    """Параметры интерполяции пустот в растре ЦМР."""

    fill_holes: bool = True
    max_search_distance: int = 100
    smoothing_iterations: int = 0
    fallback_to_min_z: bool = True
    # Метод интерполяции пустот: "laplace" (гладко) или "idw" (GDALFillNodata,
    # даёт радиальные лучи внутрь крупных пустот).
    fill_method: str = "laplace"
    # Проходов заполнения пустот; 1 — историческое однопроходное поведение.
    fill_passes: int = 3
    # Пустоты-водоёмы получают плоскую отметку вместо интерполяции (3DEP
    # hydro-flattening). См. sima_dem_core.raster.hydro.
    hydro_flatten: bool = True
    # Насколько (в метрах) допустимо экстраполировать за границу валидной
    # области. 0 — только внутренние дыры, как было исторически; такое
    # поведение выбрасывало все пустоты, касающиеся рамки растра, даже
    # вплотную к данным. См. sima_dem_core.raster.holes.
    edge_extrapolation_m: float = 5.0
    # Сохранять рядом с растром маску измеренных ячеек `<stem>_dem_measured.tif`
    # (uint8: 1 — значение получено растеризацией точек, 0 — заполнено). После
    # заполнения пустот отличить одно от другого по самому растру уже нельзя,
    # а для оценки точности и для отчёта заказчику это разные величины.
    save_measured_mask: bool = False


@dataclass
class RasterOutputConfig:
    """Параметры записи растра через writers.gdal."""

    output_type: str = "idw"
    data_type: str = "float32"
    gdaldriver: str = "GTiff"


def _fix_returns_stage() -> dict:
    return {"type": "filters.assign", "value": [
        "NumberOfReturns = 1 WHERE (NumberOfReturns == 0)",
        "ReturnNumber = 1 WHERE (ReturnNumber == 0)"]}


def _elm_outlier_stages(elm: bool = True, outlier: bool = True) -> list[dict]:
    """Стадии отсева шума перед классификацией земли.

    Оба фильтра отключаемы: контракт (`SmrfParams.elm` / `SmrfParams.outlier`)
    даёт их как самостоятельные флаги.
    """
    stages: list[dict] = []
    if elm:
        stages.append({"type": "filters.elm"})
    if outlier:
        stages.append({"type": "filters.outlier"})
    return stages


def _writers_gdal_stage(filename: str, cfg: RasterOutputConfig, resolution: float) -> dict:
    return {"filename": filename, "gdaldriver": cfg.gdaldriver,
            "resolution": resolution, "output_type": cfg.output_type,
            "type": "writers.gdal", "data_type": cfg.data_type}


class GroundProcessing:
    """Оркестрация построения ЦМР из LAS через PDAL-пайплайны."""

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
        elm: bool = True,
        outlier: bool = True,
    ) -> None:
        """Инициализация параметров обработки точек в ЦМР."""
        self.raster: list[str] = []
        self.classified_ground: Optional[str] = None
        self.measured_mask: Optional[str] = None  # путь маски измеренных ячеек
        self.water_levels: list[float] = []   # отметки гидровыравненных водоёмов, м
        self.aoi = aoi
        self.output_folder = str(output)
        self.resolution = resolution
        self.crs = crs
        self.interpolate = interpolate
        self.is_CRS_EPSG = is_CRS_EPSG if is_CRS_EPSG is not None else self._detect_crs_is_epsg(crs)
        self.cut_smrf = cut_smrf
        self.save_ground_las = save_ground_las
        self.elm = elm
        self.outlier = outlier
        self.smrf = smrf or SMRFConfig()
        self.fill = fill or FillConfig(max_search_distance=interpol_dist)
        self.raster_out = raster_out or RasterOutputConfig()

    @staticmethod
    def _detect_crs_is_epsg(crs: str) -> bool:
        """Определяет, является ли строка CRS EPSG-кодом."""
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
        """Выполняет PDAL-пайплайн, сериализованный в JSON."""
        pdal.Pipeline(json.dumps(pipeline)).execute()

    def _maybe_crop_stage(self) -> list[dict]:
        """Возвращает стадию crop по AOI, если CRS — EPSG."""
        if self.aoi and self.is_CRS_EPSG:
            return [{"type": "filters.crop", "polygon": self.aoi}]
        return []

    def _build_ground_pipeline(self, input_path: str, raster: str, out_path: Optional[str]) -> list[dict]:
        """Собирает пайплайн классификации земли SMRF и записи растра."""
        smrf_stage = self.smrf.to_cut_dict() if self.cut_smrf else self.smrf.to_dict()
        pipeline = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            _fix_returns_stage(),
            {"type": "filters.assign", "assignment": "Classification[:]=0"},
        ]
        pipeline += self._maybe_crop_stage()
        pipeline += _elm_outlier_stages(self.elm, self.outlier)
        pipeline.append(smrf_stage)
        pipeline.append({"type": "filters.sample", "radius": self.resolution})
        pipeline.append({"type": "filters.range", "limits": "Classification[2:2]"})
        if self.save_ground_las:
            ground_las = out_path or (input_path.rsplit(".", 1)[0] + "_ground.las")
            pipeline.append({"type": "writers.las", "filename": ground_las})
        pipeline.append(_writers_gdal_stage(raster, self.raster_out, self.resolution))
        return pipeline

    def _build_save_ground_pipeline(self, input_path: str, raster: str, out_path: Optional[str]) -> list[dict]:
        """Собирает пайплайн для уже классифицированного LAS с сохранением ground."""
        pipeline = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            _fix_returns_stage(),
        ]
        if self.save_ground_las:
            ground_las = out_path or (input_path.rsplit(".", 1)[0] + "_ground.las")
            pipeline.append({"type": "filters.assign", "value": ["Classification = 1 WHERE Classification != 2"]})
            pipeline.append({"type": "writers.las", "filename": ground_las})
        pipeline += self._maybe_crop_stage()
        # elm/outlier должны отработать до финального range-отбора Classification==2,
        # иначе точки, помеченные ими как шум (класс 7), не отсеиваются перед растеризацией.
        pipeline += _elm_outlier_stages(self.elm, self.outlier)
        pipeline.append({"type": "filters.sample", "radius": self.resolution})
        pipeline.append({"type": "filters.range", "limits": "Classification[2:2]"})
        pipeline.append(_writers_gdal_stage(raster, self.raster_out, self.resolution))
        return pipeline

    def _build_min_z_pipeline(self, input_path: str, raster_path: str) -> list[dict]:
        """Собирает пайплайн растра минимальных высот для заполнения пустот."""
        check = CheckClassification(input_path)
        pipeline = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            _fix_returns_stage(),
        ]
        pipeline += self._maybe_crop_stage()
        if not check.is_ground:
            pipeline += _elm_outlier_stages(self.elm, self.outlier)
            pipeline.append(self.smrf.to_cut_dict() if self.cut_smrf else self.smrf.to_dict())
        pipeline.append({"type": "filters.range", "limits": "Classification[2:2]"})
        pipeline.append({"type": "filters.sample", "radius": self.resolution})
        min_cfg = RasterOutputConfig(output_type="min", data_type=self.raster_out.data_type,
                                     gdaldriver=self.raster_out.gdaldriver)
        pipeline.append(_writers_gdal_stage(raster_path, min_cfg, self.resolution))
        return pipeline

    def _build_coverage_pipeline(self, input_path: str, raster_path: str) -> list[dict]:
        """Собирает пайплайн растра числа возвратов любого класса.

        Ни SMRF, ни отбора по классам: нужна фактическая освещённость сканером,
        а не земля. Ячейка без единого возврата — кандидат в водоём (вода не
        отражает импульс), см. `sima_dem_core.raster.hydro`.
        """
        pipeline = [
            {"type": "readers.las", "filename": input_path, "override_srs": self.crs},
            _fix_returns_stage(),
        ]
        pipeline += self._maybe_crop_stage()
        cfg = RasterOutputConfig(output_type="count", data_type="float32",
                                 gdaldriver=self.raster_out.gdaldriver)
        pipeline.append(_writers_gdal_stage(raster_path, cfg, self.resolution))
        return pipeline

    def _no_return_mask(self, input_path: str, raster: str) -> Optional[np.ndarray]:
        """Маска ячеек ЦМР, куда не попало ни одного возврата ВЛС.

        Возвращает None, если растр покрытия построить не удалось — тогда
        гидровыравнивание просто не выполняется (лучше пустота, чем плоскость
        не по воде).
        """
        cover_raster = raster.replace("_dem.tif", "_coverage.tif")
        try:
            self._run_pdal(self._build_coverage_pipeline(input_path, cover_raster))
            with rasterio.open(raster) as ref:
                shape, ref_transform = ref.shape, ref.transform
            with rasterio.open(cover_raster) as src:
                count = src.read(1)
                nodata = src.nodata
                same_grid = (src.shape == shape
                             and np.allclose(np.asarray(src.transform)[:6],
                                             np.asarray(ref_transform)[:6]))
            if not same_grid:
                return None
            hit = count > 0
            if nodata is not None:
                hit &= count != nodata
            return ~hit
        except Exception:  # noqa: BLE001 — вспомогательный растр не должен ронять расчёт
            return None
        finally:
            self._cleanup_temp(cover_raster)

    def _fill_from_min_z(self, input_path: str, raster: str) -> None:
        """Заполняет пустоты ЦМР значениями минимальных высот из отдельного растра."""
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
        """Удаляет временные файлы, игнорируя ошибки."""
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _set_projection(self, raster: str, crs_wkt: Optional[str]) -> None:
        """Прописывает проекцию в растр GDAL, если WKT задан."""
        if raster is None or crs_wkt is None:
            return
        try:
            ds = gdal.Open(raster, gdal.GA_Update)
            if ds is not None:
                ds.SetProjection(crs_wkt)
                ds = None
        except Exception as ee:
            print("gdal SetProjection failed:", ee)

    def _interpolate(self, raster: str, input_path: Optional[str] = None) -> None:
        """Интерполирует пустоты растра через fillnodata.

        Заполняются внутренние дыры и, если задан `fill.edge_extrapolation_m`,
        пустоты не далее этого расстояния от валидных данных. Проходов —
        `fill.fill_passes`: часть пустот замыкается в дыру только после
        заполнения соседних (см. sima_dem_core.raster.holes.fill_voids).

        При `fill.hydro_flatten` кандидаты в водоёмы ограничиваются ячейками без
        единого возврата ВЛС: валидная маска ЦМР — редкая сетка ground-ячеек, и
        без этого ограничения «лакуной» оказывается почти весь лист.
        """
        with rasterio.open(raster) as src:
            profile = src.profile
            arr = src.read(1)
            nodata = src.nodata
            mask = src.read_masks(1)

        if nodata is None:
            return

        # Без исходного облака судить о воде нечем — гидровыравнивание пропускается.
        water = (self._no_return_mask(input_path, raster)
                 if self.fill.hydro_flatten and input_path else None)

        result = fill_voids(
            arr, mask == 255,
            method=self.fill.fill_method,
            max_search_distance=self.fill.max_search_distance,
            smoothing_iterations=self.fill.smoothing_iterations,
            max_extrapolation_px=px_from_metres(
                self.fill.edge_extrapolation_m, self.resolution),
            max_passes=self.fill.fill_passes,
            resolution_m=self.resolution,
            hydro_flatten=self.fill.hydro_flatten and water is not None,
            water=water,
        )
        if not np.any(result.filled):
            return
        self.water_levels = result.water_levels

        with rasterio.open(raster, "w", **profile) as dest:
            dest.write_band(1, result.array)

    @staticmethod
    def measured_mask_path(raster: str) -> str:
        """Путь маски измеренных ячеек рядом с растром."""
        return raster.replace(".tif", "_measured.tif")

    def _save_measured_mask(self, raster: str) -> Optional[str]:
        """Снять маску валидных ячеек сразу после растеризации и записать её.

        Вызывается до заполнения пустот: позже отличить измеренную ячейку от
        достроенной по самому растру невозможно.
        """
        with rasterio.open(raster) as src:
            profile = src.profile
            mask = (src.read_masks(1) == 255).astype("uint8")
        out = self.measured_mask_path(raster)
        profile.update(dtype="uint8", nodata=None, count=1)
        with rasterio.open(out, "w", **profile) as dst:
            dst.write(mask, 1)
        return out

    def _get_raster_name(self, path: str, out_path: Optional[str]) -> tuple[str, str]:
        """Формирует пути выходного растра ЦМР и сглаженного растра."""
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
        """Основной метод: строит ЦМР из LAS с заполнением пустот и проекцией."""
        check = CheckClassification(path)
        raster, _ = self._get_raster_name(path, out_path)
        if check.is_ground:
            self._run_pdal(self._build_save_ground_pipeline(path, raster, out_path))
        else:
            self._run_pdal(self._build_ground_pipeline(path, raster, out_path))
        if self.fill.save_measured_mask:
            self.measured_mask = self._save_measured_mask(raster)
        if self.fill.fallback_to_min_z:
            self._fill_from_min_z(path, raster)
        if self.interpolate:
            self._interpolate(raster, path)
        self.raster.append(raster)
        if crs_wkt:
            self._set_projection(raster, crs_wkt)