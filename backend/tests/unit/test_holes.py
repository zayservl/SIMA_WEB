"""Тесты holes.py (выбор ячеек растра под заполнение интерполяцией)."""

import numpy as np

from sima_dem_core.raster.holes import fill_voids, fillable_mask, px_from_metres


class TestFillableMask:

    def test_internal_hole_filled_without_extrapolation(self):
        """Дыра, окружённая данными, заполняется и при нулевой экстраполяции."""
        valid = np.ones((20, 20), dtype=bool)
        valid[8:12, 8:12] = False
        mask = fillable_mask(valid, 0.0)
        assert mask[8:12, 8:12].all()
        assert mask.sum() == 16

    def test_edge_gap_not_filled_without_extrapolation(self):
        """Пустота, касающаяся рамки растра, при D=0 не заполняется.

        Это историческое поведение: топологически такая область не «дыра».
        """
        valid = np.ones((20, 20), dtype=bool)
        valid[:, 15:] = False  # полоса до правого края
        assert not fillable_mask(valid, 0.0).any()

    def test_edge_gap_filled_within_distance(self):
        """При D>0 приграничная пустота заполняется на заданную глубину."""
        valid = np.ones((20, 20), dtype=bool)
        valid[:, 15:] = False
        mask = fillable_mask(valid, 3.0)
        # Колонки 15..17 — в пределах 3 px от валидных данных (колонка 14).
        assert mask[:, 15:18].all()
        # Колонка 19 — на расстоянии 5 px, за пределом.
        assert not mask[:, 19].any()

    def test_distance_measured_from_valid_data_not_from_border(self):
        """Глубина отсчитывается от валидных данных, а не от рамки растра."""
        valid = np.zeros((20, 20), dtype=bool)
        valid[10, 10] = True
        mask = fillable_mask(valid, 2.0)
        assert mask[10, 12]        # 2 px от точки
        assert not mask[10, 13]    # 3 px — за пределом
        assert not mask[0, 0]      # у рамки, но далеко от данных

    def test_all_valid_gives_empty_mask(self):
        assert not fillable_mask(np.ones((10, 10), dtype=bool), 5.0).any()

    def test_all_empty_gives_empty_mask(self):
        """Без единой валидной ячейки экстраполировать не от чего."""
        assert not fillable_mask(np.zeros((10, 10), dtype=bool), 5.0).any()

    def test_negative_distance_treated_as_zero(self):
        valid = np.ones((10, 10), dtype=bool)
        valid[:, 7:] = False
        assert not fillable_mask(valid, -1.0).any()


class TestFillVoids:
    """Многопроходное заполнение пустот (`fill_voids`)."""

    NODATA = -9999.0

    def _lake_with_channel(self):
        """Растр 60x60: «озеро» 20x20, соединённое протокой с краем растра.

        До заполнения озеро не является внутренней дырой — оно сообщается с
        внешней пустотой через протоку шириной 2 px. Именно этот случай один
        проход `fillnodata` не закрывает.
        """
        arr = np.full((60, 60), 100.0, dtype="float32")
        valid = np.ones((60, 60), dtype=bool)
        valid[20:40, 20:40] = False           # озеро
        valid[29:31, 40:] = False             # протока до правой рамки
        arr[~valid] = self.NODATA
        return arr, valid

    def test_single_pass_leaves_lake_closed_by_its_own_fill(self):
        arr, valid = self._lake_with_channel()
        _, filled = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=1)
        lake = np.zeros_like(valid)
        lake[20:40, 20:40] = True
        assert not filled[lake].all(), "за один проход озеро не заполняется целиком"

    def test_second_pass_closes_it(self):
        arr, valid = self._lake_with_channel()
        _, filled = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=3)
        lake = np.zeros_like(valid)
        lake[20:40, 20:40] = True
        assert filled[lake].all()

    def test_valid_cells_never_change(self):
        """Ключевая гарантия: исходные измерения не переинтерполируются."""
        rng = np.random.default_rng(0)
        arr, valid = self._lake_with_channel()
        arr[valid] = rng.normal(100.0, 5.0, size=int(valid.sum())).astype("float32")
        for passes in (1, 2, 5):
            out, _ = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=passes)
            assert np.array_equal(out[valid], arr[valid])

    def test_outward_growth_bounded_by_allowance(self):
        """Проходы не сдвигают внешнюю границу данных дальше допуска."""
        arr = np.full((40, 40), 100.0, dtype="float32")
        valid = np.ones((40, 40), dtype=bool)
        valid[:, 20:] = False                 # пустота до правой рамки
        arr[~valid] = self.NODATA
        for passes in (1, 3, 8):
            _, filled = fill_voids(arr, valid, max_extrapolation_px=3.0, max_passes=passes)
            assert filled[:, 20:23].all()
            assert not filled[:, 23:].any(), "экстраполяция нарастает с проходами"

    def test_converges_and_is_monotonic(self):
        """Лишние проходы ничего не добавляют и не переписывают заполненное."""
        arr, valid = self._lake_with_channel()
        out3, filled3 = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=3)
        out9, filled9 = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=9)
        assert np.array_equal(filled3, filled9)
        assert np.array_equal(out3, out9)

    def test_nothing_to_fill_returns_original(self):
        arr = np.full((10, 10), 5.0, dtype="float32")
        valid = np.ones((10, 10), dtype=bool)
        out, filled = fill_voids(arr, valid, max_extrapolation_px=5.0)
        assert not filled.any()
        assert np.array_equal(out, arr)


class TestPxFromMetres:

    def test_converts_by_resolution(self):
        assert px_from_metres(5.0, 0.5) == 10.0
        assert px_from_metres(5.0, 1.0) == 5.0

    def test_non_positive_inputs_give_zero(self):
        assert px_from_metres(0.0, 1.0) == 0.0
        assert px_from_metres(5.0, 0.0) == 0.0
        assert px_from_metres(-5.0, 1.0) == 0.0
