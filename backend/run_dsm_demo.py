#!/usr/bin/env python3
"""Запуск построения ЦМР/DTM/DSM на двух датасетах.

Все параметры инкапсулированы в DemoConfig. CRS извлекается из эталонного TIFF/АФС.
Интерполяция — только внутренних дырок, без экстраполяции краёв.
Склоны/экспозиции строятся по сглаженной DTM.
Пути к данным настраиваются через переменные окружения SIMA_DATA_DIR / SIMA_OUTPUT_DIR.
"""

import os, sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import rasterio, numpy as np

backend = Path(__file__).parent
for pkg in ["packages/sima-dem-core/src", "packages/sima-dem-ground/src",
            "packages/sima-dem-dsm/src", "packages/sima-dem-pipeline/src"]:
    sys.path.insert(0, str(backend / pkg))

from sima_dem_ground.ground import GroundProcessing, SMRFConfig, FillConfig
from sima_dem_dsm.dsm import DSMBuilder, DSMConfig
from sima_dem_core.curvature import CurvatureProcessing
from sima_dem_core.raster.smooth import gauss_smooth
from sima_dem_core.raster.tpi import calculate_tpi, TPIConfig
from sima_dem_core.check_classification import CheckClassification


# ── Конфигурация путей (через env, без хардкода) ──────────────────────────

_SIMA_ROOT = Path(os.environ.get(
    "SIMA_DATA_DIR",
    str(Path(__file__).resolve().parent.parent.parent),  # ../..
))
_OUTPUT_ROOT = Path(os.environ.get(
    "SIMA_OUTPUT_DIR",
    str(backend / "output"),
))

DEMO_DIR = _SIMA_ROOT / "23_04_12_digital_elevation_1-46-315" / "demo_data"
TEST_DIR = _SIMA_ROOT / "test_data"
OUT_DIR = _OUTPUT_ROOT


# ── Конфигурация обработки (все параметры инкапсулированы) ────────────────

@dataclass
class DemoProcessingConfig:
    """Все параметры построения ЦМР/DTM/DSM — без хардкода."""

    # Разрешение выходного растра (м)
    resolution: float = 1.0

    # SMRF — Simple Morphological Filter
    smrf: SMRFConfig = field(default_factory=SMRFConfig)

    # Интерполяция дырок (без экстраполяции краёв)
    interpolate: bool = True
    fill_holes: bool = True
    max_search_distance: int = 100

    # Сглаживание (гауссов фильтр)
    gauss_sigma: float = 2.0
    gauss_order: int = 0
    gauss_window: int = 5

    # TPI
    tpi_res: float = 10.0
    tpi_config: TPIConfig = field(default_factory=TPIConfig)

    # DSM (ЦМД — все точки, max)
    build_dsm: bool = True
    dsm_resolution: float = 1.0


def extract_crs(tif_path: str) -> str:
    """Извлечь CRS из растра как WKT-строку — единый источник истины."""
    with rasterio.open(tif_path) as src:
        return src.crs.to_wkt()


