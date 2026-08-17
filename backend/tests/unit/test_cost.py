"""Поверхность стоимости для водораздела крон."""

from __future__ import annotations

import numpy as np
import pytest

from sima_forest_cmd import (
    CostWeights,
    build_cost_surface,
    delineate_crowns,
    detect_tree_tops,
    gradient_magnitude,
    local_std,
    luminance,
    robust_normalize,
)
from sima_forest_cmd.treetops import TreeTops

from test_treetops import make_chm


def touching_crowns(height=15.0, shape=(60, 100), edge_col=60):
    """Сплошной полог равной высоты с двумя вершинами и цветовой границей.

    По высоте такие кроны неразличимы: седловины между ними нет, и водораздел
    ставит границу равноудалённо. На снимке граница видна — на ней и проверяем.
    """
    chm = np.zeros(shape)
    chm[10:50, 20:80] = height
    markers = np.zeros(shape, dtype=np.int32)
    markers[30, 35] = 1
    markers[30, 65] = 2
    tops = TreeTops(np.array([30.0, 30.0]), np.array([35.0, 65.0]),
                    np.array([height, height]), markers, 2)
    rgb = np.full((shape[0], shape[1], 3), 80.0)
    rgb[:, edge_col:] = 200.0
    return chm, tops, rgb


def right_edge_of(labels, label=1, row=30):
    cells = np.flatnonzero(labels[row] == label)
    return int(cells.max()) if cells.size else -1


class TestNormalize:
    def test_приводит_к_единичному_диапазону(self):
        out = robust_normalize(np.linspace(0, 10, 101))
        assert out.min() == pytest.approx(0.0, abs=0.02)
        assert out.max() == pytest.approx(1.0, abs=0.02)

    def test_выброс_не_сжимает_шкалу(self):
        data = np.concatenate([np.linspace(0, 1, 999), [1e6]])
        out = robust_normalize(data)
        # без обрезки по перцентилям полезный сигнал ушёл бы в 1e-6
        assert out[:999].max() > 0.9

    def test_маска_ограничивает_выборку(self):
        data = np.array([[0.0, 100.0], [1.0, 2.0]])
        mask = np.array([[False, False], [True, True]])
        out = robust_normalize(data, mask)
        assert out[1, 0] == pytest.approx(0.0, abs=0.02)
        assert out[1, 1] == pytest.approx(1.0, abs=0.02)

    def test_постоянный_растр_даёт_нули(self):
        assert np.all(robust_normalize(np.full((5, 5), 3.0)) == 0.0)

    def test_пустая_маска_даёт_нули(self):
        assert np.all(robust_normalize(np.ones((4, 4)), np.zeros((4, 4), bool)) == 0.0)


class TestComponents:
    def test_градиент_выделяет_ступеньку(self):
        data = np.zeros((10, 10))
        data[:, 5:] = 1.0
        grad = gradient_magnitude(data)
        assert grad[:, 4:6].max() > 0
        assert grad[:, 0:3].max() == pytest.approx(0.0)

    def test_текстура_нулевая_на_однородном(self):
        assert local_std(np.full((10, 10), 7.0)).max() == pytest.approx(0.0)

    def test_текстура_растёт_на_шуме(self):
        rng = np.random.default_rng(0)
        assert local_std(rng.normal(size=(50, 50))).mean() > 0.5

    def test_яркость_принимает_оба_порядка_осей(self):
        rgb = np.dstack([np.full((4, 4), 10.0), np.full((4, 4), 20.0), np.full((4, 4), 30.0)])
        assert np.allclose(luminance(rgb), luminance(np.moveaxis(rgb, -1, 0)))

    def test_яркость_по_rec601(self):
        rgb = np.zeros((1, 1, 3))
        rgb[0, 0] = (100.0, 200.0, 50.0)
        assert luminance(rgb)[0, 0] == pytest.approx(0.299 * 100 + 0.587 * 200 + 0.114 * 50)


class TestDefaultWeights:
    def test_по_умолчанию_только_высота(self):
        assert CostWeights().is_height_only

    def test_метки_совпадают_с_базовым_водоразделом(self):
        # ключевая гарантия: подключение модуля само по себе ничего не меняет
        chm = make_chm([(25, 25), (25, 75), (75, 25), (75, 75), (50, 50)],
                       sigma=7.0, vary=0.5)
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=3.0)
        canopy = np.where(np.isfinite(chm), chm, 0.0) >= 0.5
        surface = build_cost_surface(chm, CostWeights(), canopy_mask=canopy).surface

        assert np.array_equal(delineate_crowns(chm, tops),
                              delineate_crowns(chm, tops, surface=surface))


