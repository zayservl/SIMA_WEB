"""Бинаризация и векторизация растров.

Порт из legacy `processings/raster_utils.py::binarize, bin_to_polys, raster_crop`.
Без fiona — rasterio.features.
"""

from __future__ import annotations

import os
import rasterio
import numpy as np
from rasterio import features
from rasterio import mask as rio_mask
import shapely
from shapely.geometry import shape as shp_shape
from pathlib import Path


def binarize(input_raster: str, out_raster: str, t_min: float, t_max: float) -> None:
    """Бинаризовать растр: 1 для пикселей в [t_min, t_max], 0 иначе.

    Args:
        input_raster: входной GeoTIFF
        out_raster: выходной бинарный GeoTIFF
        t_min: минимальный порог
        t_max: максимальный порог
    """
    with rasterio.open(input_raster) as source:
        profile = source.profile
        array = source.read(1).astype(float)
        bin_array = np.array(np.clip(array, t_min, t_max) // t_max, dtype=np.uint8)
        bin_array = np.invert(bin_array.astype(bool)).astype(np.uint8)
        profile.update(dtype="uint8", count=1, nodata=None)
        with rasterio.open(out_raster, "w", **profile) as dst:
            dst.write(bin_array, 1)


def bin_to_polys(path: str, outfolder: str) -> str:
    """Векторизовать бинарный растр в GeoJSON-полигоны.

    Args:
        path: путь к бинарному GeoTIFF
        outfolder: каталог для выходного GeoJSON

    Returns:
        Путь к выходному GeoJSON или пустая строка если нет полигонов.
    """
    outpath = os.path.join(outfolder, Path(path).stem + "_polys.geojson")

    src = rasterio.open(path)
    ar = src.read(1)
    transform = src.transform
    crs = src.crs
    threshold = ar == 1

    all_polygons = []
    for geom, value in features.shapes(mask.astype(np.int16), mask=(mask > 0), transform=transform):
        all_polygons.append(shp_shape(geom))

    if not all_polygons:
        src.close()
        return ""

    multipoly = shapely.geometry.MultiPolygon(all_polygons)
    if not multipoly.is_valid:
        multipoly = multipoly.buffer(0)

    import json
    feature = {
        "type": "Feature",
        "geometry": shapely.geometry.mapping(multipoly),
        "properties": {},
    }
    geojson = {"type": "FeatureCollection", "features": [feature]}
    Path(outpath).write_text(json.dumps(geojson))
    src.close()
    return outpath


def raster_crop(raster: str, shapefile_path: str, out_folder: str) -> str:
    """Обрезать растр по полигону (GeoJSON).

    Args:
        raster: путь к GeoTIFF
        shapefile_path: путь к GeoJSON с полигоном
        out_folder: выходной каталог

    Returns:
        Путь к обрезанному растру.
    """
    import json
    with open(shapefile_path, "r") as f:
        data = json.load(f)
    if data["type"] == "FeatureCollection":
        shapes = [feat["geometry"] for feat in data["features"]]
    else:
        shapes = [data]

    with rasterio.open(raster) as src:
        out_image, out_transform = rio_mask.mask(src, shapes, crop=True)
        out_meta = src.meta

    out_image_path = os.path.join(out_folder, Path(raster).name)
    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
    })
    with rasterio.open(out_image_path, "w", **out_meta) as dest:
        dest.write(out_image)
    return out_image_path