"""TIN-поверхность из точек (ground/высоты) → экспорт в DXF (3DFACE).

Чистый Python: scipy.spatial.Delaunay + минимальный self-contained ASCII
DXF-writer (DXF R12). Без QGIS/ezdxf. Порт логики легаси
relief_analysis/relief.py::tin() (там — QGIS native:tinmeshcreation + экспорт
граней в .dxf через QgsVectorFileWriter); здесь — то же по смыслу, без QGIS.
"""

from __future__ import annotations

import os
from typing import Optional

import laspy
import numpy as np
from scipy.spatial import Delaunay

from sima_dem_core.thinning import thin_by_min_distance


def _write_dxf_3dface(points_xyz: np.ndarray, simplices: np.ndarray, out_path: str) -> None:
    """Записать TIN-треугольники как 3DFACE-сущности DXF R12 (ASCII)."""
    lines: list[str] = []
    lines.append("0")
    lines.append("SECTION")
    lines.append("2")
    lines.append("HEADER")
    lines.append("9")
    lines.append("$ACADVER")
    lines.append("1")
    lines.append("AC1009")
    lines.append("0")
    lines.append("ENDSEC")
    lines.append("0")
    lines.append("SECTION")
    lines.append("2")
    lines.append("ENTITIES")
    for tri in simplices:
        x1, y1, z1 = points_xyz[tri[0]]
        x2, y2, z2 = points_xyz[tri[1]]
        x3, y3, z3 = points_xyz[tri[2]]
        lines += [
            "0", "3DFACE",
            "8", "0",
            "10", f"{x1:.3f}", "20", f"{y1:.3f}", "30", f"{z1:.3f}",
            "11", f"{x2:.3f}", "21", f"{y2:.3f}", "31", f"{z2:.3f}",
            "12", f"{x3:.3f}", "22", f"{y3:.3f}", "32", f"{z3:.3f}",
            "13", f"{x3:.3f}", "23", f"{y3:.3f}", "33", f"{z3:.3f}",
        ]
    lines.append("0")
    lines.append("ENDSEC")
    lines.append("0")
    lines.append("EOF")
    with open(out_path, "w", encoding="ascii") as fh:
        fh.write("\n".join(lines))


def build_tin(points_xyz: np.ndarray, out_path: str, crs_wkt: Optional[str] = None) -> str:
    """Построить TIN (Delaunay по xy) и записать .dxf (3DFACE-треугольники).

    Args:
        points_xyz: массив (N, 3) [x, y, z] float.
        out_path: путь выходного .dxf.
        crs_wkt: зарезервирован (DXF R12 ненадёжно хранит CRS).
    Returns:
        out_path.
    """
    pts = np.asarray(points_xyz, dtype=float)
    if pts.ndim != 2 or pts.shape[1] < 3 or pts.shape[0] < 3:
        raise ValueError(f"TIN требует >=3 точек (N,3), получено {pts.shape}")
    tri = Delaunay(pts[:, :2])
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    _write_dxf_3dface(pts, tri.simplices, out_path)
    return out_path


def build_tin_from_las(
    las_path: str,
    out_path: str,
    min_distance_m: float = 10.0,
    crs_wkt: Optional[str] = None,
) -> str:
    """Ground-точки (Classification==2) из LAS, прорежённые по расстоянию, TIN → .dxf.

    min_distance_m — минимальное расстояние между узлами триангуляции, м
    (тот же параметр, что и у отметок высот). 0 — без прореживания.
    """
    las = laspy.read(las_path)
    cls = np.asarray(las.classification)
    x = np.asarray(las.x)
    y = np.asarray(las.y)
    z = np.asarray(las.z)
    mask = cls == 2
    if not np.any(mask):
        mask = np.ones_like(cls, dtype=bool)  # нет ground — берём все точки
    xs, ys, zs = x[mask], y[mask], z[mask]
    keep = thin_by_min_distance(xs, ys, min_distance_m)
    pts = np.column_stack([xs[keep], ys[keep], zs[keep]])
    return build_tin(pts, out_path, crs_wkt=crs_wkt)