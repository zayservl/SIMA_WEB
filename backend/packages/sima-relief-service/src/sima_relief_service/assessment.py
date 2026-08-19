"""Оценка/валидация исходных материалов (АФС=GeoTIFF, ВЛС=LAS).

Чистый Python: laspy/rasterio/pyproj. Без QGIS.
Извлекает: СК, площадь экстента, разрешение (АФС), плотность точек и диапазон
высот ТЛО (ВЛС). Соответствует Q3 «Оценка файлов ВЛС/АФС» и контракту
src/api/types.ts (AfsReport/VlsReport/MaterialAssessment/FailedTile).

Примечание: масштаб ОФП (ofp_scale) и масштаб облака ТЛО (tlo_scale) не
выводятся из файла — это параметры съёмки, задаются пользователем. Поэтому
поля Optional и возвращаются None.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import laspy
import numpy as np
import rasterio
from pyproj import CRS, Geod

from .status import FailedTile


@dataclass
class AfsReport:
    crs: str
    extent_area_km2: float
    resolution_m: float
    ofp_scale: Optional[str]
    tiles_total: int
    tiles_ok: int
    tiles_failed: int
    failed_tiles: list[FailedTile] = field(default_factory=list)


@dataclass
class VlsReport:
    crs: str
    extent_area_km2: float
    density_pts_m2: float
    tlo_scale: Optional[str]
    tlo_height_range_m: tuple
    tiles_total: int
    tiles_ok: int
    tiles_failed: int
    failed_tiles: list[FailedTile] = field(default_factory=list)


@dataclass
class MaterialAssessment:
    afs: Optional[AfsReport] = None
    vls: Optional[VlsReport] = None


@dataclass
class CrsCheck:
    """Результат сверки СК внутри пары АФС+ВЛС.

    Attributes:
        status: 'match' — системы совпадают; 'mismatch' — различаются, тайл
            непригоден; 'unknown' — хотя бы у одного файла СК не объявлена,
            сверить нечем; 'single' — в паре только один материал, сверять не с чем.
        vls_crs: СК облака как строка (WKT или пусто).
        afs_crs: СК снимка как строка (WKT или пусто).
        reason: человекочитаемая причина для 'mismatch' и 'unknown'.
    """

    status: str
    vls_crs: str = ""
    afs_crs: str = ""
    reason: Optional[str] = None

    @property
    def blocking(self) -> bool:
        """Расхождение СК — единственный статус, при котором тайл не берётся в работу."""
        return self.status == "mismatch"


def _crs_label(crs_text: str) -> str:
    """Короткое имя СК для сообщений: EPSG-код, иначе имя, иначе «не объявлена»."""
    if not crs_text:
        return "не объявлена"
    try:
        crs = CRS.from_user_input(crs_text)
    except Exception:  # noqa: BLE001
        return crs_text[:60]
    code = crs.to_epsg()
    return f"EPSG:{code}" if code else (crs.name or crs_text[:60])


def crs_equivalent(a: str, b: str) -> bool:
    """Совпадают ли две СК по существу.

    Строковое сравнение непригодно: одна и та же система приходит из GeoTIFF и
    из LAS разными WKT (разный порядок ключей, разные версии стандарта, EPSG-код
    против полного описания). Сравнение ведёт pyproj по семантике; при неразборном
    WKT — откат на сравнение нормализованных строк.
    """
    if not a or not b:
        return False
    try:
        return CRS.from_user_input(a) == CRS.from_user_input(b)
    except Exception:  # noqa: BLE001
        return " ".join(a.split()) == " ".join(b.split())


def check_pair_crs(vls_path: Optional[str], afs_path: Optional[str]) -> CrsCheck:
    """Сверить СК облака и снимка одной пары тайлов.

    Приведения координат в конвейере нет (см. README, раздел «Координаты»),
    поэтому пара с разными СК даст молча смещённый результат — такие тайлы
    отбраковываются до расчёта.
    """
    if not vls_path or not afs_path:
        return CrsCheck(status="single")

    vls_crs = afs_crs = ""
    problems: list[str] = []
    try:
        with rasterio.open(afs_path) as src:
            afs_crs = src.crs.to_wkt() if src.crs is not None else ""
    except Exception as e:  # noqa: BLE001
        problems.append(f"АФС не читается: {e}")
    try:
        crs_obj = laspy.read(vls_path).header.parse_crs()
        vls_crs = crs_obj.to_wkt() if crs_obj is not None else ""
    except Exception as e:  # noqa: BLE001
        problems.append(f"ВЛС не читается: {e}")

    if problems:
        return CrsCheck("unknown", vls_crs, afs_crs, "; ".join(problems))
    if not vls_crs or not afs_crs:
        missing = "ВЛС" if not vls_crs else "АФС"
        return CrsCheck("unknown", vls_crs, afs_crs,
                        f"СК не объявлена в {missing}; сверка невозможна")
    if crs_equivalent(vls_crs, afs_crs):
        return CrsCheck("match", vls_crs, afs_crs)
    return CrsCheck(
        "mismatch", vls_crs, afs_crs,
        f"СК не совпадают: ВЛС {_crs_label(vls_crs)}, АФС {_crs_label(afs_crs)}; "
        "приведение координат не выполняется",
    )


def _geod_area_km2(crs: CRS, xmin: float, ymin: float, xmax: float, ymax: float) -> float:
    """Площадь bbox в кв.км с учётом CRS."""
    try:
        if crs is not None and crs.is_geographic:
            geod = Geod(ellps="WGS84")
            ring = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
            area, _ = geod.polygon_area_perimeter(
                [p[0] for p in ring], [p[1] for p in ring]
            )
            return abs(area) / 1e6
    except Exception:  # noqa: BLE001
        pass
    # projected или CRS неизвестна → координаты в метрах, простое произведение сторон
    return abs((xmax - xmin) * (ymax - ymin)) / 1e6


def assess_tiff(path: str) -> AfsReport:
    """Оценка одного АФС-тайла (GeoTIFF): СК, площадь, разрешение."""
    with rasterio.open(path) as src:
        crs = src.crs.to_wkt() if src.crs is not None else ""
        t = src.transform
        xres = abs(t.a)
        yres = abs(t.e)
        resolution_m = float((xres + yres) / 2.0) if (xres and yres) else float(xres)
        xmin, ymin, xmax, ymax = src.bounds
        area = _geod_area_km2(src.crs, xmin, ymin, xmax, ymax)
    return AfsReport(
        crs=crs,
        extent_area_km2=area,
        resolution_m=resolution_m,
        ofp_scale=None,
        tiles_total=1, tiles_ok=1, tiles_failed=0, failed_tiles=[],
    )


def _las_crs(las: laspy.LasData) -> str:
    try:
        crs = las.header.parse_crs()  # pyproj.CRS | None
    except Exception:  # noqa: BLE001
        crs = None
    if crs is None:
        return ""
    try:
        return crs.to_wkt()
    except Exception:  # noqa: BLE001
        return str(crs)


def assess_las(path: str) -> VlsReport:
    """Оценка одного ВЛС-тайла (LAS): СК, площадь, плотность, диапазон высот ТЛО."""
    las = laspy.read(path)
    crs_obj = None
    try:
        crs_obj = las.header.parse_crs()
    except Exception:  # noqa: BLE001
        crs_obj = None
    crs = crs_obj.to_wkt() if crs_obj is not None else ""
    x = np.asarray(las.x)
    y = np.asarray(las.y)
    z = np.asarray(las.z)
    n = int(len(x))
    if n == 0:
        return VlsReport(crs=crs, extent_area_km2=0.0, density_pts_m2=0.0,
                         tlo_scale=None, tlo_height_range_m=(0.0, 0.0),
                         tiles_total=1, tiles_ok=1, tiles_failed=0, failed_tiles=[])
    xmin, xmax = float(np.min(x)), float(np.max(x))
    ymin, ymax = float(np.min(y)), float(np.max(y))
    area_km2 = _geod_area_km2(crs_obj, xmin, ymin, xmax, ymax)
    area_m2 = area_km2 * 1e6
    density = float(n / area_m2) if area_m2 > 0 else 0.0
    zmin, zmax = float(np.min(z)), float(np.max(z))
    return VlsReport(
        crs=crs, extent_area_km2=area_km2, density_pts_m2=density,
        tlo_scale=None, tlo_height_range_m=(zmin, zmax),
        tiles_total=1, tiles_ok=1, tiles_failed=0, failed_tiles=[],
    )


def _collect_files(directory: str, exts: list[str]) -> list[str]:
    d = Path(directory)
    out = []
    for ext in exts:
        out.extend(sorted(str(p) for p in d.glob(f"*{ext}")))
        out.extend(sorted(str(p) for p in d.glob(f"*{ext.upper()}")))
    return out


def assess_materials(
    vls_dir: Optional[str] = None,
    afs_dir: Optional[str] = None,
    vls_files: Optional[list[str]] = None,
    afs_files: Optional[list[str]] = None,
) -> MaterialAssessment:
    """Оценка каталогов/файлов ВЛС и АФС. Агрегирует тайлы, собирает failed_tiles."""
    afs_report = None
    vls_report = None

    # --- АФС (GeoTIFF) ---
    afs_paths = list(afs_files) if afs_files else (
        _collect_files(afs_dir, [".tif", ".tiff"]) if afs_dir else []
    )
    if afs_paths:
        ok_total = failed_total = 0
        first: Optional[AfsReport] = None
        failed: list[FailedTile] = []
        for p in afs_paths:
            try:
                rep = assess_tiff(p)
                ok_total += 1
                if first is None:
                    first = rep
            except Exception as e:  # noqa: BLE001
                failed_total += 1
                failed.append(FailedTile(os.path.basename(p), str(e)))
        if first is not None:
            afs_report = AfsReport(
                crs=first.crs, extent_area_km2=first.extent_area_km2,
                resolution_m=first.resolution_m, ofp_scale=None,
                tiles_total=len(afs_paths), tiles_ok=ok_total,
                tiles_failed=failed_total, failed_tiles=failed,
            )

    # --- ВЛС (LAS) ---
    vls_paths = list(vls_files) if vls_files else (
        _collect_files(vls_dir, [".las", ".laz"]) if vls_dir else []
    )
    if vls_paths:
        ok_total = failed_total = 0
        first: Optional[VlsReport] = None
        failed: list[FailedTile] = []
        for p in vls_paths:
            try:
                rep = assess_las(p)
                ok_total += 1
                if first is None:
                    first = rep
            except Exception as e:  # noqa: BLE001
                failed_total += 1
                failed.append(FailedTile(os.path.basename(p), str(e)))
        if first is not None:
            vls_report = VlsReport(
                crs=first.crs, extent_area_km2=first.extent_area_km2,
                density_pts_m2=first.density_pts_m2, tlo_scale=None,
                tlo_height_range_m=first.tlo_height_range_m,
                tiles_total=len(vls_paths), tiles_ok=ok_total,
                tiles_failed=failed_total, failed_tiles=failed,
            )

    return MaterialAssessment(afs=afs_report, vls=vls_report)