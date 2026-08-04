"""Тесты holes.py (выбор ячеек растра под заполнение интерполяцией)."""

import numpy as np

from sima_dem_core.raster.holes import fillable_mask, px_from_metres


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


class TestPxFromMetres:

    def test_converts_by_resolution(self):
        assert px_from_metres(5.0, 0.5) == 10.0
        assert px_from_metres(5.0, 1.0) == 5.0

    def test_non_positive_inputs_give_zero(self):
        assert px_from_metres(0.0, 1.0) == 0.0
        assert px_from_metres(5.0, 0.0) == 0.0
        assert px_from_metres(-5.0, 1.0) == 0.0
