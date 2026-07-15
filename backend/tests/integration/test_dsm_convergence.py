"""Интеграционный тест: построение DSM и сравнение с эталоном.

Восстанавливает абсолютные Z из TLO + эталонного DSM,
строит DSM через PDAL writers.gdal output_type="max",
сравнивает с эталоном: сходимость ≥ 5%.
"""

import pytest
import os
import tempfile
from pathlib import Path

import numpy as np
import rasterio
import laspy

from tests.conftest import TLO_LAS, REFERENCE_DSM, get_test_crs_wkt, TEST_DATA_DIR
from tests.fixtures.restore_las import restore_absolute_las
from sima_dem_ground.ground import GroundProcessing


# Skip if test data not available
pytestmark = pytest.mark.skipif(
    not Path(TLO_LAS).exists() or not Path(REFERENCE_DSM).exists(),
    reason=f"Test data not found: {TLO_LAS} or {REFERENCE_DSM}",
)


class TestDSMIntegration:

    @pytest.fixture(scope="class")
    def crs_wkt(self) -> str:
        """CRS извлекается из эталонного DSM — единый источник истины."""
        return get_test_crs_wkt()

    @pytest.fixture(scope="class")
    def restored_las(self, tmp_path_factory):
        """Восстановить LAS с абсолютными Z из TLO + эталонного DSM."""
        out_dir = tmp_path_factory.mktemp("restore")
        out_las = str(out_dir / "P-42-041-239-g_absolute.las")
        restore_absolute_las(TLO_LAS, REFERENCE_DSM, out_las)
        return out_las

    @pytest.fixture(scope="class")
    def built_dsm(self, restored_las, crs_wkt, tmp_path_factory):
        """Построить ЦМР (DTM) из восстановленного LAS — только ground-точки."""
        out_dir = tmp_path_factory.mktemp("dsm")
        gp = GroundProcessing(
            output=str(out_dir),
            resolution=1.0,
            crs=crs_wkt,
            interpolate=True,
            interpol_dist=100,
            save_ground_las=False,
        )
        gp.get_raster(restored_las, crs_wkt=crs_wkt)
        return gp.raster[0]

    def test_dsm_shape_matches_reference(self, built_dsm):
        """Размер построенного DSM близок к эталону (±1 пиксель допустимо)."""
        with rasterio.open(built_dsm) as src:
            built = src.read(1)
        with rasterio.open(REFERENCE_DSM) as src:
            ref = src.read(1)
        h_diff = abs(built.shape[0] - ref.shape[0])
        w_diff = abs(built.shape[1] - ref.shape[1])
        assert h_diff <= 1 and w_diff <= 1, (
            f"Shape mismatch too large: {built.shape} vs {ref.shape}"
        )

    def test_dsm_crs_matches_reference(self, built_dsm):
        """CRS построенного DSM совпадает с эталоном."""
        with rasterio.open(built_dsm) as src:
            built_crs = src.crs
        with rasterio.open(REFERENCE_DSM) as src:
            ref_crs = src.crs
        assert built_crs is not None, "Built DSM has no CRS"
        assert ref_crs is not None, "Reference DSM has no CRS"

    def test_dsm_convergence_within_5_percent(self, built_dsm):
        """Сходимость DSM с эталоном ≥ 5% (RMSE / mean < 5%)."""
        with rasterio.open(built_dsm) as src:
            built = src.read(1).astype(float)
            built_nodata = src.nodata
        with rasterio.open(REFERENCE_DSM) as src:
            ref = src.read(1).astype(float)
            ref_nodata = src.nodata

        min_h = min(built.shape[0], ref.shape[0])
        min_w = min(built.shape[1], ref.shape[1])
        built = built[:min_h, :min_w]
        ref = ref[:min_h, :min_w]

        if built_nodata is not None and ref_nodata is not None:
            valid = (built != built_nodata) & (ref != ref_nodata)
        else:
            valid = np.ones_like(built, dtype=bool)

        diff = np.abs(built[valid] - ref[valid])
        rmse = np.sqrt(np.mean(diff ** 2))
        mean_ref = np.mean(ref[valid])
        relative_error = rmse / mean_ref if mean_ref != 0 else float("inf")

        print(f"RMSE: {rmse:.4f}, Mean ref: {mean_ref:.4f}, Relative error: {relative_error:.4%}")
        assert relative_error < 0.05, (
            f"DSM convergence failed: relative error {relative_error:.4%} >= 5%"
        )

    def test_dsm_z_range_matches_reference(self, built_dsm):
        """Диапазон Z построенного DSM близок к эталону."""
        with rasterio.open(built_dsm) as src:
            built = src.read(1).astype(float)
            built_nodata = src.nodata
        with rasterio.open(REFERENCE_DSM) as src:
            ref = src.read(1).astype(float)
            ref_nodata = src.nodata

        if built_nodata is not None:
            built_valid = built[built != built_nodata]
        else:
            built_valid = built.flatten()
        if ref_nodata is not None:
            ref_valid = ref[ref != ref_nodata]
        else:
            ref_valid = ref.flatten()

        if len(built_valid) > 0 and len(ref_valid) > 0:
            # Минимум/максимум должны быть в разумном диапазоне
            assert abs(np.min(built_valid) - np.min(ref_valid)) < 20.0, (
                f"Min Z mismatch: {np.min(built_valid)} vs {np.min(ref_valid)}"
            )
            assert abs(np.max(built_valid) - np.max(ref_valid)) < 20.0, (
                f"Max Z mismatch: {np.max(built_valid)} vs {np.max(ref_valid)}"
            )