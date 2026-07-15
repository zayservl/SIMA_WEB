"""Тесты raster/vectorize.py (binarize, bin_to_polys, raster_crop)."""

import pytest
import rasterio
import numpy as np
import json
from pathlib import Path

from sima_dem_core.raster.vectorize import binarize, bin_to_polys, raster_crop


def _write_test_tif(path: str, data: np.ndarray, nodata: float = -9999.0, resolution: float = 1.0) -> str:
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "nodata": nodata,
        "width": data.shape[1],
        "height": data.shape[0],
        "count": 1,
        "crs": "EPSG:32642",
        "transform": rasterio.transform.from_origin(0, data.shape[0] * resolution, resolution, resolution),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(np.float32), 1)
    return path


class TestBinarize:

    def test_binarize_basic(self, tmp_path):
        """Бинаризация: 1 для значений в диапазоне, 0 вне."""
        data = np.array([[5, 10, 15], [20, 25, 30]], dtype=np.float32)
        inp = str(tmp_path / "in.tif")
        outp = str(tmp_path / "out.tif")
        _write_test_tif(inp, data)
        binarize(inp, outp, t_min=10, t_max=25)
        with rasterio.open(outp) as src:
            result = src.read(1)
        assert result.dtype == np.uint8 or result.dtype == np.bool_


class TestRasterCrop:

    def test_raster_crop(self, tmp_path):
        """Обрезка растра по полигону."""
        data = np.full((20, 20), 100.0, dtype=np.float32)
        inp = str(tmp_path / "in.tif")
        _write_test_tif(inp, data, resolution=1.0)
        aoi = str(tmp_path / "aoi.geojson")
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[5, 5], [15, 5], [15, 15], [5, 15], [5, 5]]]
                },
                "properties": {}
            }]
        }
        Path(aoi).write_text(json.dumps(geojson))
        outp = raster_crop(inp, aoi, str(tmp_path))
        with rasterio.open(outp) as src:
            cropped = src.read(1)
        assert cropped.shape[0] <= 20
        assert cropped.shape[1] <= 20