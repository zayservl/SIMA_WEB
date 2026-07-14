"""Склоны/Формы рельефа — slope & aspect через gdal.DEMProcessing.

Порт из legacy `processings/SFR.py`. Без QGIS.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from osgeo import gdal


class CurvatureProcessing:
    """Расчёт уклонов и экспозиций (aspect) из ЦМР."""

    def __init__(self) -> None:
        self.slopes: list[str] = []
        self.aspects: list[str] = []

    def _set_projection(self, raster: str, crs_wkt: Optional[str], x_res: float, y_res: float) -> None:
        if crs_wkt is None:
            return
        infn = raster.replace(".tif", "_tmp.tif")
        os.rename(raster, infn)
        try:
            ds = gdal.Warp(raster, infn, resampleAlg="near", xRes=x_res, yRes=y_res)
            ds = gdal.Open(raster, gdal.GA_Update)
            if ds is not None:
                ds.SetProjection(crs_wkt)
                ds = None
        except Exception as ee:  # noqa: BLE001
            print("gdal SetSpatialRef,", ee)
        finally:
            ds = None
            if os.path.exists(infn):
                os.remove(infn)

    def calculate_slope(
        self,
        raster: str,
        crs: Optional[str],
        x_res: float,
        y_res: float,
        out_folder: Optional[str] = None,
    ) -> str:
        filename, file_extension = os.path.splitext(raster)
        if out_folder:
            stem = Path(raster).stem
            stem = stem.rsplit("_dem", 1)[0] if "_dem" in stem else stem
            output = os.path.join(out_folder, stem + "_slope" + file_extension)
        else:
            output = filename.rstrip("dem") + "slope" + file_extension
        gdal.DEMProcessing(output, raster, "slope", format="GTiff")
        self._set_projection(output, crs, x_res, y_res)
        self.slopes.append(output)
        return output

    def calculate_aspect(
        self,
        raster: str,
        crs: Optional[str],
        x_res: float,
        y_res: float,
        out_folder: Optional[str] = None,
    ) -> str:
        filename, file_extension = os.path.splitext(raster)
        if out_folder:
            stem = Path(raster).stem
            stem = stem.rsplit("_dem", 1)[0] if "_dem" in stem else stem
            output = os.path.join(out_folder, stem + "_aspect" + file_extension)
        else:
            output = filename.rstrip("dem") + "aspect" + file_extension
        gdal.DEMProcessing(output, raster, "aspect", format="GTiff")
        self._set_projection(output, crs, x_res, y_res)
        self.aspects.append(output)
        return output