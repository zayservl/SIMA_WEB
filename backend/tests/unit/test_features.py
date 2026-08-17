"""Признаки крон: геометрия с аналитическим ответом и невоспроизведение легаси-ошибок."""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from sima_forest_cmd import (
    crown_features,
    crown_geometry,
    crown_height_structure,
    crown_point_features,
    vertical_complexity,
)

TRANSFORM = from_origin(0.0, 10.0, 0.5, 0.5)


def square_labels(size=6, shape=(20, 20), start=5):
    labels = np.zeros(shape, dtype=np.int64)
    labels[start:start + size, start:start + size] = 1
    return labels


class TestGeometry:
    def test_площадь_и_периметр_квадрата(self):
        g = crown_geometry(square_labels(), n_trees=1, resolution_m=0.5)
        assert g["area_m2"][0] == pytest.approx(6 * 6 * 0.25)
        assert g["perimeter_m"][0] == pytest.approx(4 * 6 * 0.5)

    def test_эквивалентный_диаметр(self):
        g = crown_geometry(square_labels(), n_trees=1, resolution_m=0.5)
        area = g["area_m2"][0]
        assert g["equivalent_diameter_m"][0] == pytest.approx(2 * np.sqrt(area / np.pi))

    def test_компактность_квадрата(self):
        # для квадрата со ступенчатым периметром 4piA/P^2 = pi/4
        g = crown_geometry(square_labels(), n_trees=1, resolution_m=0.5)
        assert g["compactness"][0] == pytest.approx(np.pi / 4)

    def test_вытянутая_крона_менее_компактна(self):
        labels = np.zeros((20, 20), dtype=np.int64)
        labels[5:7, 2:18] = 1
        thin = crown_geometry(labels, 1, 0.5)["compactness"][0]
        square = crown_geometry(square_labels(), 1, 0.5)["compactness"][0]
        assert thin < square

    def test_смещение_вершины_от_центроида(self):
        labels = square_labels()                       # центроид в (7.5, 7.5)
        g = crown_geometry(labels, 1, resolution_m=0.5,
                           apex_rows=np.array([7.5]), apex_cols=np.array([9.5]))
        assert g["apex_offset_m"][0] == pytest.approx(2 * 0.5)

    def test_дерево_без_ячеек_даёт_нулевую_площадь(self):
        g = crown_geometry(square_labels(), n_trees=3, resolution_m=0.5)
        assert g["area_m2"][1] == 0.0 and g["area_m2"][2] == 0.0


class TestHeightStructure:
    def test_среднее_и_максимум(self):
        labels = square_labels()
        chm = np.zeros((20, 20))
        chm[5:11, 5:11] = np.linspace(1, 12, 36).reshape(6, 6)
        h = crown_height_structure(labels, chm, 1)
        assert h["chm_mean_m"][0] == pytest.approx(6.5)
        assert h["chm_max_m"][0] == pytest.approx(12.0)

    def test_устойчивая_высота_отбрасывает_выброс(self):
        labels = square_labels()
        chm = np.zeros((20, 20))
        chm[5:11, 5:11] = 10.0
        chm[5, 5] = 60.0                               # одиночный выброс ЦМД
        h = crown_height_structure(labels, chm, 1)
        assert h["chm_max_m"][0] == pytest.approx(60.0)
        assert h["height_robust_m"][0] == pytest.approx(10.0)

    def test_p99_на_мелкой_кроне_почти_равен_максимуму(self):
        # 36 ячеек: одиночный выброс попадает выше 97-го перцентиля, поэтому p99
        # устойчивости не даёт — ради этого и введена height_robust_m
        labels = square_labels()
        chm = np.zeros((20, 20))
        chm[5:11, 5:11] = 10.0
        chm[5, 5] = 60.0
        h = crown_height_structure(labels, chm, 1)
        assert h["chm_p99_m"][0] > 40.0

    def test_устойчивая_высота_на_однородной_кроне_равна_максимуму(self):
        labels = square_labels()
        chm = np.zeros((20, 20))
        chm[5:11, 5:11] = 14.0
        h = crown_height_structure(labels, chm, 1)
        assert h["height_robust_m"][0] == pytest.approx(14.0)

    def test_квантили_не_схлопываются_в_минимум(self):
        # легаси считал np.percentile(z, i // 100) -> всегда 0 -> минимум
        labels = square_labels()
        chm = np.zeros((20, 20))
        chm[5:11, 5:11] = np.linspace(1, 12, 36).reshape(6, 6)
        h = crown_height_structure(labels, chm, 1)
        quantiles = [h[f"chm_p{p}_m"][0] for p in (50, 75, 95)]
        assert quantiles == sorted(quantiles)
        assert quantiles[0] > chm[5:11, 5:11].min()


