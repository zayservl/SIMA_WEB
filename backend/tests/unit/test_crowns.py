"""Сегментация крон водоразделом и векторизация — на синтетике."""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from sima_forest_cmd import (
    crown_areas_by_tree,
    crowns_to_polygons,
    delineate_crowns,
    detect_tree_tops,
)

from test_treetops import make_chm


class TestDelineation:
    def test_крон_столько_же_сколько_вершин(self):
        centres = [(25, 25), (25, 75), (75, 25), (75, 75)]
        chm = make_chm(centres, sigma=6.0)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=3.0)
        labels = delineate_crowns(chm, tops)

        assert len(tops) == len(centres)
        assert len(np.unique(labels[labels > 0])) == len(centres)

    def test_кроны_не_пересекаются(self):
        # у водораздела каждая ячейка принадлежит ровно одной кроне по построению;
        # проверяем, что маркеры не порождают дублей меток
        chm = make_chm([(30, 30), (30, 70), (70, 50)], sigma=6.0)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=3.0)
        labels = delineate_crowns(chm, tops)
        assert labels.shape == chm.shape
        assert set(np.unique(labels)) <= {0, 1, 2, 3}

    def test_заливка_не_уходит_ниже_полога(self):
        chm = make_chm([(50, 50)], sigma=5.0)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=3.0)
        labels = delineate_crowns(chm, tops, min_height_m=5.0)
        assert np.all(np.nan_to_num(chm)[labels > 0] >= 5.0)

    def test_без_вершин_пустой_результат(self):
        labels = delineate_crowns(np.zeros((20, 20)),
                                  detect_tree_tops(np.zeros((20, 20)), 0.5, 2.0))
        assert labels.max() == 0

    def test_nodata_не_попадает_в_крону(self):
        chm = make_chm([(40, 40)], sigma=5.0)
        chm[10:15, 10:15] = np.nan
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=3.0)
        labels = delineate_crowns(chm, tops)
        assert labels[10:15, 10:15].max() == 0


class TestPolygons:
    def test_полигон_на_каждую_крону(self):
        centres = [(25, 25), (25, 75), (75, 50)]
        chm = make_chm(centres, sigma=6.0)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=3.0)
        labels = delineate_crowns(chm, tops)
        crowns = crowns_to_polygons(labels, from_origin(0.0, 100.0, 0.5, 0.5))

        assert len(crowns) >= len(centres)
        assert set(crowns.tree_index) == set(range(len(centres)))
        assert np.all(crowns.areas_m2 > 0)

    def test_площадь_совпадает_с_числом_ячеек(self):
        labels = np.zeros((20, 20), dtype=np.int32)
        labels[5:11, 5:11] = 1                      # 36 ячеек
        crowns = crowns_to_polygons(labels, from_origin(0.0, 10.0, 0.5, 0.5))
        assert crowns.areas_m2.sum() == pytest.approx(36 * 0.25)

    def test_площадь_за_вычетом_отверстия(self):
        labels = np.zeros((20, 20), dtype=np.int32)
        labels[5:11, 5:11] = 1
        labels[7:9, 7:9] = 0                        # просвет 4 ячейки внутри кроны
        crowns = crowns_to_polygons(labels, from_origin(0.0, 10.0, 0.5, 0.5))
        assert crowns.areas_m2.sum() == pytest.approx((36 - 4) * 0.25)

    def test_пустой_растр_даёт_пустой_список(self):
        crowns = crowns_to_polygons(np.zeros((10, 10), dtype=np.int32),
                                    from_origin(0.0, 5.0, 0.5, 0.5))
        assert len(crowns) == 0


class TestAreasByTree:
    def test_площадь_по_каждому_дереву(self):
        labels = np.zeros((20, 20), dtype=np.int32)
        labels[0:4, 0:4] = 1                        # 16 ячеек
        labels[10:12, 10:12] = 2                    # 4 ячейки
        areas = crown_areas_by_tree(labels, n_trees=2, resolution_m=0.5)
        assert list(areas) == [16 * 0.25, 4 * 0.25]

    def test_дерево_без_кроны_получает_ноль(self):
        labels = np.zeros((10, 10), dtype=np.int32)
        labels[0:2, 0:2] = 1
        areas = crown_areas_by_tree(labels, n_trees=3, resolution_m=1.0)
        assert list(areas) == [4.0, 0.0, 0.0]

    def test_без_деревьев(self):
        assert crown_areas_by_tree(np.zeros((5, 5), dtype=np.int32), 0, 1.0).size == 0
