"""Тесты crop.py (обрезка LAS по полигону)."""

import pytest
import laspy
import numpy as np
import json
from pathlib import Path

from sima_dem_core.crop import Crop


def _make_las(path: str, n: int = 100) -> str:
    """Создать LAS с точками по сетке 10x10."""
    las = laspy.create(point_format=3, file_version="1.2")
    xs = np.repeat(np.linspace(0, 100, 10), 10)
    ys = np.tile(np.linspace(0, 100, 10), 10)
    las.x = xs
    las.y = ys
    las.z = np.linspace(0, 50, n, dtype=np.float64)
    las.classification = np.array([2] * n, dtype=np.uint8)
    las.write(path)
    return path


def _make_aoi(path: str, bounds: tuple[float, float, float, float]) -> str:
    """Создать GeoJSON-полигон AOI."""
    minx, miny, maxx, maxy = bounds
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]
            },
            "properties": {}
        }]
    }
    Path(path).write_text(json.dumps(geojson))
    return path


class TestCrop:

    def test_crop_basic(self, tmp_path):
        """Обрезка LAS по полигону оставляет только точки внутри."""
        inp = str(tmp_path / "test.las")
        _make_las(inp, n=100)
        aoi = str(tmp_path / "aoi.geojson")
        _make_aoi(aoi, (20, 20, 80, 80))
        outp = str(tmp_path / "cropped.las")
        crop = Crop(vls_cropped=outp, vls_path=inp, shapefile=aoi)
        crop.cropCalc()
        result = laspy.read(outp)
        x = np.asarray(result.x)
        y = np.asarray(result.y)
        assert len(x) > 0
        assert np.all(x >= 20) and np.all(x <= 80)
        assert np.all(y >= 20) and np.all(y <= 80)

    def test_crop_no_intersection(self, tmp_path):
        """AOI вне области точек → пустой результат."""
        inp = str(tmp_path / "test.las")
        _make_las(inp, n=100)
        aoi = str(tmp_path / "aoi.geojson")
        _make_aoi(aoi, (200, 200, 300, 300))
        outp = str(tmp_path / "empty_cropped.las")
        crop = Crop(vls_cropped=outp, vls_path=inp, shapefile=aoi)
        crop.cropCalc()
        # Файл может не существовать или быть пустым
        if Path(outp).exists():
            result = laspy.read(outp)
            assert len(result.points) == 0