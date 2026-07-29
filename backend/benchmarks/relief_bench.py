"""Харнесс бенчмаркинга сервиса рельефа (sima-relief-service) на датасете триплетов.

Датасет: <root>/{OFP,LAS,DSM} — триплеты подбираются по имени номенклатурного
листа (stem файла ОФП):

    OFP/<stem>.tif              — аэрофотоснимок (АФС)
    LAS/<stem>_ground_TLO.las   — облако ВЛС (Z = HeightAboveGround, ТЛО)
    DSM/<n>/<stem>.tif          — эталонная ЦМР, посчитанная ранее независимо

Замеряется:
  * время каждого шага конвейера (crop/filter/dtm/dsm/smooth/slope/aspect/tpi/
    contours/tin/heights) и суммарное время тайла — из TileStep.duration_ms;
  * время подготовительных операций вне сервиса (оценка материалов, восстановление
    абсолютных Z, расчёт метрик);
  * точность ЦМР/ЦММ относительно эталона (ME/MAE/RMSE/NMAD/P95/coverage).

ВАЖНО о методологии (см. `restore_absolute()`): ВЛС в датасете хранит ТЛО —
нормализованные высоты. Абсолютные Z восстанавливаются по эталонной ЦМР, поэтому
сравнение построенной ЦМР с эталоном измеряет точность *растеризации и
реконструкции поверхности* сервисом (SMRF-классификация → IDW → заполнение дыр),
а не независимую точность съёмки. Это ограничение исходных данных, не харнесса.

CLI:
    python benchmarks/relief_bench.py --limit 5 --out benchmarks/results
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator, Optional

BACKEND = Path(__file__).resolve().parent.parent
for _pkg in (
    "packages/sima-dem-core/src",
    "packages/sima-dem-ground/src",
    "packages/sima-dem-dsm/src",
    "packages/sima-relief-service/src",
):
    _p = str(BACKEND / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import warnings  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

import laspy  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.warp import Resampling, reproject  # noqa: E402

from sima_relief_service import (  # noqa: E402
    DerivativesParams,
    DsmParams,
    HeightsParams,
    ReliefParams,
    ReliefRequest,
    ReliefService,
    SmoothingParams,
    SmrfParams,
    TileInput,
    VectorsParams,
    assess_materials,
)
from sima_relief_service import steps as S  # noqa: E402

# Порядок шагов конвейера — для стабильных колонок в таблицах времени.
STEP_ORDER = [
    "crop", "filter", "dtm", "dsm", "smooth",
    "slope", "aspect", "tpi", "contours", "tin", "heights",
]

# Какой шаг породил какой выходной слой (для отчёта «время на каждый результат»).
LAYER_STEP = {
    "dtm": "dtm",
    "ground_las": "dtm",
    "dsm": "dsm",
    "dtm_smooth": "smooth",
    "slope": "slope",
    "aspect": "aspect",
    "tpi": "tpi",
    "contours": "contours",
    "tin": "tin",
    "heights": "heights",
}


# --- 1. Поиск триплетов -------------------------------------------------

@dataclass
class Triplet:
    name: str          # stem номенклатурного листа, напр. 'P-42-041-239-g'
    ofp: str           # АФС GeoTIFF
    las: str           # ВЛС LAS (ТЛО)
    ref: str           # эталонная ЦМР GeoTIFF


def find_triplets(root: str, las_suffix: str = "_ground_TLO") -> list[Triplet]:
    """Отобрать триплеты (ОФП + ВЛС + эталон) по имени файла ОФП."""
    r = Path(root)
    ofp = {p.stem: p for p in sorted((r / "OFP").glob("*.tif"))}
    las = {p.stem[: -len(las_suffix)] if p.stem.endswith(las_suffix) else p.stem: p
           for p in sorted((r / "LAS").glob("*.las"))}
    ref: dict[str, Path] = {}
    for p in sorted((r / "DSM").rglob("*.tif")):
        ref.setdefault(p.stem, p)  # первый по сортировке — детерминированно
    names = sorted(set(ofp) & set(las) & set(ref))
    return [Triplet(n, str(ofp[n]), str(las[n]), str(ref[n])) for n in names]


# --- 2. Подготовка: восстановление абсолютных Z из ТЛО -------------------

def restore_absolute(tlo_path: str, reference_path: str, out_path: str) -> str:
    """Восстановить абсолютные Z из ТЛО по эталонной ЦМР.

    Ground-точки (Classification==2) получают Z эталона в своей ячейке,
    остальные — Z эталона + HeightAboveGround. Точки вне эталона отбрасываются
    (в отличие от tests/fixtures/restore_las.py, где им присваивалось среднее
    по растру — это вносило искусственные плато на краях тайла).
    """
    las = laspy.read(tlo_path)
    x = np.asarray(las.x)
    y = np.asarray(las.y)
    z_hag = np.asarray(las.z, dtype=float)
    cls = np.asarray(las.classification)

    with rasterio.open(reference_path) as ref:
        data = ref.read(1).astype(float)
        nodata = ref.nodata
        inv = ~ref.transform
    if nodata is not None:
        data = np.where(data == nodata, np.nan, data)

    cols, rows = inv * (x, y)
    rows = np.floor(rows).astype(int)
    cols = np.floor(cols).astype(int)
    h, w = data.shape
    inside = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)

    z_ground = np.full(len(x), np.nan)
    z_ground[inside] = data[rows[inside], cols[inside]]
    keep = np.isfinite(z_ground)

    z_abs = np.where(cls == 2, z_ground, z_ground + z_hag)

    # Подрезка без .copy(): ScaleAwarePointRecord теряет scales/offsets при копии.
    las.points = las.points[keep]
    las.z = z_abs[keep]
    las.write(out_path)
    return out_path


# --- 3. Параметры расчёта (совпадают с relief_demo.ipynb) ---------------

def default_params(crs_wkt: str, resolution: float = 1.0) -> ReliefParams:
    """Параметры Q3, выровненные с легаси-прототипом и relief_demo.ipynb."""
    return ReliefParams(
        target_crs=crs_wkt,
        filter_method="smrf",
        smrf=SmrfParams(slope=0.2, window=16, threshold=0.45, scalar=1.2),
        smoothing=SmoothingParams(enabled=True, sigma=2.0, order=0, window=5),
        dsm=DsmParams(enabled=True, output_type="max", interpolate=True, fill_holes=True),
        derivatives=DerivativesParams(
            slopes=True, slopes_res=resolution,
            aspect=True, aspect_res=resolution,
            tpi=True, tpi_radii=[270, 810, 2430],
            interpolation=True, inter_amp=100,
        ),
        vectors=VectorsParams(horizontals=[0.5, 2.0, 5.0, 10.0], tin=True),
        heights=HeightsParams(enabled=True, source="las", step=10),
        deterministic=True, seed=42,
    )


# --- 4. Метрики точности -------------------------------------------------

def _read_masked(path: str) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        arr = src.read(1).astype("float64")
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        prof = {"transform": src.transform, "crs": src.crs, "shape": src.shape}
    return arr, prof


def align_to_reference(src_path: str, ref_path: str) -> tuple[np.ndarray, np.ndarray]:
    """Перепроецировать растр на сетку эталона. Возвращает (candidate, reference)."""
    ref_arr, ref_prof = _read_masked(ref_path)
    with rasterio.open(src_path) as src:
        dst = np.full(ref_prof["shape"], np.nan, dtype="float64")
        src_arr = src.read(1).astype("float64")
        if src.nodata is not None:
            src_arr = np.where(src_arr == src.nodata, np.nan, src_arr)
        reproject(
            source=src_arr,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs or ref_prof["crs"],
            src_nodata=np.nan,
            dst_transform=ref_prof["transform"],
            dst_crs=ref_prof["crs"],
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
    return dst, ref_arr


def accuracy_metrics(src_path: str, ref_path: str) -> dict:
    """Метрики отклонения растра от эталонной ЦМР (в метрах)."""
    cand, ref = align_to_reference(src_path, ref_path)
    valid = np.isfinite(cand) & np.isfinite(ref)
    n = int(valid.sum())
    n_ref = int(np.isfinite(ref).sum())
    out = {
        "n_valid": n,
        "n_ref_valid": n_ref,
        "coverage_pct": 100.0 * n / n_ref if n_ref else 0.0,
        "ref_mean": float(np.nanmean(ref)) if n_ref else float("nan"),
    }
    if n == 0:
        out.update({k: float("nan") for k in
                    ("me", "mae", "rmse", "std", "nmad", "p68", "p95", "max_abs", "rel_rmse_pct")})
        return out
    d = cand[valid] - ref[valid]
    ad = np.abs(d)
    med = float(np.median(d))
    out.update({
        "me": float(np.mean(d)),
        "mae": float(np.mean(ad)),
        "rmse": float(np.sqrt(np.mean(d ** 2))),
        "std": float(np.std(d)),
        "nmad": float(1.4826 * np.median(np.abs(d - med))),
        "p68": float(np.percentile(ad, 68.3)),
        "p95": float(np.percentile(ad, 95.0)),
        "max_abs": float(np.max(ad)),
    })
    out["rel_rmse_pct"] = 100.0 * out["rmse"] / out["ref_mean"] if out["ref_mean"] else float("nan")
    return out


def raster_stats(path: str) -> dict:
    arr, _ = _read_masked(path)
    v = arr[np.isfinite(arr)]
    if v.size == 0:
        return {"z_min": float("nan"), "z_max": float("nan"), "z_mean": float("nan"),
                "z_std": float("nan"), "valid_pct": 0.0}
    return {
        "z_min": float(v.min()), "z_max": float(v.max()),
        "z_mean": float(v.mean()), "z_std": float(v.std()),
        "valid_pct": 100.0 * v.size / arr.size,
    }


# --- 5. Прогон одного триплета ------------------------------------------

@contextmanager
def timed(store: dict, key: str) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        store[key] = (time.perf_counter() - t0) * 1000.0


def run_triplet(
    tri: Triplet,
    out_root: str,
    resolution: float = 1.0,
    keep_outputs: bool = False,
) -> dict:
    """Прогнать полный конвейер на одном триплете и собрать время + точность."""
    rec: dict = {"name": tri.name, "ofp": tri.ofp, "las": tri.las, "ref": tri.ref,
                 "status": "failed", "reason": None}
    prep: dict = {}
    tile_dir = Path(out_root) / tri.name
    tile_dir.mkdir(parents=True, exist_ok=True)

    try:
        with rasterio.open(tri.ref) as src:
            crs_wkt = src.crs.to_wkt()
            rec["ref_shape"] = list(src.shape)
            rec["ref_res_m"] = float(abs(src.transform.a))
            rec["ref_area_km2"] = float(
                abs(src.bounds.right - src.bounds.left)
                * abs(src.bounds.top - src.bounds.bottom) / 1e6)
        rec["ofp_size_mb"] = os.path.getsize(tri.ofp) / 1e6
        rec["las_size_mb"] = os.path.getsize(tri.las) / 1e6

        # 0. Оценка материалов (Q3 «Оценка файлов ВЛС/АФС»)
        with timed(prep, "assess_ms"):
            assessment = assess_materials(vls_files=[tri.las], afs_files=[tri.ofp])
        if assessment.vls:
            rec["las_points_density"] = assessment.vls.density_pts_m2
            rec["tlo_range_m"] = list(assessment.vls.tlo_height_range_m)
        if assessment.afs:
            rec["ofp_res_m"] = assessment.afs.resolution_m

        # 0b. Подготовка: ТЛО → абсолютные Z (вне сервиса, по эталону)
        abs_las = str(tile_dir / f"{tri.name}_abs.las")
        with timed(prep, "restore_ms"):
            restore_absolute(tri.las, tri.ref, abs_las)
        with laspy.open(abs_las) as f:
            rec["n_points"] = int(f.header.point_count)

        # 1. Конвейер рельефа
        params = default_params(crs_wkt, resolution)
        request = ReliefRequest(
            params=params, project_id=f"bench_{tri.name}", resolution=resolution,
            season="summer",
            tiles=[TileInput(name=tri.name, vls_path=abs_las, afs_path=tri.ofp)],
        )
        svc = ReliefService(root_dir=str(tile_dir / "service"))
        t0 = time.perf_counter()
        result = svc.run(request)
        prep["service_wall_ms"] = (time.perf_counter() - t0) * 1000.0

        tile = result.job.tiles[0]
        rec["status"] = tile.status
        rec["reason"] = tile.reason
        rec["tile_duration_ms"] = tile.duration_ms
        rec["steps"] = {s.name: {"status": s.status, "ms": s.duration_ms, "message": s.message}
                        for s in tile.steps}

        # 2. Артефакты: путь, размер, время породившего шага
        step_ms = {s.name: s.duration_ms for s in tile.steps}
        arts = []
        for a in tile.output_files:
            arts.append({
                "layer": a.layer, "kind": a.kind, "path": a.path,
                "size_bytes": a.size_bytes, "file": os.path.basename(a.path),
                "step": LAYER_STEP.get(a.layer),
                "step_ms": step_ms.get(LAYER_STEP.get(a.layer, ""), None),
            })
        rec["artifacts"] = arts
        art_map = {a.layer: a.path for a in tile.output_files}

        # 2b. Горизонтали: шаг `contours` строит 4 сечения за один замер, поэтому
        # каждое сечение дополнительно замеряется отдельно (вне общего таймлайна).
        base = art_map.get("dtm_smooth") or art_map.get("dtm")
        if base and params.vectors.horizontals:
            det_dir = tile_dir / "contours_detail"
            det_dir.mkdir(exist_ok=True)
            detail = {}
            for interval in params.vectors.horizontals:
                t1 = time.perf_counter()
                paths = S.step_contours(base, [interval], str(det_dir), crs_wkt)
                detail[str(interval)] = {
                    "ms": (time.perf_counter() - t1) * 1000.0,
                    "size_bytes": os.path.getsize(paths[0]) if os.path.exists(paths[0]) else None,
                }
            rec["contours_detail"] = detail

        # 3. Точность относительно эталонной ЦМР
        acc: dict = {}
        with timed(prep, "metrics_ms"):
            for layer in ("dtm", "dtm_smooth", "dsm"):
                if layer in art_map and os.path.exists(art_map[layer]):
                    acc[layer] = accuracy_metrics(art_map[layer], tri.ref)
                    acc[layer].update(raster_stats(art_map[layer]))
            # ЦММ − ЦМР: высота объектов над землёй (у ЦММ нет эталона)
            if "dsm" in art_map and "dtm" in art_map:
                dsm_a = align_to_reference(art_map["dsm"], tri.ref)[0]
                dtm_a = align_to_reference(art_map["dtm"], tri.ref)[0]
                d = dsm_a - dtm_a
                m = np.isfinite(d)
                acc["dsm_minus_dtm"] = {
                    "mean": float(np.mean(d[m])) if m.any() else float("nan"),
                    "p95": float(np.percentile(d[m], 95)) if m.any() else float("nan"),
                    "max": float(np.max(d[m])) if m.any() else float("nan"),
                }
        rec["accuracy"] = acc
        rec["prep"] = prep

    except Exception as e:  # noqa: BLE001 — один упавший тайл не роняет прогон
        rec["status"] = "failed"
        rec["reason"] = f"{type(e).__name__}: {e}"
        rec["traceback"] = traceback.format_exc()
        rec["prep"] = prep
    finally:
        if not keep_outputs:
            shutil.rmtree(tile_dir, ignore_errors=True)
    return rec


def run_benchmark(
    root: str,
    out_dir: str,
    limit: Optional[int] = None,
    offset: int = 0,
    resolution: float = 1.0,
    keep_outputs: bool = False,
    results_path: Optional[str] = None,
    verbose: bool = True,
) -> list[dict]:
    """Прогнать бенчмарк по триплетам; результаты пишутся построчно в JSONL."""
    triplets = find_triplets(root)[offset: (offset + limit) if limit else None]
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    results_path = results_path or str(out_root / "results.jsonl")
    work_root = str(out_root / "_work")

    records: list[dict] = []
    with open(results_path, "w", encoding="utf-8") as fh:
        for i, tri in enumerate(triplets, 1):
            t0 = time.perf_counter()
            rec = run_triplet(tri, work_root, resolution, keep_outputs)
            rec["index"] = offset + i
            rec["total_wall_ms"] = (time.perf_counter() - t0) * 1000.0
            records.append(rec)
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            fh.flush()
            if verbose:
                acc = rec.get("accuracy", {}).get("dtm", {})
                print(f"[{i}/{len(triplets)}] {tri.name:22s} {rec['status']:7s} "
                      f"{rec['total_wall_ms']/1000:7.1f}s  "
                      f"RMSE={acc.get('rmse', float('nan')):.3f} м  "
                      f"cov={acc.get('coverage_pct', float('nan')):.1f}%"
                      + (f"  {rec['reason']}" if rec["status"] == "failed" else ""),
                      flush=True)
    if not keep_outputs:
        shutil.rmtree(work_root, ignore_errors=True)
    return records


def load_results(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="/Users/sergeyzay/Documents/НЕДРА/СИМА/test_data/dsm_dataset")
    ap.add_argument("--out", default=str(BACKEND / "benchmarks" / "results"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--resolution", type=float, default=1.0)
    ap.add_argument("--keep-outputs", action="store_true")
    ap.add_argument("--results", default=None)
    args = ap.parse_args()
    run_benchmark(args.root, args.out, args.limit, args.offset,
                  args.resolution, args.keep_outputs, args.results)


if __name__ == "__main__":
    main()
