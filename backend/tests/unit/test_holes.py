"""Тесты holes.py: выбор ячеек под заполнение, интерполяция пустот, гидровыравнивание."""

import numpy as np
import pytest
from scipy.ndimage import binary_dilation, binary_erosion

from sima_dem_core.raster import holes
from sima_dem_core.raster.holes import fill_voids, fillable_mask, px_from_metres
from sima_dem_core.raster.hydro import flatten_water_voids


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


NODATA = -9999.0


def lake_with_channel(size=60, lake=(20, 40), level=100.0):
    """Растр `size`x`size`: «озеро», соединённое протокой с краем растра.

    До заполнения озеро не является внутренней дырой — оно сообщается с внешней
    пустотой через протоку шириной 2 px. Именно этот случай один проход не закрывает.
    """
    lo, hi = lake
    arr = np.full((size, size), level, dtype="float32")
    valid = np.ones((size, size), dtype=bool)
    valid[lo:hi, lo:hi] = False                       # озеро
    valid[(lo + hi) // 2 - 1:(lo + hi) // 2 + 1, hi:] = False   # протока до рамки
    arr[~valid] = NODATA
    mask = np.zeros((size, size), dtype=bool)
    mask[lo:hi, lo:hi] = True
    return arr, valid, mask


class TestFillVoids:
    """Многопроходное заполнение пустот (`fill_voids`)."""

    def test_single_pass_leaves_lake_closed_by_its_own_fill(self):
        arr, valid, lake = lake_with_channel()
        result = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=1)
        assert not result.filled[lake].all(), "за один проход озеро не заполняется целиком"

    def test_second_pass_closes_it(self):
        arr, valid, lake = lake_with_channel()
        result = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=3)
        assert result.filled[lake].all()
        assert result.passes >= 2

    @pytest.mark.parametrize("method", ["laplace", "idw"])
    def test_valid_cells_never_change(self, method):
        """Ключевая гарантия: исходные измерения не переинтерполируются."""
        rng = np.random.default_rng(0)
        arr, valid, _ = lake_with_channel()
        arr[valid] = rng.normal(100.0, 5.0, size=int(valid.sum())).astype("float32")
        for passes in (1, 2, 5):
            result = fill_voids(arr, valid, method=method,
                                max_extrapolation_px=5.0, max_passes=passes)
            assert np.array_equal(result.array[valid], arr[valid])

    def test_outward_growth_bounded_by_allowance(self):
        """Проходы не сдвигают внешнюю границу данных дальше допуска."""
        arr = np.full((40, 40), 100.0, dtype="float32")
        valid = np.ones((40, 40), dtype=bool)
        valid[:, 20:] = False                 # пустота до правой рамки
        arr[~valid] = NODATA
        for passes in (1, 3, 8):
            result = fill_voids(arr, valid, max_extrapolation_px=3.0, max_passes=passes)
            assert result.filled[:, 20:23].all()
            assert not result.filled[:, 23:].any(), "экстраполяция нарастает с проходами"

    def test_converges_and_is_monotonic(self):
        """Лишние проходы ничего не добавляют и не переписывают заполненное."""
        arr, valid, _ = lake_with_channel()
        three = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=3)
        nine = fill_voids(arr, valid, max_extrapolation_px=5.0, max_passes=9)
        assert np.array_equal(three.filled, nine.filled)
        assert np.array_equal(three.array, nine.array)

    def test_nothing_to_fill_returns_original(self):
        arr = np.full((10, 10), 5.0, dtype="float32")
        valid = np.ones((10, 10), dtype=bool)
        result = fill_voids(arr, valid, max_extrapolation_px=5.0)
        assert not result.filled.any()
        assert np.array_equal(result.array, arr)

    def test_unknown_method_raises(self):
        arr, valid, _ = lake_with_channel()
        with pytest.raises(ValueError, match="метод"):
            fill_voids(arr, valid, method="spline", max_extrapolation_px=5.0)


class TestLaplaceFill:
    """Гармоническая интерполяция против конического IDW."""

    def _ramp_with_hole(self):
        """Линейный склон с квадратной дырой: гармоническое решение = сам склон."""
        rows = np.arange(40, dtype="float32")[:, None]
        arr = np.repeat(rows, 40, axis=1) + 100.0
        valid = np.ones((40, 40), dtype=bool)
        valid[14:26, 14:26] = False
        arr[~valid] = NODATA
        return arr, valid

    def test_reproduces_linear_surface(self):
        """На линейном склоне гармоническое заполнение восстанавливает склон."""
        arr, valid = self._ramp_with_hole()
        truth = np.repeat(np.arange(40, dtype="float32")[:, None], 40, axis=1) + 100.0
        result = fill_voids(arr, valid, method="laplace")
        assert np.abs(result.array[~valid] - truth[~valid]).max() < 1e-3

    def test_obeys_maximum_principle(self):
        """Значения внутри пустоты не выходят за диапазон её границы."""
        rng = np.random.default_rng(1)
        arr, valid = self._ramp_with_hole()
        arr[valid] += rng.normal(0.0, 2.0, size=int(valid.sum())).astype("float32")
        result = fill_voids(arr, valid, method="laplace")
        rim = binary_dilation(~valid) & valid
        assert result.array[~valid].min() >= arr[rim].min() - 1e-6
        assert result.array[~valid].max() <= arr[rim].max() + 1e-6

    def test_result_is_harmonic_inside(self):
        """Внутри пустоты лапласиан равен нулю — радиальных лучей быть не может."""
        arr, valid = self._ramp_with_hole()
        result = fill_voids(arr, valid, method="laplace")
        a = result.array.astype("float64")
        lap = (4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1]
               - a[1:-1, :-2] - a[1:-1, 2:])
        interior = binary_erosion(~valid)[1:-1, 1:-1]
        assert np.abs(lap[interior]).max() < 1e-6

    def test_large_region_falls_back_to_idw(self, monkeypatch):
        """Слишком крупная пустота решается IDW, а не разреженной системой."""
        monkeypatch.setattr(holes, "LAPLACE_MAX_CELLS", 10)
        arr, valid = self._ramp_with_hole()
        result = fill_voids(arr, valid, method="laplace")
        assert result.filled.sum() > 10          # заполнено, но другим методом
        assert np.array_equal(result.array[valid], arr[valid])


