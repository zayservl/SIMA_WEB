"""Согласие сегментации крон с эталонным набором полигонов."""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from sima_forest_cmd import crown_iou, rasterize_polygons


def box(rows, cols, shape=(20, 20), label=1):
    labels = np.zeros(shape, dtype=np.int64)
    labels[rows[0]:rows[1], cols[0]:cols[1]] = label
    return labels


class TestIoU:
    def test_идентичные_наборы(self):
        a = box((2, 8), (2, 8))
        a[12:18, 12:18] = 2
        result = crown_iou(a, a)
        assert result.mean_iou == pytest.approx(1.0)
        assert result.matched_share == pytest.approx(1.0)
        assert result.unmatched_reference == 0
        assert result.unmatched_ours == 0

    def test_непересекающиеся(self):
        result = crown_iou(box((2, 8), (2, 8)), box((2, 8), (10, 16)))
        assert result.mean_iou == 0.0
        assert result.unmatched_reference == 1
        assert result.unmatched_ours == 1

    def test_смещение_на_половину(self):
        # пересечение 6x3=18, объединение 36+36-18=54
        result = crown_iou(box((2, 8), (2, 8)), box((2, 8), (5, 11)))
        assert result.iou[0] == pytest.approx(18 / 54)

    def test_порог_сопоставления(self):
        ours, reference = box((2, 8), (2, 8)), box((2, 8), (5, 11))
        assert crown_iou(ours, reference, threshold=0.3).matched_share == 1.0
        assert crown_iou(ours, reference, threshold=0.5).matched_share == 0.0

    def test_слипшаяся_крона_видна_по_числу_пар(self):
        # одна наша крона накрывает две эталонные: обе сопоставлены с ней же
        ours = box((2, 18), (2, 18))
        reference = np.zeros((20, 20), dtype=np.int64)
        reference[2:10, 2:18] = 1
        reference[10:18, 2:18] = 2
        result = crown_iou(ours, reference)
        assert result.n_reference == 2
        assert result.n_ours == 1
        assert result.unmatched_ours == 0        # наша крона использована

    def test_лишние_наши_кроны(self):
        ours = np.zeros((20, 20), dtype=np.int64)
        ours[2:8, 2:8] = 1
        ours[12:18, 12:18] = 2                   # эталон её не знает
        result = crown_iou(ours, box((2, 8), (2, 8)))
        assert result.unmatched_ours == 1

    def test_пустой_эталон(self):
        result = crown_iou(box((2, 8), (2, 8)), np.zeros((20, 20), dtype=np.int64))
        assert result.n_reference == 0
        assert result.matched_share == 0.0

    def test_разные_формы_отвергаются(self):
        with pytest.raises(ValueError, match="не совпадают"):
            crown_iou(np.zeros((5, 5), dtype=np.int64), np.zeros((6, 6), dtype=np.int64))

    def test_лучшая_пара_выбирается_по_максимуму_перекрытия(self):
        # эталонная крона перекрыта нашей №2 сильнее, чем нашей №1
        ours = np.zeros((20, 20), dtype=np.int64)
        ours[2:8, 2:4] = 1
        ours[2:8, 4:12] = 2
        reference = box((2, 8), (2, 12))
        result = crown_iou(ours, reference)
        assert result.iou[0] == pytest.approx(48 / 60)


class TestRasterize:
    def test_полигон_попадает_в_свои_ячейки(self):
        transform = from_origin(0.0, 10.0, 0.5, 0.5)
        geom = {"type": "Polygon", "coordinates": [
            [(1.0, 8.0), (1.0, 9.0), (2.0, 9.0), (2.0, 8.0), (1.0, 8.0)]]}
        labels = rasterize_polygons([geom], (20, 20), transform)
        assert labels.max() == 1
        assert (labels == 1).sum() == pytest.approx(4, abs=2)

    def test_несколько_полигонов_нумеруются_подряд(self):
        transform = from_origin(0.0, 10.0, 0.5, 0.5)
        geoms = [
            {"type": "Polygon", "coordinates": [
                [(0.5, 9.0), (0.5, 9.5), (1.0, 9.5), (1.0, 9.0), (0.5, 9.0)]]},
            {"type": "Polygon", "coordinates": [
                [(3.0, 6.0), (3.0, 6.5), (3.5, 6.5), (3.5, 6.0), (3.0, 6.0)]]},
        ]
        labels = rasterize_polygons(geoms, (20, 20), transform)
        assert set(np.unique(labels)) == {0, 1, 2}

    def test_пустой_список(self):
        labels = rasterize_polygons([], (10, 10), from_origin(0.0, 5.0, 0.5, 0.5))
        assert labels.max() == 0
