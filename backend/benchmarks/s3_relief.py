"""Прогон конвейера рельефа по материалам из S3 — общая часть демо-ноутбуков.

Ноутбуки `relief_s3_*.ipynb` различаются только описанием датасета: префиксами в
бакете, правилом сопоставления АФС с ВЛС и источником системы координат. Всё
остальное — доступ к бакету, загрузка ВЛС, оценка материалов, вызов
`ReliefService`, замеры времени, превью тайла — общее и живёт здесь, чтобы
ноутбук показывал результат, а не реализацию.

Один тайл (`Runner.process`):
    ВЛС из S3 → заголовок АФС по сети (`/vsis3`) → оценка материалов →
    (опц.) ТЛО → абсолютные Z по эталонной ЦМР → ReliefService.run() → превью.

Записи пишутся в JSONL построчно: прерванный прогон продолжается с места
остановки (`resume=True`), упавший тайл не роняет прогон.

CLI — прогрев результатов до открытия ноутбука:

    python benchmarks/s3_relief.py --dataset yuilskiy --limit 100 --restore-z
    python benchmarks/s3_relief.py --dataset yuzhno_zimniy --limit 30
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import traceback
import unicodedata
import warnings
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND / "benchmarks") not in sys.path:
    sys.path.insert(0, str(BACKEND / "benchmarks"))

warnings.filterwarnings("ignore")

import boto3  # noqa: E402
import laspy  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

import relief_bench as RB  # noqa: E402
from sima_relief_service import (  # noqa: E402
    ReliefRequest,
    ReliefService,
    TileInput,
    assess_materials,
)

nfd = lambda s: unicodedata.normalize("NFD", s)  # ключи бакета — в форме NFD  # noqa: E731

S3_ENDPOINT = "https://storage.yandexcloud.net"
S3_REGION = "ru-central1"
BUCKET = "geomate-project"


# --- 1. Датасеты ---------------------------------------------------------

@dataclass(frozen=True)
class Dataset:
    """Описание датасета в бакете: где лежит, как сопоставляются пары, какая СК."""

    key: str                      # короткое имя для CLI
    title: str                    # для заголовков
    las_prefix: str               # префикс ВЛС
    afs_prefixes: tuple[str, ...]  # префиксы АФС (у Ю-Зимнего их четыре — по этапам)
    ref_prefix: Optional[str] = None   # эталонные ЦМР (нужны только для restore_z)
    las_suffix: str = ""          # отбрасывается из стема ВЛС при сопоставлении
    pair_by: str = "stem"         # 'stem' — по имени листа, 'block' — по номеру блока
    target_crs: Optional[str] = None   # None — брать СК из заголовка АФС
    results_dirname: str = ""

    @property
    def results_dir(self) -> Path:
        return BACKEND / "benchmarks" / (self.results_dirname or f"results_s3_{self.key}")


_YU = nfd("СИМА/Datasets/Юильский/")
_ZIM = nfd("СИМА/Datasets/2022_Ю-Зимний 3Д/")

DATASETS: dict[str, Dataset] = {
    "yuilskiy": Dataset(
        key="yuilskiy",
        title="Юильский",
        las_prefix=_YU + "LAS/",
        afs_prefixes=(_YU + "ОФП/MSK86z2/",),
        ref_prefix=_YU + "DSM/MSK86z2/",
        las_suffix="_ground_TLO",
        pair_by="stem",
        target_crs=None,             # СК берётся из заголовка АФС (MSK86z2)
        results_dirname="results_s3_yuilskiy",
    ),
    "yuzhno_zimniy": Dataset(
        key="yuzhno_zimniy",
        title="Южно-Зимний 2022",
        las_prefix=_ZIM + "LAS-Uzno-Zimniy/",
        afs_prefixes=tuple(_ZIM + p for p in (
            "1-этап/ORTO_TIFF_1-216/",
            "2-этап/ORTO_TIFF_217-500/",
            "3-этап/ORTO_TIFF_501-764/",
            "4-этап/ORTO_TIFF_765-984/",
        )),
        pair_by="block",
        # У АФС в заголовке LOCAL_CS — проекции нет. ГСК-2011, зона 12 без номера
        # зоны в X (Уватский район, 68.5°E): EPSG:21012, а не EPSG:20912.
        target_crs="EPSG:21012",
        results_dirname="results_s3_yuzhno_zimniy",
    ),
}


# --- 2. Доступ к бакету --------------------------------------------------

def credentials() -> tuple[str, str]:
    """Ключи S3 из окружения, иначе из `backend/.s3_credentials.json` (в .gitignore)."""
    ak = os.environ.get("S3_ACCESS_KEY", "")
    sk = os.environ.get("S3_SECRET_KEY", "")
    if not (ak and sk):
        cred = BACKEND / ".s3_credentials.json"
        if cred.exists():
            c = json.loads(cred.read_text(encoding="utf-8"))
            ak, sk = c["access_key"], c["secret_key"]
    if not (ak and sk):
        raise RuntimeError(
            "Нет ключей S3: задайте S3_ACCESS_KEY/S3_SECRET_KEY или создайте "
            "backend/.s3_credentials.json вида {\"access_key\": \"...\", \"secret_key\": \"...\"}")
    return ak, sk


def connect() -> "boto3.client":
    """Клиент boto3 и окружение GDAL для чтения АФС по сети через /vsis3."""
    ak, sk = credentials()
    os.environ.update(
        AWS_ACCESS_KEY_ID=ak,
        AWS_SECRET_ACCESS_KEY=sk,
        AWS_S3_ENDPOINT=S3_ENDPOINT.split("://")[-1],
        AWS_VIRTUAL_HOSTING="FALSE",
        AWS_DEFAULT_REGION=S3_REGION,
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",  # для превью временно снимается
        # Чтение АФС идёт по сети: без границ одна залипшая выдача бакета вешает
        # прогон целиком (наблюдалось на отрисовке превью — 15 мин в одном read).
        GDAL_HTTP_TIMEOUT="60",
        GDAL_HTTP_CONNECTTIMEOUT="15",
        GDAL_HTTP_MAX_RETRY="3",
        GDAL_HTTP_RETRY_DELAY="2",
    )
    os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")  # GDAL/PDAL
    return boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name=S3_REGION,
                        aws_access_key_id=ak, aws_secret_access_key=sk)


def vsis3(key: str) -> str:
    return f"/vsis3/{BUCKET}/{key}"


def _block_no(key: str) -> Optional[int]:
    """Номер блока из имени: 'pt000012.las' → 12, '00000012.tif' → 12."""
    digits = re.sub(r"\D", "", PurePosixPath(key).stem)
    return int(digits) if digits else None


# --- 3. Каталог бакета ---------------------------------------------------

@dataclass
class Catalog:
    """Индексы АФС/ВЛС/эталонов и список сопоставленных пар."""

    afs: dict = field(default_factory=dict)   # id → (key, size)
    las: dict = field(default_factory=dict)
    ref: dict = field(default_factory=dict)
    pairs: list = field(default_factory=list)  # отсортированные id полных пар
    names: dict = field(default_factory=dict)  # id → имя тайла
    listing_s: float = 0.0

    def size_gb(self, ids: Iterable) -> float:
        return sum(self.las[i][1] for i in ids) / 1e9


class Runner:
    """Прогон датасета: каталог бакета, обработка тайлов, JSONL и превью."""

    def __init__(
        self,
        dataset: Dataset | str,
        resolution: float = 1.0,
        fill_method: str = RB.DEFAULT_FILL_METHOD,
        restore_z: bool = False,
        keep_outputs: bool = False,
        cache_las: bool = False,
        preview_every: int = 10,
        results_dir: Optional[Path] = None,
    ) -> None:
        self.ds = DATASETS[dataset] if isinstance(dataset, str) else dataset
        self.resolution = resolution
        self.fill_method = fill_method     # чем заполнять пустоты: laplace | idw
        self.restore_z = restore_z
        self.keep_outputs = keep_outputs
        self.cache_las = cache_las
        self.preview_every = preview_every

        self.results_dir = Path(results_dir or self.ds.results_dir)
        self.results_path = self.results_dir / "results.jsonl"
        self.preview_dir = self.results_dir / "previews"
        self.work_root = self.results_dir / "_work"
        self.cache_dir = self.results_dir / "_las_cache"
        for d in (self.results_dir, self.preview_dir, self.work_root, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.s3 = connect()
        self.cat = Catalog()

    # --- каталог ---------------------------------------------------------

    def _index(self, prefixes, ext: str, strip_suffix: str = "") -> dict:
        out: dict = {}
        for prefix in ([prefixes] if isinstance(prefixes, str) else prefixes):
            for page in self.s3.get_paginator("list_objects_v2").paginate(
                    Bucket=BUCKET, Prefix=prefix):
                for o in page.get("Contents", []):
                    if not o["Key"].lower().endswith(ext):
                        continue
                    if self.ds.pair_by == "block":
                        key_id = _block_no(o["Key"])
                    else:
                        stem = PurePosixPath(o["Key"]).stem
                        key_id = (stem[: -len(strip_suffix)]
                                  if strip_suffix and stem.endswith(strip_suffix) else stem)
                    if key_id is not None:
                        out.setdefault(key_id, (o["Key"], o["Size"]))  # детерминированно
        return out

    def catalog(self) -> Catalog:
        """Проиндексировать бакет и сопоставить пары АФС+ВЛС."""
        t0 = time.perf_counter()
        c = Catalog()
        c.afs = self._index(self.ds.afs_prefixes, ".tif")
        c.las = self._index(self.ds.las_prefix, ".las", self.ds.las_suffix)
        if self.ds.ref_prefix:
            c.ref = self._index(self.ds.ref_prefix, ".tif")
        c.pairs = sorted(set(c.afs) & set(c.las))
        if self.restore_z:
            c.pairs = [i for i in c.pairs if i in c.ref]
        c.names = {i: PurePosixPath(c.las[i][0]).stem for i in c.pairs}
        if self.ds.las_suffix:
            c.names = {i: n[: -len(self.ds.las_suffix)] if n.endswith(self.ds.las_suffix) else n
                       for i, n in c.names.items()}
        c.listing_s = time.perf_counter() - t0
        self.cat = c
        return c

    def select(self, limit: Optional[int] = None, offset: int = 0) -> list:
        pairs = self.cat.pairs or self.catalog().pairs
        return pairs[offset: (offset + limit) if limit else None]

    # --- один тайл -------------------------------------------------------

    def process(self, tile_id) -> dict:
        """Полный прогон одной пары АФС+ВЛС; возвращает запись для JSONL."""
        c = self.cat
        las_key, las_size = c.las[tile_id]
        afs_key, afs_size = c.afs[tile_id]
        name = c.names[tile_id]
        rec: dict = {"name": name, "status": "failed", "reason": None,
                     "las_key": las_key, "afs_key": afs_key,
                     "las_size_mb": las_size / 1e6, "afs_size_mb": afs_size / 1e6}
        if self.ds.pair_by == "block":
            rec["block"] = tile_id
        prep: dict = {}
        tile_dir = self.work_root / str(name)
        tile_dir.mkdir(parents=True, exist_ok=True)
        local_las = self.cache_dir / PurePosixPath(las_key).name
        rec["tile_dir"] = str(tile_dir)
        rec["local_las"] = str(local_las)

        try:
            # 1. ВЛС: скачивание (или готовый файл в кэше)
            if local_las.exists() and local_las.stat().st_size == las_size:
                prep["download_ms"] = 0.0
                rec["las_cached"] = True
            else:
                with RB.timed(prep, "download_ms"):
                    self.s3.download_file(BUCKET, las_key, str(local_las))
                rec["las_cached"] = False

            # 2. АФС: только заголовок, по сети
            with RB.timed(prep, "afs_header_ms"):
                with rasterio.open(vsis3(afs_key)) as src:
                    afs_crs = src.crs
                    b = src.bounds
                    rec["afs_shape"] = list(src.shape)
                    rec["afs_res_m"] = float(abs(src.transform.a))
                    rec["afs_area_km2"] = abs(b.right - b.left) * abs(b.top - b.bottom) / 1e6

            # 3. СК: из заголовка АФС, иначе заданная датасетом
            if self.ds.target_crs is None:
                crs_wkt = afs_crs.to_wkt()
                rec["crs_source"] = "afs"
            else:
                from pyproj import CRS as PyCRS
                crs_wkt = PyCRS.from_user_input(self.ds.target_crs).to_wkt()
                rec["crs_source"] = self.ds.target_crs

            # 4. Оценка материалов (Q3 «Оценка файлов ВЛС/АФС»)
            with RB.timed(prep, "assess_ms"):
                assessment = assess_materials(vls_files=[str(local_las)],
                                              afs_files=[vsis3(afs_key)])
            if assessment.vls:
                rec["las_points_density"] = assessment.vls.density_pts_m2
                rec["z_range_m"] = list(assessment.vls.tlo_height_range_m)
                rec["las_area_km2"] = assessment.vls.extent_area_km2

            # 5. ТЛО → абсолютные Z по эталонной ЦМР (вне сервиса, опционально)
            src_las = str(local_las)
            if self.restore_z:
                abs_las = str(tile_dir / f"{name}_abs.las")
                with RB.timed(prep, "restore_ms"):
                    RB.restore_absolute(str(local_las), vsis3(c.ref[tile_id][0]), abs_las)
                src_las = abs_las
            with laspy.open(src_las) as f:
                rec["n_points"] = int(f.header.point_count)

            # 6. Конвейер рельефа
            params = RB.default_params(crs_wkt, self.resolution, self.fill_method)
            request = ReliefRequest(
                params=params, project_id=f"s3_{name}", resolution=self.resolution,
                season="summer",
                tiles=[TileInput(name=name, vls_path=src_las, afs_path=vsis3(afs_key))],
            )
            svc = ReliefService(root_dir=str(tile_dir / "service"))
            t0 = time.perf_counter()
            result = svc.run(request)
            prep["service_wall_ms"] = (time.perf_counter() - t0) * 1000.0

            tile = result.job.tiles[0]
            rec["status"] = tile.status
            rec["reason"] = tile.reason
            rec["tile_duration_ms"] = tile.duration_ms
            rec["steps"] = {s.name: {"status": s.status, "ms": s.duration_ms,
                                     "message": s.message} for s in tile.steps}

            step_ms = {s.name: s.duration_ms for s in tile.steps}
            rec["artifacts"] = [{
                "layer": a.layer, "kind": a.kind, "path": a.path,
                "file": os.path.basename(a.path), "size_bytes": a.size_bytes,
                "step": RB.LAYER_STEP.get(a.layer),
                "step_ms": step_ms.get(RB.LAYER_STEP.get(a.layer, "")),
            } for a in tile.output_files]

            art = {a.layer: a.path for a in tile.output_files}
            rec["stats"] = {k: RB.raster_stats(art[k]) for k in ("dtm", "dtm_smooth", "dsm")
                            if k in art and os.path.exists(art[k])}

        except Exception as e:  # noqa: BLE001 — один упавший тайл не роняет прогон
            rec["status"] = "failed"
            rec["reason"] = f"{type(e).__name__}: {e}"
            rec["traceback"] = traceback.format_exc()

        rec["prep"] = prep
        return rec

    def cleanup(self, rec: dict) -> None:
        if not self.keep_outputs:
            shutil.rmtree(rec["tile_dir"], ignore_errors=True)
        if not self.cache_las:
            Path(rec["local_las"]).unlink(missing_ok=True)

    # --- прогон ----------------------------------------------------------

    def load_results(self, names: Optional[set] = None) -> list[dict]:
        if not self.results_path.exists():
            return []
        with open(self.results_path, encoding="utf-8") as fh:
            recs = [json.loads(line) for line in fh if line.strip()]
        return [r for r in recs if names is None or r["name"] in names] if recs else []

    def run(
        self,
        ids: list,
        resume: bool = True,
        verbose: bool = True,
        on_preview: Optional[Callable[[dict], None]] = None,
    ) -> list[dict]:
        """Обработать выбранные тайлы, дописывая JSONL и сохраняя превью."""
        done = {r["name"] for r in self.load_results()} if resume else set()
        queue = [i for i in ids if self.cat.names[i] not in done]
        if verbose:
            print(f"к обработке: {len(queue)} из {len(ids)} "
                  f"(уже в JSONL: {len(ids) - len(queue)})", flush=True)

        with open(self.results_path, "a" if resume else "w", encoding="utf-8") as fh:
            for n, tile_id in enumerate(queue, 1):
                t0 = time.perf_counter()
                rec = self.process(tile_id)
                rec["index"] = ids.index(tile_id) + 1
                rec["total_wall_ms"] = (time.perf_counter() - t0) * 1000.0
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                fh.flush()
                if verbose:
                    print(f"[{n}/{len(queue)}] {str(rec['name']):22s} {rec['status']:7s} "
                          f"всего {rec['total_wall_ms'] / 1000:6.1f} с  "
                          f"(сеть {rec['prep'].get('download_ms', 0) / 1000:4.1f} + "
                          f"конвейер {rec.get('tile_duration_ms', 0) / 1000:5.1f})  "
                          f"{rec.get('n_points', 0):>9,} точек"
                          + (f"  ✗ {rec['reason']}" if rec["status"] != "done" else ""),
                          flush=True)
                if (rec["status"] == "done" and self.preview_every
                        and rec["index"] % self.preview_every == 0):
                    try:
                        save_preview(rec, self.preview_dir)
                        if on_preview:
                            on_preview(rec)
                    except Exception as e:  # noqa: BLE001 — превью не должно ронять прогон
                        print(f"  превью не построено: {type(e).__name__}: {e}", flush=True)
                self.cleanup(rec)

        names = {self.cat.names[i] for i in ids}
        return self.load_results(names)


# --- 4. Превью тайла -----------------------------------------------------

def read_raster(path: str):
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        return arr, src.bounds, src.crs


def afs_window(afs_key: str, bounds, max_px: int = 900):
    """Фрагмент АФС по экстенту ЦМР, прореженный до max_px по длинной стороне.

    GDAL_DISABLE_READDIR_ON_OPEN снимается: без этого не подхватываются
    сайдкар-пирамиды .tif.ovr и декимированное чтение 168-МБ ОФП идёт ~12 с
    вместо ~1.5 с.
    """
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="NO"):
        with rasterio.open(vsis3(afs_key)) as src:
            win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            h, w = int(win.height), int(win.width)
            if h <= 0 or w <= 0:
                return None
            k = max(1.0, max(h, w) / max_px)
            bands = [1, 2, 3] if src.count >= 3 else [1]
            arr = src.read(bands, window=win, boundless=True, fill_value=255,
                           out_shape=(len(bands), max(1, int(h / k)), max(1, int(w / k))))
    return np.transpose(arr, (1, 2, 0)) if arr.shape[0] == 3 else arr[0]


def tile_panels(rec: dict) -> list[dict]:
    """Панели превью тайла: АФС и растры расчёта в порядке показа."""
    art = {a["layer"]: a["path"] for a in rec.get("artifacts", [])
           if os.path.exists(a["path"])}
    if "dtm" not in art:
        return []
    dtm, bounds, _ = read_raster(art["dtm"])

    panels: list[dict] = []
    afs = afs_window(rec["afs_key"], bounds)
    if afs is not None:
        panels.append({"title": "АФС (фрагмент по экстенту ЦМР)", "arr": afs, "kind": "rgb"})

    panels.append({"title": "ЦМР (DTM, IDW)", "arr": dtm, "cmap": "terrain", "kind": "z"})
    for key, title in (("dtm_smooth", "ЦМР сглаженная (σ=2)"), ("dsm", "ЦММ (DSM, max)")):
        if key in art:
            panels.append({"title": title, "arr": read_raster(art[key])[0],
                           "cmap": "terrain", "kind": "z"})
    if "dsm" in art:
        d = read_raster(art["dsm"])[0]
        h, w = min(d.shape[0], dtm.shape[0]), min(d.shape[1], dtm.shape[1])
        panels.append({"title": "ЦММ − ЦМР (высота объектов)",
                       "arr": d[:h, :w] - dtm[:h, :w], "cmap": "YlGn", "kind": "own"})
    for key, title, cmap in (("slope", "Уклон, град", "magma"),
                             ("aspect", "Экспозиция, град", "twilight"),
                             ("tpi", "TPI (формы рельефа)", "RdBu_r")):
        if key in art:
            panels.append({"title": title, "arr": read_raster(art[key])[0],
                           "cmap": cmap, "kind": "own"})
    return panels


def tile_figure(panels: list[dict], suptitle: str = ""):
    """Сетка панелей под форму тайла; ЦМР/сглаженная/ЦММ — в общей шкале высот."""
    import matplotlib.pyplot as plt

    zs = [p["arr"] for p in panels if p.get("kind") == "z" and np.isfinite(p["arr"]).any()]
    zmin = min(float(np.nanmin(a)) for a in zs) if zs else 0.0
    zmax = max(float(np.nanmax(a)) for a in zs) if zs else 1.0

    ref = next(p["arr"] for p in panels if p.get("kind") != "rgb")
    aspect = ref.shape[1] / max(ref.shape[0], 1)
    n = len(panels)
    # Вытянутые тайлы кладём в один-два столбца, близкие к квадрату — в три.
    ncols = 1 if aspect > 3 else (3 if aspect < 0.8 else 2)
    nrows = int(np.ceil(n / ncols))
    panel_w = 7.5 if ncols == 1 else 5.6
    panel_h = float(np.clip(panel_w / aspect, 2.2, 7.0))

    fig, axes = plt.subplots(nrows, ncols, figsize=(panel_w * ncols, panel_h * nrows))
    axes = np.atleast_1d(axes).ravel()
    for ax, p in zip(axes, panels):
        arr, kind = p["arr"], p.get("kind", "own")
        if kind == "rgb":
            ax.imshow(arr, cmap=None if arr.ndim == 3 else "gray")
            ax.set_title(p["title"], fontsize=11)
        elif not np.isfinite(arr).any():
            ax.imshow(np.zeros(arr.shape[:2]), cmap="gray", vmin=0, vmax=1)
            ax.text(.5, .5, "слой пуст (nodata)", ha="center", va="center",
                    transform=ax.transAxes, fontsize=11, color="crimson")
            ax.set_title(p["title"], fontsize=11)
        else:
            kw = dict(vmin=zmin, vmax=zmax) if kind == "z" else {}
            im = ax.imshow(arr, cmap=p.get("cmap", "viridis"), **kw)
            fig.colorbar(im, ax=ax, shrink=.75)
            ax.set_title(f"{p['title']}\n{np.nanmin(arr):.2f} … {np.nanmax(arr):.2f}",
                         fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
    for ax in axes[len(panels):]:
        ax.set_visible(False)
    if suptitle:
        fig.suptitle(suptitle, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.55 / fig.get_figheight()))
    return fig


def save_preview(rec: dict, preview_dir: Path, dpi: int = 100) -> Optional[Path]:
    """Собрать и сохранить превью тайла; в ноутбук оно попадает через галерею."""
    import matplotlib.pyplot as plt

    panels = tile_panels(rec)
    if not panels:
        return None
    title = (f"{rec['name']}   {rec.get('n_points', 0):,} точек   "
             f"конвейер {rec.get('tile_duration_ms', 0) / 1000:.1f} с   "
             f"всего {rec.get('total_wall_ms', 0) / 1000:.1f} с")
    fig = tile_figure(panels, title)
    path = Path(preview_dir) / f"{rec['name']}.png"
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


def gallery(preview_dir, max_n: int = 10, width: int = 1000,
            names: Optional[list] = None, quality: int = 82) -> int:
    """Показать сохранённые превью в ноутбуке.

    Картинки ужимаются до ширины `width` и встраиваются как JPEG: полноразмерные
    PNG лежат на диске, а вложенные в .ipynb вчетверо-впятеро легче — иначе десяток
    карт с аэрофотоснимками раздувает файл до десятков мегабайт.
    """
    from io import BytesIO

    from IPython.display import Image as IPyImage, display
    from PIL import Image

    paths = sorted(Path(preview_dir).glob("*.png"))
    if names is not None:
        keep = {str(n) for n in names}
        paths = [p for p in paths if p.stem in keep]
    for p in paths[:max_n]:
        img = Image.open(p).convert("RGB")
        if img.width > width:
            img = img.resize((width, round(img.height * width / img.width)))
        buf = BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        print(p.stem)
        display(IPyImage(data=buf.getvalue(), format="jpeg"))
    return len(paths)


# --- 6. Сводная таблица по тайлам ---------------------------------------

def frame(records: list[dict]):
    """DataFrame по успешным тайлам: объём облака, время сети и шагов, статистика растров."""
    import pandas as pd

    rows = []
    for r in records:
        if r["status"] != "done":
            continue
        prep, st = r.get("prep", {}), r.get("stats", {})
        row = {
            "tile": r["name"],
            "points": r.get("n_points"),
            "las_MB": round(r.get("las_size_mb", 0), 1),
            "density_pts_m2": r.get("las_points_density"),
            "las_area_km2": r.get("las_area_km2"),
            "download_s": prep.get("download_ms", 0) / 1000,
            "afs_hdr_s": prep.get("afs_header_ms", 0) / 1000,
            "assess_s": prep.get("assess_ms", 0) / 1000,
            "restore_s": prep.get("restore_ms", 0) / 1000,
            "pipeline_s": (r.get("tile_duration_ms") or 0) / 1000,
            "total_s": r.get("total_wall_ms", 0) / 1000,
            "dtm_z_min": st.get("dtm", {}).get("z_min"),
            "dtm_z_max": st.get("dtm", {}).get("z_max"),
            "dsm_z_max": st.get("dsm", {}).get("z_max"),
            "dtm_valid_%": st.get("dtm", {}).get("valid_pct"),
            "dsm_valid_%": st.get("dsm", {}).get("valid_pct"),
        }
        for s in RB.STEP_ORDER:
            row[f"ms_{s}"] = (r.get("steps", {}).get(s) or {}).get("ms")
        rows.append(row)
    return pd.DataFrame(rows).set_index("tile")


def artifacts_frame(records: list[dict]):
    """Время и объём по выходным слоям: размеры — по файлам, время — по парам (тайл, шаг)."""
    import numpy as np
    import pandas as pd

    arts = pd.DataFrame([
        {"tile": r["name"], "layer": a["layer"], "kind": a["kind"], "file": a["file"],
         "step": a["step"], "ms": a["step_ms"], "size_kb": (a["size_bytes"] or 0) / 1024}
        for r in records if r["status"] == "done" for a in r.get("artifacts", [])])
    if arts.empty:
        return arts
    size_agg = arts.groupby("layer").agg(
        файлов=("file", "count"), формат=("kind", "first"), шаг=("step", "first"),
        медиана_KB=("size_kb", "median"), сумма_MB=("size_kb", lambda s: s.sum() / 1024))
    time_agg = (arts.drop_duplicates(subset=["tile", "step"]).groupby("step")["ms"]
                .agg(медиана_мс="median", p95_мс=lambda s: s.quantile(.95),
                     сумма_с=lambda s: s.sum() / 1000))
    out = size_agg.join(time_agg, on="шаг").sort_values("сумма_MB", ascending=False).round(2)
    out["примечание"] = np.where(
        out.groupby("шаг")["шаг"].transform("size") > 1,
        "время делится с др. слоями того же шага", "")
    return out


# --- 5. CLI --------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="yuilskiy", choices=sorted(DATASETS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--resolution", type=float, default=1.0)
    ap.add_argument("--restore-z", action="store_true",
                    help="восстановить абсолютные Z из ТЛО по эталонной ЦМР бакета")
    ap.add_argument("--preview-every", type=int, default=10)
    ap.add_argument("--fill-method", default=RB.DEFAULT_FILL_METHOD,
                    choices=("laplace", "idw"))
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--cache-las", action="store_true")
    args = ap.parse_args()

    RB.quiet_gdal()
    r = Runner(args.dataset, resolution=args.resolution, fill_method=args.fill_method,
               restore_z=args.restore_z,
               preview_every=args.preview_every, cache_las=args.cache_las,
               results_dir=args.results_dir)
    cat = r.catalog()
    ids = r.select(args.limit, args.offset)
    print(f"{r.ds.title}: АФС {len(cat.afs)}, ВЛС {len(cat.las)}, "
          f"эталонов {len(cat.ref)}, полных пар {len(cat.pairs)}")
    print(f"в прогоне: {len(ids)} тайлов, {cat.size_gb(ids):.2f} ГБ ВЛС, "
          f"restore_z={args.restore_z}")
    recs = r.run(ids, resume=not args.no_resume)
    ok = [x for x in recs if x["status"] == "done"]
    print(f"готово: {len(ok)}/{len(recs)} успешно; JSONL → {r.results_path}")


if __name__ == "__main__":
    main()
