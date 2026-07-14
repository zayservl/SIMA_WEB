"""Конфигурация pytest: пути к тестовым данным."""

import os
from pathlib import Path

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

# CRS тестовых данных (SK42 Transverse Mercator, central_meridian=66.05)
TEST_CRS_WKT = (
    'PROJCS["TRANSVERSE MERCATOR_M_D_SK42GOST51794-2008",'
    'GEOGCS["unknown",'
    'DATUM["unnamed",'
    'SPHEROID["Krassowsky 1940",6378245,298.300000376014]],'
    'TOWGS84[23.57,-140.95,-79.8,0,0.35,0.79,-0.22],'
    'PRIMEM["Greenwich",0],'
    'UNIT["degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",0],'
    'PARAMETER["central_meridian",66.05],'
    'PARAMETER["scale_factor",1],'
    'PARAMETER["false_easting",2500000],'
    'PARAMETER["false_northing",-5811057.63],'
    'UNIT["metre",1]]'
)