class TestPointFeatures:
    def points(self):
        # девять точек внутри квадрата кроны
        xs = np.full(9, 3.0) + np.arange(9) * 0.01
        ys = np.full(9, 6.5)
        zs = np.linspace(2.0, 18.0, 9)
        return xs, ys, zs

    def test_интенсивность_не_копия_высоты(self):
        # легаси читал интенсивность из размерности Z
        xs, ys, zs = self.points()
        intensity = np.full(9, 250.0)
        f = crown_point_features(square_labels(), TRANSFORM, xs, ys, zs, 1,
                                 intensity=intensity, resolution_m=0.5)
        assert f["intensity_mean"][0] == pytest.approx(250.0)
        assert f["intensity_mean"][0] != pytest.approx(f["z_mean_m"][0])

    def test_квантили_интенсивности_различаются(self):
        xs, ys, zs = self.points()
        f = crown_point_features(square_labels(), TRANSFORM, xs, ys, zs, 1,
                                 intensity=np.linspace(0, 800, 9), resolution_m=0.5)
        values = [f[f"intensity_p{p}"][0] for p in (50, 75, 95)]
        assert values == sorted(values)
        assert values[0] > 0.0

    def test_плотность_точек(self):
        xs, ys, zs = self.points()
        f = crown_point_features(square_labels(), TRANSFORM, xs, ys, zs, 1,
                                 resolution_m=0.5)
        assert f["n_points"][0] == 9
        assert f["point_density_m2"][0] == pytest.approx(9 / (36 * 0.25))

    def test_точки_вне_крон_игнорируются(self):
        xs = np.array([3.0, 100.0])
        ys = np.array([6.5, 100.0])
        f = crown_point_features(square_labels(), TRANSFORM, xs, ys,
                                 np.array([5.0, 5.0]), 1, resolution_m=0.5)
        assert f["n_points"][0] == 1

    def test_доли_возвратов(self):
        xs, ys, zs = self.points()
        f = crown_point_features(square_labels(), TRANSFORM, xs, ys, zs, 1,
                                 return_number=np.array([1] * 6 + [2] * 3),
                                 number_of_returns=np.array([1] * 3 + [2] * 6),
                                 resolution_m=0.5)
        assert f["first_return_share"][0] == pytest.approx(6 / 9)
        assert f["multi_return_share"][0] == pytest.approx(6 / 9)


class TestVCI:
    def test_один_слой_даёт_ноль(self):
        assert vertical_complexity(np.array([1.0, 1.2, 1.4]), step_m=1.0) == 0.0

    def test_равномерное_распределение_даёт_единицу(self):
        assert vertical_complexity(np.arange(0, 10, 0.05), step_m=1.0) == pytest.approx(1.0, abs=0.01)

    def test_пустой_вход(self):
        assert np.isnan(vertical_complexity(np.empty(0)))


class TestCrownFeatures:
    def test_полная_таблица(self):
        labels = square_labels()
        chm = np.zeros((20, 20))
        chm[5:11, 5:11] = 12.0
        xs = np.full(5, 3.0)
        ys = np.full(5, 6.5)
        result = crown_features(
            labels, chm, TRANSFORM, resolution_m=0.5,
            apex_rows=np.array([7.0]), apex_cols=np.array([7.0]),
            points={"x": xs, "y": ys, "z": np.linspace(3, 12, 5),
                    "intensity": np.full(5, 90.0)})
        assert len(result) == 1
        assert {"area_m2", "compactness", "chm_mean_m", "height_robust_m",
                "n_points", "intensity_mean", "vci"} <= set(result.columns)
        assert list(result.tree_id) == [1]

    def test_без_облака_только_растровые_признаки(self):
        labels = square_labels()
        result = crown_features(labels, np.zeros((20, 20)), TRANSFORM, 0.5)
        assert "n_points" not in result.columns
        assert "area_m2" in result.columns

    def test_пустой_растр(self):
        result = crown_features(np.zeros((10, 10), dtype=np.int64),
                                np.zeros((10, 10)), TRANSFORM, 0.5)
        assert len(result) == 0

    def test_словарь_включает_идентификатор(self):
        result = crown_features(square_labels(), np.zeros((20, 20)), TRANSFORM, 0.5)
        assert "tree_id" in result.to_dict()
