#!/usr/bin/env python3
"""Запуск построения ЦМР/DTM/DSM на двух датасетах.

Все параметры инкапсулированы. CRS извлекается из эталонного TIFF/АФС.
Интерполяция — только внутренних дырок, без экстраполяции краёв.
Склоны/экспозиции строятся по сглаженной DTM.
"""

import os, sys
from pathlib import Path
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

SIMA = Path("/Users/sergeyzay/Documents/НЕДРА/СИМА")
DEMO = SIMA / "23_04_12_digital_elevation_1-46-315" / "demo_data"
TEST = SIMA / "test_data"
OUT = SIMA / "sima-web" / "backend" / "output"


def extract_crs(tif_path):
    with rasterio.open(tif_path) as src:
        return src.crs.to_wkt()


def process(name, las_path, crs, out_dir, ref_dsm=None, build_dsm=False):
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n{'='*60}\nДАТАСЕТ: {name}\n{'='*60}")
    print(f"LAS:   {las_path}")
    print(f"Выход: {out_dir}")

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
        output=out_dir, resolution=1.0, crs=crs,
        interpolate=True, save_ground_las=False,
        smrf=SMRFConfig(),  # slope=0.2, window=16, threshold=0.45, scalar=1.2
        fill=FillConfig(fill_holes=True, max_search_distance=100),
    )
    gp.get_raster(las_path, crs_wkt=crs)
    dtm = gp.raster[0]
    print(f"   {dtm}")

    # 2. Сглаживание (с интерполяцией дырок перед gauss)
    print("2. Сглаживание (с интерполяцией дырок)...")
    stem = Path(dtm).stem.replace("_dem", "")
    smoothed = str(Path(out_dir) / (stem + "_dem_smooth.tif"))
    gauss_smooth(dtm, smoothed, sigma=2.0, order=0, window_size=5,
                 fill_holes=True, max_search_distance=100)
    print(f"   {smoothed}")

    # 3. Уклоны — по сглаженной DTM (#4)
    print("3. Уклоны (по сглаженной DTM)...")
    cp = CurvatureProcessing()
    slope = cp.calculate_slope(smoothed, crs, 1.0, 1.0, out_dir)
    print(f"   {slope}")

    # 4. Экспозиции — по сглаженной DTM (#4)
    print("4. Экспозиции (по сглаженной DTM)...")
    aspect = cp.calculate_aspect(smoothed, crs, 1.0, 1.0, out_dir)
    print(f"   {aspect}")

    # 5. TPI — по сглаженной DTM
    print("5. TPI (по сглаженной DTM)...")
    tpi = calculate_tpi(smoothed, crs, out_dir, 1.0, 10.0, TPIConfig())
    print(f"   {tpi}")

    # 6. DSM (ЦМД — все точки, max)
    if build_dsm:
        print("6. DSM (все точки, max)...")
        builder = DSMBuilder(
            output=out_dir, crs=crs,
            config=DSMConfig(resolution=1.0, interpolate=True, fill_holes=True),
        )
        dsm_path = builder.build(las_path, crs_wkt=crs)
        print(f"   {dsm_path}")

    # Результаты
    print(f"\n--- Результаты: {name} ---")
    files = [("DTM", dtm), ("Сглаженная", smoothed), ("Уклоны", slope),
             ("Экспозиции", aspect), ("TPI", tpi)]
    if build_dsm:
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
    print("СИМА — ЦМР/DTM/DSM (параметры инкапсулированы, без хардкода)")
    print("=" * 60)

    # demo_data
    process("demo_data (pt000100.las)",
            str(DEMO / "pt000100.las"),
            extract_crs(str(DEMO / "00000100.tif")),
            str(OUT / "demo_data"),
            build_dsm=True)

    # test_data
    process("test_data (P-42-041-239-g, TLO + восстановление)",
            str(TEST / "P-42-041-239-g_ground_TLO.las"),
            extract_crs(str(TEST / "P-42-041-239-g_DSM.tif")),
            str(OUT / "test_data"),
            ref_dsm=str(TEST / "P-42-041-239-g_DSM.tif"),
            build_dsm=True)

    print(f"\n{'='*60}\nВСЕ РЕЗУЛЬТАТЫ: {OUT}\n{'='*60}")
    for dp, dn, fns in os.walk(OUT):
        for f in sorted(fns):
            if f.endswith((".tif", ".las")):
                p = os.path.join(dp, f)
                print(f"  {p}  ({os.path.getsize(p)/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()