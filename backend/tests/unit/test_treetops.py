"""Детекция вершин деревьев по ЦМД — на синтетике с известным ответом."""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from sima_forest_cmd import (
    detect_tree_tops,
    disc_kernel,
    prepare_chm,
    split_by_height,
    to_world,
    window_radius_px,
)


def make_chm(centres, shape=(100, 100), height=15.0, sigma=3.0, vary=0.0):
    """Растр из гауссовых крон с вершинами в заданных ячейках.

    `vary` разводит высоты соседних крон: при строго равных высотах каждая крона
    оказывается собственным максимумом независимо от размера окна, и слипание
    крон на грубой сетке не воспроизводится.
    """
    rows, cols = np.mgrid[0:shape[0], 0:shape[1]]
    chm = np.zeros(shape, dtype=float)
    for i, (r, c) in enumerate(centres):
        h = height + vary * ((i % 7) - 3)
        chm = np.maximum(chm, h * np.exp(
            -((rows - r) ** 2 + (cols - c) ** 2) / (2 * sigma ** 2)))
    return chm


def make_chm_metres(centres_m, extent_m, resolution_m, height=15.0,
                    crown_radius_m=1.0, vary=0.5):
    """Тот же участок местности, растеризованный с заданным разрешением.

    Позволяет сравнить детекцию на разных сетках при неизменной сцене.
    """
    n = int(round(extent_m / resolution_m))
    ys, xs = np.mgrid[0:n, 0:n] * resolution_m + resolution_m / 2
    chm = np.zeros((n, n), dtype=float)
    sigma = crown_radius_m / 2.0
    for i, (y, x) in enumerate(centres_m):
        h = height + vary * ((i % 7) - 3)
        chm = np.maximum(chm, h * np.exp(
            -((ys - y) ** 2 + (xs - x) ** 2) / (2 * sigma ** 2)))
    return chm


class TestWindowRadius:
    def test_округление_а_не_усечение(self):
        # 0.75/0.5 = 1.5 -> 2 px; при усечении было бы 1 px и окно вдвое уже
        assert window_radius_px(0.75, 0.5) == 2

    def test_окно_равное_разрешению_даёт_радиус_1(self):
        assert window_radius_px(0.5, 0.5) == 1

    def test_окно_меньше_разрешения_отвергается(self):
        # иначе радиус выродился бы в 0, ядро в 1x1, и максимумом стала бы каждая ячейка
        with pytest.raises(ValueError, match="меньше разрешения"):
            window_radius_px(0.25, 0.5)

    def test_нулевое_разрешение_отвергается(self):
        with pytest.raises(ValueError, match="больше 0|> 0"):
            window_radius_px(1.0, 0.0)

    @pytest.mark.parametrize("radius,expected", [(1, 3), (2, 5), (3, 7)])
    def test_размер_дискового_ядра(self, radius, expected):
        kernel = disc_kernel(radius)
        assert kernel.shape == (expected, expected)
        assert kernel[radius, radius]

    def test_ядро_нулевого_радиуса_отвергается(self):
        with pytest.raises(ValueError):
            disc_kernel(0)


class TestDetection:
    def test_находит_ровно_заданные_вершины(self):
        centres = [(20, 20), (20, 70), (70, 20), (70, 70), (45, 45)]
        chm = make_chm(centres)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0)

        assert len(tops) == len(centres)
        found = sorted(zip(np.rint(tops.rows).astype(int),
                           np.rint(tops.cols).astype(int)))
        assert found == sorted(centres)

    def test_высота_берётся_из_растра(self):
        chm = make_chm([(50, 50)], height=23.0)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0)
        assert tops.heights[0] == pytest.approx(23.0, abs=0.5)

    def test_вершины_ниже_порога_отбрасываются(self):
        chm = make_chm([(30, 30)], height=20.0) + make_chm([(70, 70)], height=1.0)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0, min_height_m=5.0)
        assert len(tops) == 1
        assert np.rint(tops.rows[0]) == 30

    def test_шум_выше_верхней_отсечки_отбрасывается(self):
        chm = make_chm([(40, 40)], height=18.0)
        chm[10, 10] = 120.0                      # заведомый выброс ЦМД
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0,
                                max_height_m=60.0, smooth_radius_px=0)
        assert len(tops) == 1
        assert np.rint(tops.rows[0]) == 40

    def test_плато_даёт_одну_вершину(self):
        # плоская макушка не должна рассыпаться на несколько стволов
        chm = np.zeros((60, 60))
        chm[25:35, 25:35] = 12.0
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0, smooth_radius_px=0)
        assert len(tops) == 1
        assert tops.rows[0] == pytest.approx(29.5, abs=1.0)

    def test_пустой_растр_не_падает(self):
        tops = detect_tree_tops(np.zeros((30, 30)), resolution_m=0.5, window_m=2.0)
        assert len(tops) == 0
        assert tops.markers.max() == 0

    def test_nan_не_становится_вершиной(self):
        chm = make_chm([(30, 30)])
        chm[50:55, 50:55] = np.nan
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0)
        assert len(tops) == 1

    def test_маркеры_нумеруются_подряд(self):
        chm = make_chm([(20, 20), (20, 60), (60, 20)])
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0)
        assert sorted(np.unique(tops.markers)) == [0, 1, 2, 3]