class TestAfsSplitsTouchingCrowns:
    """То, ради чего вводилась совместная стоимость."""

    def test_по_высоте_граница_равноудалённая(self):
        chm, tops, _ = touching_crowns(edge_col=60)
        labels = delineate_crowns(chm, tops)
        assert right_edge_of(labels) == pytest.approx(50, abs=2)

    def test_границы_афс_сдвигают_раздел_к_цветовому_переходу(self):
        chm, tops, rgb = touching_crowns(edge_col=60)
        canopy = chm >= 0.5
        surface = build_cost_surface(
            chm, CostWeights(height=1.0, afs_edges=3.0),
            afs_rgb=rgb, canopy_mask=canopy).surface
        labels = delineate_crowns(chm, tops, surface=surface)
        assert right_edge_of(labels) == pytest.approx(60, abs=2)

    @pytest.mark.parametrize("edge", [40, 45, 55, 64])
    def test_положение_границы_следует_за_снимком(self, edge):
        chm, tops, rgb = touching_crowns(edge_col=edge)
        surface = build_cost_surface(
            chm, CostWeights(height=1.0, afs_edges=3.0),
            afs_rgb=rgb, canopy_mask=chm >= 0.5).surface
        assert right_edge_of(delineate_crowns(chm, tops, surface=surface)) \
            == pytest.approx(edge, abs=3)

    def test_граница_вне_промежутка_между_вершинами_не_действует(self):
        # Раздел водораздела всегда лежит между маркерами (здесь столбцы 35 и 65).
        # Цветовая граница правее 65 попадает внутрь второй кроны и разделителем
        # стать не может — снимок не двигает раздел куда угодно.
        chm, tops, rgb = touching_crowns(edge_col=70)
        surface = build_cost_surface(
            chm, CostWeights(height=1.0, afs_edges=3.0),
            afs_rgb=rgb, canopy_mask=chm >= 0.5).surface
        assert right_edge_of(delineate_crowns(chm, tops, surface=surface)) \
            == pytest.approx(50, abs=2)

    def test_число_крон_не_меняется(self):
        # поверхность двигает границы, но не создаёт и не убирает деревья
        chm, tops, rgb = touching_crowns()
        surface = build_cost_surface(
            chm, CostWeights(height=1.0, afs_edges=3.0),
            afs_rgb=rgb, canopy_mask=chm >= 0.5).surface
        labels = delineate_crowns(chm, tops, surface=surface)
        assert set(np.unique(labels[labels > 0])) == {1, 2}


class TestValidation:
    def test_вес_на_афс_без_снимка_отвергается(self):
        with pytest.raises(ValueError, match="снимок не передан"):
            build_cost_surface(np.ones((10, 10)), CostWeights(afs_edges=1.0))

    def test_вес_на_интенсивность_без_растра_отвергается(self):
        with pytest.raises(ValueError, match="intensity"):
            build_cost_surface(np.ones((10, 10)), CostWeights(intensity=1.0))

    def test_несовпадение_формы_поверхности(self):
        chm = make_chm([(20, 20)])
        tops = detect_tree_tops(chm, resolution_m=0.5, window_m=2.0)
        with pytest.raises(ValueError, match="не совпадает"):
            delineate_crowns(chm, tops, surface=np.zeros((5, 5)))

    def test_компоненты_и_веса_возвращаются(self):
        chm, _, rgb = touching_crowns()
        result = build_cost_surface(chm, CostWeights(height=1.0, afs_texture=2.0),
                                    afs_rgb=rgb, canopy_mask=chm >= 0.5)
        assert set(result.components) == {"height", "afs_texture"}
        assert result.weights == {"height": 1.0, "afs_texture": 2.0}


class TestResample:
    def test_снимок_приводится_к_сетке_цмд(self):
        chm = np.zeros((20, 20))
        chm[5:15, 5:15] = 10.0
        rgb = np.zeros((200, 200, 3))
        rgb[:, 100:] = 255.0
        surface = build_cost_surface(chm, CostWeights(afs_edges=1.0),
                                     afs_rgb=rgb, canopy_mask=chm >= 0.5).surface
        assert surface.shape == chm.shape
