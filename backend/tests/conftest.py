"""Конфигурация pytest: пути к тестовым данным."""

import os
from pathlib import Path

import rasterio

# Базовые пути
BACKEND_DIR = Path(__file__).parent.parent
TEST_DATA_DIR = Path(os.environ.get(
    "SIMA_TEST_DATA",
    str(Path(__file__).parent.parent.parent.parent / "test_data"),
))

# Тестовые файлы
TLO_LAS = str(TEST_DATA_DIR / "P-42-041-239-g_ground_TLO.las")
REFERENCE_DSM = str(TEST_DATA_DIR / "P-42-041-239-g_DSM.tif")
AFS_TIF = str(TEST_DATA_DIR / "P-42-041-239-g.tif")


def extract_crs_from_raster(raster_path: str) -> str:
    """Извлечь CRS из растра как WKT-строку.

    Единый источник истины для CRS тестовых данных — сам эталонный TIFF.
    Раньше CRS был захардкожен как TEST_CRS_WKT, что могло рассинхронизироваться
    с реальными метаданными файла.
    """
    with rasterio.open(raster_path) as src:
        return src.crs.to_wkt()


def get_test_crs_wkt() -> str:
    """CRS тестовых данных (SK42 Transverse Mercator), извлечённый из эталонного DSM."""
    return extract_crs_from_raster(REFERENCE_DSM)


# Обратная совместимость: TEST_CRS_WKT вычисляется лениво при первом обращении.
# Новому коду следует использовать get_test_crs_wkt() или extract_crs_from_raster().
class _LazyCRS:
    __slots__ = ("_value",)
    def __init__(self) -> None:
        self._value = None
    def __str__(self) -> str:
        if self._value is None:
            self._value = get_test_crs_wkt()
        return self._value
    def __eq__(self, other: object) -> bool:
        return str(self) == str(other)
    def __hash__(self) -> int:
        return hash(str(self))

TEST_CRS_WKT = _LazyCRS()