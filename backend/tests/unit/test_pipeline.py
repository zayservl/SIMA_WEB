"""Тесты pipeline.py (оркестрация конвейера рельефа)."""

import pytest
import laspy
import numpy as np
from pathlib import Path

from sima_dem_pipeline.pipeline import ReliefPipeline, PipelineConfig

# CRS для синтетических unit-тестов (произвольная UTM-зона — данные синтетические).
TEST_UNIT_CRS = "EPSG:32642"


def _make_test_las(path: str, n: int = 500) -> str:
    """Создать тестовый LAS с ground-точками."""
    las = laspy.create(point_format=3, file_version="1.2")
    xs = np.linspace(0, 100, n, dtype=np.float64)
    ys = np.linspace(0, 100, n, dtype=np.float64)
    zs = np.linspace(90, 110, n, dtype=np.float64)
    las.x = xs
    las.y = ys
    las.z = zs
    las.classification = np.array([2] * n, dtype=np.uint8)  # Ground
    las.write(path)
    return path


class TestPipelineConfig:

    def test_config_defaults(self):
        """PipelineConfig имеет корректные дефолты."""
        config = PipelineConfig(
            las_catalog="/tmp/las",
            output_dir="/tmp/out",
            resolution=1.0,
            crs=TEST_UNIT_CRS,
        )
        assert config.filter_type is None
        assert config.do_tpi is False
        assert config.do_slopes is False


class TestReliefPipeline:

    def test_pipeline_no_filters(self, tmp_path):
        """Pipeline без фильтров: ЦМР из ground-точек."""
        las_dir = tmp_path / "las"
        las_dir.mkdir()
        _make_test_las(str(las_dir / "test.las"), n=200)
        out_dir = tmp_path / "out"
        config = PipelineConfig(
            las_catalog=str(las_dir),
            output_dir=str(out_dir),
            resolution=1.0,
            crs=TEST_UNIT_CRS,
            save_ground_las=False,
        )
        pipeline = ReliefPipeline(config)
        result = pipeline.run()
        assert len(result.dem_rasters) >= 1

    def test_pipeline_with_manual_filter(self, tmp_path):
        """Pipeline с manual-фильтром."""
        las_dir = tmp_path / "las"
        las_dir.mkdir()
        _make_test_las(str(las_dir / "test.las"), n=200)
        out_dir = tmp_path / "out"
        config = PipelineConfig(
            las_catalog=str(las_dir),
            output_dir=str(out_dir),
            resolution=1.0,
            crs=TEST_UNIT_CRS,
            filter_type="manual",
            z_min=0.0,
            z_max=200.0,
            save_ground_las=False,
        )
        pipeline = ReliefPipeline(config)
        result = pipeline.run()
        assert len(result.dem_rasters) >= 1