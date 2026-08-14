"""Запись деревьев и крон в shapefile."""

from __future__ import annotations

import os

import numpy as np
import pytest
from osgeo import ogr

from sima_forest_cmd import estimate_stem_diameter, write_crown_polygons, write_tree_points


def read_layer(path):
    ds = ogr.Open(path)
    layer = ds.GetLayer()
    fields = [layer.GetLayerDefn().GetFieldDefn(i).GetName()
              for i in range(layer.GetLayerDefn().GetFieldCount())]
    rows = [{f: feat.GetField(f) for f in fields} for feat in layer]
    count = len(rows)
    ds = None
    return fields, rows, count


class TestPoints:
    def test_запись_вершин_с_атрибутами(self, tmp_path):
        out = str(tmp_path / "tops_localMax.shp")
        xyz = np.array([[100.0, 200.0, 15.0], [110.0, 210.0, 8.0]])
        write_tree_points(xyz, out, attributes={
            "hght": xyz[:, 2],
            "crown": np.array([12.5, 7.0]),
        })

        assert os.path.exists(out)
        fields, rows, count = read_layer(out)
        assert count == 2
        assert "hght" in fields and "crown" in fields
        assert rows[0]["hght"] == pytest.approx(15.0)

    def test_нечисловая_форма_отвергается(self, tmp_path):
        with pytest.raises(ValueError, match=r"\(N,3\)"):
            write_tree_points(np.array([1.0, 2.0]), str(tmp_path / "bad.shp"))

    def test_nan_пишется_как_пусто(self, tmp_path):
        out = str(tmp_path / "diam.shp")
        xyz = np.array([[1.0, 2.0, 3.0]])
        write_tree_points(xyz, out, attributes={
            "diam": estimate_stem_diameter(xyz[:, 2]),
        })
        _, rows, _ = read_layer(out)
        assert rows[0]["diam"] is None

    def test_длинное_имя_поля_обрезается(self, tmp_path):
        out = str(tmp_path / "long.shp")
        write_tree_points(np.array([[1.0, 2.0, 3.0]]), out,
                          attributes={"очень_длинное_имя_поля": np.array([1.0])})
        fields, _, _ = read_layer(out)
        assert all(len(f) <= 10 for f in fields)

    def test_пустой_слой_создаётся(self, tmp_path):
        out = str(tmp_path / "empty.shp")
        write_tree_points(np.empty((0, 3)), out, attributes={"hght": np.empty(0)})
        _, _, count = read_layer(out)
        assert count == 0


class TestPolygons:
    def test_запись_крон(self, tmp_path):
        out = str(tmp_path / "crowns_treesWS.shp")
        geom = {"type": "Polygon", "coordinates": [
            [(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0), (0.0, 0.0)]]}
        write_crown_polygons([geom], out, attributes={"hght": np.array([12.0])})

        fields, rows, count = read_layer(out)
        assert count == 1
        assert rows[0]["hght"] == pytest.approx(12.0)

    def test_перезапись_существующего(self, tmp_path):
        out = str(tmp_path / "again.shp")
        geom = {"type": "Polygon", "coordinates": [
            [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]]}
        write_crown_polygons([geom], out)
        write_crown_polygons([geom, geom], out)
        _, _, count = read_layer(out)
        assert count == 2


class TestDiameter:
    def test_заглушка_возвращает_nan_нужной_длины(self):
        result = estimate_stem_diameter(np.array([10.0, 12.0, 15.0]))
        assert result.shape == (3,)
        assert np.all(np.isnan(result))
