"""Горизонтали (изолинии) из ЦМР.

Порт из legacy `relief_analysis/relief.py::horizontals()` (QGIS gdal:contour).
Использует gdal.ContourGenerate напрямую — без зависимости от QGIS.
"""

from __future__ import annotations

import os
from osgeo import gdal, ogr, osr


def generate_contours(
    raster_path: str,
    interval: float,
    output_path: str,
    crs_wkt: str | None = None,
    field_name: str = "alt",
    offset: float = 0.0,
    base: float = 0.0,
    fixed_levels: list[float] | None = None,
    create_3d: bool = True,
    nodata: float | None = None,
    driver: str = "GPKG",
) -> str:
    """Сгенерировать горизонтали (изолинии) из ЦМР.

    Args:
        driver: "GPKG" (по умолчанию) или "ESRI Shapefile" для вывода .shp
                (требование Q3 — горизонтали .shp). Имя поля обрезается до 10
                символов для Shapefile (ограничение DBF).
    """
    ds = gdal.Open(raster_path)
    if ds is None:
        raise FileNotFoundError(f"Cannot open raster: {raster_path}")

    band = ds.GetRasterBand(1)
    ogr_driver = ogr.GetDriverByName(driver)
    if ogr_driver is None:
        raise ValueError(f"Неизвестный OGR-драйвер: {driver}")
    if os.path.exists(output_path):
        ogr_driver.DeleteDataSource(output_path)

    ds_out = ogr_driver.CreateDataSource(output_path)
    layer_name = os.path.splitext(os.path.basename(output_path))[0]
    if driver == "ESRI Shapefile":
        layer_name = layer_name[:10]
        field_name = field_name[:10]
    srs = None
    if crs_wkt:
        srs = osr.SpatialReference()
        srs.ImportFromWkt(crs_wkt)
    geom_type = ogr.wkbLineString25D if create_3d else ogr.wkbLineString
    layer = ds_out.CreateLayer(layer_name, srs=srs, geom_type=geom_type)
    field_idx = layer.CreateField(ogr.FieldDefn(field_name, ogr.OFTReal))

    use_nodata = 1 if nodata is not None else 0
    nd_val = nodata if nodata is not None else 0.0
    elev_field_idx = field_idx

    if fixed_levels:
        for lv in sorted(fixed_levels):
            gdal.ContourGenerate(band, 0.0, lv, [lv], use_nodata, nd_val,
                                 layer, 0, elev_field_idx)
    else:
        gdal.ContourGenerate(band, interval, base, [], use_nodata, nd_val,
                             layer, 0, elev_field_idx)

    ds_out = None
    ds = None
    return output_path