def process(name: str, las_path: str, crs: str, out_dir: str,
            ref_dsm: Optional[str] = None,
            cfg: Optional[DemoProcessingConfig] = None) -> None:
    """Построить ЦМР/DTM/DSM с заданными параметрами."""
    cfg = cfg or DemoProcessingConfig()
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n{'='*60}\nДАТАСЕТ: {name}\n{'='*60}")
    print(f"LAS:   {las_path}")
    print(f"Выход: {out_dir}")
    print(f"CRS:   {crs[:80]}...")
    print(f"Параметры: resolution={cfg.resolution}, sigma={cfg.gauss_sigma}, "
          f"tpi_res={cfg.tpi_res}, build_dsm={cfg.build_dsm}")

    if ref_dsm:
        print("\n0. Восстановление абсолютных Z...")
        sys.path.insert(0, str(backend))
        from tests.fixtures.restore_las import restore_absolute_las
        restored = str(Path(out_dir) / "restored_absolute.las")
        restore_absolute_las(las_path, ref_dsm, restored)
        las_path = restored

    # 1. DTM (ЦМР — ground, SMRF, интерполяция дырок, без экстраполяции краёв)
    print("\n1. DTM (SMRF + интерполяция дырок)...")
    gp = GroundProcessing(
        output=out_dir, resolution=cfg.resolution, crs=crs,
        interpolate=cfg.interpolate, save_ground_las=False,
        smrf=cfg.smrf,
        fill=FillConfig(fill_holes=cfg.fill_holes,
                        max_search_distance=cfg.max_search_distance,
                        fallback_to_min_z=True),
    )
    gp.get_raster(las_path, crs_wkt=crs)
    dtm = gp.raster[0]
    print(f"   {dtm}")

    # 2. Сглаживание (с интерполяцией дырок перед gauss)
    print("2. Сглаживание (с интерполяцией дырок)...")
    stem = Path(dtm).stem.replace("_dem", "")
    smoothed = str(Path(out_dir) / (stem + "_dem_smooth.tif"))
    gauss_smooth(dtm, smoothed,
                 sigma=cfg.gauss_sigma, order=cfg.gauss_order,
                 window_size=cfg.gauss_window,
                 fill_holes=cfg.fill_holes,
                 max_search_distance=cfg.max_search_distance)
    print(f"   {smoothed}")

    # 3. Уклоны — по сглаженной DTM (#4)
    print("3. Уклоны (по сглаженной DTM)...")
    cp = CurvatureProcessing()
    slope = cp.calculate_slope(smoothed, crs,
                               cfg.resolution, cfg.resolution, out_dir)
    print(f"   {slope}")

    # 4. Экспозиции — по сглаженной DTM (#4)
    print("4. Экспозиции (по сглаженной DTM)...")
    aspect = cp.calculate_aspect(smoothed, crs,
                                  cfg.resolution, cfg.resolution, out_dir)
    print(f"   {aspect}")

    # 5. TPI — по сглаженной DTM
    print("5. TPI (по сглаженной DTM)...")
    tpi = calculate_tpi(smoothed, crs, out_dir,
                        cfg.resolution, cfg.tpi_res, cfg.tpi_config)
    print(f"   {tpi}")

    # 6. DSM (ЦМД — все точки, max)
    if cfg.build_dsm:
        print("6. DSM (все точки, max)...")
        builder = DSMBuilder(
            output=out_dir, crs=crs,
            config=DSMConfig(resolution=cfg.dsm_resolution,
                             interpolate=cfg.interpolate,
                             fill_holes=cfg.fill_holes),
        )
        dsm_path = builder.build(las_path, crs_wkt=crs)
        print(f"   {dsm_path}")

    # Результаты
    print(f"\n--- Результаты: {name} ---")
    files = [("DTM", dtm), ("Сглаженная", smoothed), ("Уклоны", slope),
             ("Экспозиции", aspect), ("TPI", tpi)]
    if cfg.build_dsm:
        files.append(("DSM", dsm_path))
    for label, path in files:
        try:
            ds = rasterio.open(path)
            arr = ds.read(1)
            valid = arr[arr != ds.nodata] if ds.nodata is not None else arr.flatten()
            print(f"  {label}: {ds.width}x{ds.height}, Z={np.min(valid):.2f}-{np.max(valid):.2f}, "
                  f"mean={np.mean(valid):.2f}, {os.path.getsize(path)/1024/1024:.1f} MB")
            print(f"         {path}")
        except Exception as e:
            print(f"  {label}: ERROR {e}")

    # Сравнение с эталоном
    if ref_dsm and os.path.exists(ref_dsm):
        print(f"\n--- Сравнение с эталоном ---")
        with rasterio.open(dtm) as src:
            built = src.read(1).astype(float)
            b_nd = src.nodata
        with rasterio.open(ref_dsm) as src:
            ref = src.read(1).astype(float)
            r_nd = src.nodata
        min_h, min_w = min(built.shape[0], ref.shape[0]), min(built.shape[1], ref.shape[1])
        built, ref = built[:min_h, :min_w], ref[:min_h, :min_w]
        valid = (built != b_nd) & (ref != r_nd)
        diff = np.abs(built[valid] - ref[valid])
        rmse = float(np.sqrt(np.mean(diff**2)))
        mean_ref = float(np.mean(ref[valid]))
        rel = rmse / mean_ref if mean_ref else float("inf")
        print(f"  RMSE: {rmse:.4f}, Mean: {mean_ref:.4f}, Ошибка: {rel:.4%}")
        print(f"  Требование < 5%: {'✓ ПРОЙДЕН' if rel < 0.05 else '✗ НЕ ПРОЙДЕН'}")


def main():
    print("=" * 60)
    print("СИМА — ЦМР/DTM/DSM (параметры в DemoProcessingConfig, пути через env)")
    print("=" * 60)

    cfg = DemoProcessingConfig()

    # demo_data — CRS из АФС (00000100.tif)
    process("demo_data (pt000100.las)",
            str(DEMO_DIR / "pt000100.las"),
            extract_crs(str(DEMO_DIR / "00000100.tif")),
            str(OUT_DIR / "demo_data"),
            cfg=cfg)

    # test_data — CRS из эталонного DSM
    process("test_data (P-42-041-239-g, TLO + восстановление)",
            str(TEST_DIR / "P-42-041-239-g_ground_TLO.las"),
            extract_crs(str(TEST_DIR / "P-42-041-239-g_DSM.tif")),
            str(OUT_DIR / "test_data"),
            ref_dsm=str(TEST_DIR / "P-42-041-239-g_DSM.tif"),
            cfg=cfg)

    print(f"\n{'='*60}\nВСЕ РЕЗУЛЬТАТЫ: {OUT_DIR}\n{'='*60}")
    for dp, dn, fns in os.walk(OUT_DIR):
        for f in sorted(fns):
            if f.endswith((".tif", ".las")):
                p = os.path.join(dp, f)
                print(f"  {p}  ({os.path.getsize(p)/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()