class TestHydroFlattening:
    """Гидровыравнивание пустот-водоёмов (порог площади 3DEP)."""

    # 100x100 ячеек при res=1 м — 1 га, выше порога 3DEP (0.8 га).
    def _lake(self, side=100, rim_level=50.0, canopy=70.0, size=140):
        """Озеро в центре, по периметру — низкий урез и высокие кроны."""
        arr = np.full((size, size), canopy, dtype="float32")
        valid = np.ones((size, size), dtype=bool)
        lo = (size - side) // 2
        valid[lo:lo + side, lo:lo + side] = False
        arr[~valid] = NODATA
        rim = binary_dilation(~valid) & valid
        arr[rim] = rim_level                      # ровный урез по всему периметру
        return arr, valid, ~valid

    def test_lake_gets_flat_level_from_rim(self):
        arr, valid, lake = self._lake()
        result = fill_voids(arr, valid, hydro_flatten=True, resolution_m=1.0)
        assert result.water[lake].all()
        assert np.allclose(result.array[lake], 50.0)
        assert result.water_levels == pytest.approx([50.0])

    def test_small_void_is_interpolated_not_flattened(self):
        """Пустота меньше порога 0.8 га водоёмом не считается."""
        arr, valid, small = self._lake(side=20)    # 400 м² при res=1 м
        result = fill_voids(arr, valid, hydro_flatten=True, resolution_m=1.0)
        assert not result.water.any()
        assert result.filled[small].any()

    def test_level_taken_from_low_envelope_of_rim(self):
        """Отметка — нижний квантиль окаймления: урез воды, а не кроны берега."""
        arr, valid, lake = self._lake(rim_level=50.0, canopy=70.0)
        rim = binary_dilation(lake) & valid
        idx = np.argwhere(rim)
        arr[idx[: len(idx) // 2, 0], idx[: len(idx) // 2, 1]] = 65.0   # кроны над урезом
        result = fill_voids(arr, valid, hydro_flatten=True, resolution_m=1.0)
        assert result.water[lake].all()
        assert result.water_levels[0] == pytest.approx(50.0, abs=0.5)

    def test_area_threshold_is_the_only_criterion_without_mask(self):
        """Признак косвенный: замкнутая пустота нужного размера считается водой.

        Документирует ограничение — крупная лакуна не водного происхождения
        будет выровнена. Отсюда рекомендация передавать готовую маску.
        """
        arr, valid, void = self._lake()
        result = fill_voids(arr, valid, hydro_flatten=True, resolution_m=1.0,
                            min_water_area_m2=1.0)
        assert result.water[void].all()

    def test_explicit_water_mask_skips_area_check(self):
        """С готовой маской (брейклайны) отбор по площади не нужен."""
        arr, valid, small = self._lake(side=20)
        result = fill_voids(arr, valid, hydro_flatten=True, resolution_m=1.0,
                            water=small)
        assert result.water[small].all()

    def test_disabled_by_default(self):
        arr, valid, lake = self._lake()
        result = fill_voids(arr, valid, resolution_m=1.0)
        assert not result.water.any()

    def test_valid_cells_untouched_by_flattening(self):
        arr, valid, _ = self._lake()
        result = fill_voids(arr, valid, hydro_flatten=True, resolution_m=1.0)
        assert np.array_equal(result.array[valid], arr[valid])

    def test_no_candidates_returns_unchanged(self):
        """Пустой набор кандидатов — растр возвращается как есть."""
        arr, valid, _ = self._lake()
        out = flatten_water_voids(arr, valid, np.zeros_like(valid), 1.0)
        assert not out.water.any()
        assert out.levels == []
        assert np.array_equal(out.array, arr)

    def test_void_without_rim_is_skipped(self):
        """Пустота без единого валидного соседа отметку взять не может."""
        arr = np.full((20, 20), NODATA, dtype="float32")
        valid = np.zeros((20, 20), dtype=bool)
        out = flatten_water_voids(arr, valid, ~valid, 1.0, min_area_m2=1.0)
        assert not out.water.any()

    def test_non_positive_resolution_disables_area_check(self):
        """При нефизичном разрешении порог площади недостижим — воды нет."""
        arr, valid, _ = self._lake()
        out = flatten_water_voids(arr, valid, ~valid, 0.0)
        assert not out.water.any()


class TestPxFromMetres:

    def test_converts_by_resolution(self):
        assert px_from_metres(5.0, 0.5) == 10.0
        assert px_from_metres(5.0, 1.0) == 5.0

    def test_non_positive_inputs_give_zero(self):
        assert px_from_metres(0.0, 1.0) == 0.0
        assert px_from_metres(5.0, 0.0) == 0.0
        assert px_from_metres(-5.0, 1.0) == 0.0