class TestResolutionEffect:
    """Ключ к расхождению с эталоном: на грубой сетке окно шире, кроны слипаются.

    Физический поперечник окна равен `2 * radius_px * resolution + resolution`.
    При окне 1 м это 2.5 м на сетке 0.5 м и 3.0 м на сетке 1.0 м — то есть переход
    на метровую сетку сам по себе расширяет окно поиска.
    """

    @pytest.mark.parametrize("resolution,radius_px,width_m", [(0.5, 2, 2.5), (1.0, 1, 3.0)])
    def test_физический_размер_окна(self, resolution, radius_px, width_m):
        r = window_radius_px(1.0, resolution)
        assert r == radius_px
        assert 2 * r * resolution + resolution == pytest.approx(width_m)

    def test_крона_мельче_ячейки_исчезает(self):
        # Крона радиусом 0.5 м на сетке 0.5 м находится вся, на сетке 1.0 м
        # не выживает: ячейка шире кроны, максимум размывается ниже отсечки.
        step = 2.6
        centres = [(5 + i * step, 5 + j * step) for i in range(10) for j in range(10)]
        fine = make_chm_metres(centres, extent_m=40.0, resolution_m=0.5,
                               crown_radius_m=0.5)
        coarse = make_chm_metres(centres, extent_m=40.0, resolution_m=1.0,
                                 crown_radius_m=0.5)

        assert len(detect_tree_tops(fine, resolution_m=0.5, window_m=1.0)) == len(centres)
        assert len(detect_tree_tops(coarse, resolution_m=1.0, window_m=1.0)) == 0

    @pytest.mark.parametrize("crown_radius_m", [1.0, 2.0, 3.0])
    def test_отдельные_кроны_грубая_сетка_не_теряет(self, crown_radius_m):
        # Обратное гипотезе: пока кроны не соприкасаются, грубая сетка их не
        # сливает — дискретизация даже добавляет ложные вершины на ничьих высот.
        # Значит объяснять недостачу деревьев одним лишь разрешением нельзя,
        # это решается замером на реальных данных.
        step = 2.6
        centres = [(5 + i * step, 5 + j * step) for i in range(10) for j in range(10)]
        coarse = make_chm_metres(centres, extent_m=40.0, resolution_m=1.0,
                                 crown_radius_m=crown_radius_m)
        assert len(detect_tree_tops(coarse, resolution_m=1.0, window_m=1.0)) >= len(centres)

    def test_окно_шире_даёт_меньше_вершин(self):
        centres = [(r, c) for r in range(15, 95, 8) for c in range(15, 95, 8)]
        chm = make_chm(centres, shape=(100, 100), sigma=2.0, vary=0.5)
        assert (len(detect_tree_tops(chm, resolution_m=0.5, window_m=4.0))
                < len(detect_tree_tops(chm, resolution_m=0.5, window_m=1.0)))


class TestHelpers:
    def test_подготовка_обнуляет_невалидное(self):
        chm = np.array([[np.nan, 0.2], [80.0, 12.0]])
        prepared = prepare_chm(chm, smooth_radius_px=0)
        assert prepared[0, 0] == 0.0     # nodata
        assert prepared[0, 1] == 0.0     # ниже нижней отсечки
        assert prepared[1, 0] == 0.0     # выше верхней отсечки
        assert prepared[1, 1] == 12.0

    def test_перевод_в_координаты(self):
        chm = make_chm([(10, 20)])
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0)
        transform = from_origin(1000.0, 2000.0, 0.5, 0.5)
        xyz = to_world(tops, transform)
        assert xyz.shape == (1, 3)
        assert xyz[0, 0] == pytest.approx(1000.0 + 20.5 * 0.5, abs=0.01)
        assert xyz[0, 1] == pytest.approx(2000.0 - 10.5 * 0.5, abs=0.01)

    def test_перевод_пустых_вершин(self):
        tops = detect_tree_tops(np.zeros((10, 10)), resolution_m=0.5, window_m=2.0)
        assert to_world(tops, from_origin(0, 0, 0.5, 0.5)).shape == (0, 3)

    def test_разделение_на_древостой_и_кустарник(self):
        trees, shrubs = split_by_height(np.array([1.0, 4.9, 5.0, 20.0]),
                                        shrub_height_m=5.0)
        assert list(trees) == [False, False, True, True]
        assert list(shrubs) == [True, True, False, False]
