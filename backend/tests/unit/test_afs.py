"""Корректировка вершин по аэрофотоснимку: вегетационная маска, отсев, уточнение."""

from __future__ import annotations

import numpy as np
import pytest

from sima_forest_cmd import (
    correct_tops,
    resample_mask_to_grid,
    vegetation_index,
    vegetation_mask,
)


def make_scene(shape=(40, 40)):
    """Серый фон, две зелёные кроны и серый столб между ними."""
    rgb = np.full((shape[0], shape[1], 3), 120, dtype=np.uint8)
    rgb[8:16, 8:16] = (60, 170, 60)      # крона
    rgb[8:16, 24:32] = (60, 170, 60)     # крона
    rgb[26:30, 18:22] = (150, 150, 150)  # столб — ярче фона, но не зелёный
    return rgb


class TestIndex:
    def test_зелень_выше_серого(self):
        rgb = make_scene()
        index = vegetation_index(rgb, "exg")
        assert index[12, 12] > index[28, 20]

    def test_принимает_оба_порядка_осей(self):
        rgb = make_scene()
        a = vegetation_index(rgb, "exg")
        b = vegetation_index(np.moveaxis(rgb, -1, 0), "exg")
        assert np.allclose(a, b, equal_nan=True)

    def test_vari_тоже_различает_зелень(self):
        rgb = make_scene()
        index = vegetation_index(rgb, "vari")
        assert index[12, 12] > index[28, 20]

    def test_чёрный_пиксель_не_ломает_деление(self):
        rgb = np.zeros((4, 4, 3), dtype=np.uint8)
        assert np.all(np.isnan(vegetation_index(rgb, "exg")))

    def test_неизвестный_индекс(self):
        with pytest.raises(ValueError, match="Неизвестный индекс"):
            vegetation_index(make_scene(), "ndvi")

    def test_одноканальный_растр_отвергается(self):
        with pytest.raises(ValueError):
            vegetation_index(np.zeros((10, 10)), "exg")


class TestMask:
    def test_кроны_в_маске_столб_нет(self):
        veg = vegetation_mask(make_scene(), threshold=0.05)
        assert veg.mask[12, 12]
        assert veg.mask[12, 28]
        assert not veg.mask[28, 20]

    def test_мелкие_пятна_отбрасываются(self):
        rgb = np.full((30, 30, 3), 120, dtype=np.uint8)
        rgb[5:13, 5:13] = (60, 170, 60)     # 64 ячейки — остаётся
        rgb[20, 20] = (60, 170, 60)         # одиночная — уходит
        veg = vegetation_mask(rgb, min_area_px=10)
        assert veg.mask[8, 8]
        assert not veg.mask[20, 20]

    def test_покрытие_считается(self):
        veg = vegetation_mask(make_scene())
        assert 0 < veg.coverage_pct < 100


class TestResample:
    def test_приведение_к_сетке_цмд(self):
        mask = np.zeros((40, 40), dtype=bool)
        mask[0:20, 0:20] = True
        small = resample_mask_to_grid(mask, (10, 10))
        assert small.shape == (10, 10)
        assert small[0:5, 0:5].all()
        assert not small[5:, 5:].any()

    def test_совпадающая_сетка_возвращается_как_есть(self):
        mask = np.zeros((8, 8), dtype=bool)
        assert resample_mask_to_grid(mask, (8, 8)).shape == (8, 8)


class TestCorrection:
    def test_вершина_вне_растительности_отсеивается(self):
        veg = np.zeros((20, 20), dtype=bool)
        veg[5:10, 5:10] = True
        out = correct_tops(np.array([7.0, 15.0]), np.array([7.0, 15.0]),
                           veg, resolution_m=0.5, refine_position=False)
        assert list(out.keep) == [True, False]
        assert out.dropped == 1

    def test_отсев_можно_выключить(self):
        veg = np.zeros((20, 20), dtype=bool)
        out = correct_tops(np.array([5.0]), np.array([5.0]), veg,
                           resolution_m=0.5, drop_non_vegetation=False,
                           refine_position=False)
        assert out.keep.all()
        assert out.dropped == 0

    def test_вершина_сдвигается_к_центру_кроны(self):
        veg = np.zeros((20, 20), dtype=bool)
        veg[6:11, 6:11] = True                        # центр в (8,8)
        out = correct_tops(np.array([6.0]), np.array([6.0]), veg,
                           resolution_m=0.5, refine_radius_m=3.0)
        assert out.rows[0] == pytest.approx(8.0, abs=0.01)
        assert out.cols[0] == pytest.approx(8.0, abs=0.01)
        assert out.moved == 1

    def test_дальний_сдвиг_отклоняется(self):
        # слитный полог: центр области далеко, исходное положение по ЦМД надёжнее
        veg = np.zeros((40, 40), dtype=bool)
        veg[0:40, 0:40] = True
        out = correct_tops(np.array([2.0]), np.array([2.0]), veg,
                           resolution_m=0.5, refine_radius_m=1.0)
        assert out.rows[0] == 2.0
        assert out.moved == 0

    def test_без_вершин_не_падает(self):
        out = correct_tops(np.empty(0), np.empty(0), np.zeros((5, 5), dtype=bool), 0.5)
        assert len(out.keep) == 0

    def test_статистика_сдвига_заполняется(self):
        veg = np.zeros((20, 20), dtype=bool)
        veg[6:11, 6:11] = True
        out = correct_tops(np.array([6.0, 8.0]), np.array([6.0, 8.0]), veg,
                           resolution_m=0.5, refine_radius_m=3.0)
        assert out.shift_px.size == 2
        assert out.shift_px[0] > 0        # сдвинулась
        assert out.shift_px[1] == 0       # уже в центре
