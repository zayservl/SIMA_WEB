"""Тесты пространственного прореживания по минимальному расстоянию."""

import numpy as np

from sima_dem_core.thinning import thin_by_min_distance


def _min_pairwise(pts: np.ndarray) -> float:
    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    return float(d.min())


class TestThinByMinDistance:

    def test_empty_input(self):
        assert thin_by_min_distance(np.array([]), np.array([]), 10).size == 0

    def test_zero_distance_keeps_all(self):
        x = np.arange(10, dtype=float)
        y = np.zeros(10)
        keep = thin_by_min_distance(x, y, 0)
        assert keep.tolist() == list(range(10))

    def test_dense_line_respects_distance(self):
        """Плотная линия точек с шагом 1 м при пороге 5 м."""
        x = np.arange(0, 100, 1.0)
        y = np.zeros_like(x)
        keep = thin_by_min_distance(x, y, 5.0)
        pts = np.column_stack([x[keep], y[keep]])
        assert len(keep) < len(x)
        assert _min_pairwise(pts) >= 5.0 - 1e-9

    def test_random_cloud_respects_distance(self):
        """Случайное облако: гарантия минимального расстояния сохраняется."""
        rng = np.random.default_rng(42)
        x = rng.uniform(0, 100, 3000)
        y = rng.uniform(0, 100, 3000)
        keep = thin_by_min_distance(x, y, 4.0)
        pts = np.column_stack([x[keep], y[keep]])
        assert _min_pairwise(pts) >= 4.0 - 1e-9
        # Прореживание не должно вырождаться: на 100×100 м с шагом 4 м
        # помещается заметно больше сотни точек.
        assert len(keep) > 100

    def test_sparse_cloud_keeps_everything(self):
        """Точки и так дальше порога — все сохраняются."""
        x = np.array([0.0, 50.0, 100.0])
        y = np.array([0.0, 50.0, 100.0])
        keep = thin_by_min_distance(x, y, 10.0)
        assert keep.tolist() == [0, 1, 2]

    def test_indices_are_sorted(self):
        rng = np.random.default_rng(7)
        x = rng.uniform(0, 30, 500)
        y = rng.uniform(0, 30, 500)
        keep = thin_by_min_distance(x, y, 3.0)
        assert np.all(np.diff(keep) > 0)
