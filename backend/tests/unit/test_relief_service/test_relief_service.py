"""Тесты сервисного слоя рельефа (sima-relief-service).

Покрывают: assessment, contract mapping, storage layout, tin (.dxf), shp (.shp),
шаги (existing_dtm, dem-source heights), сервис end-to-end на синтетике
(упавший тайл → failed+reason, остальные продолжаются; повторный запуск →
новый tile_id).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import laspy
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds


# --- фикстуры синтетических данных --------------------------------------

def _make_ground_las(path: str, n: int = 600) -> str:
    las = laspy.create(point_format=3, file_version="1.2")
    rng = np.random.default_rng(42)
    x = rng.uniform(100.0, 200.0, n)
    y = rng.uniform(100.0, 200.0, n)
    z = 90.0 + 0.01 * (x - 100) + 0.01 * (y - 100)
    las.x = x
    las.y = y
    las.z = z
    las.classification = np.array([2] * n, dtype=np.uint8)
    las.write(path)
    return path


def _make_dtm_tif(path: str, crs="EPSG:32642", size=20) -> str:
    arr = np.linspace(90, 110, size * size, dtype=np.float32).reshape(size, size)
    transform = from_bounds(100, 100, 200, 200, size, size)
    with rasterio.open(path, "w", driver="GTiff", height=size, width=size,
                      count=1, dtype="float32", crs=crs, transform=transform,
                      nodata=-9999) as dst:
        dst.write(arr, 1)
    return path


# --- assessment ---------------------------------------------------------

class TestAssessment:

    def test_assess_las(self, tmp_path):
        from sima_relief_service import assess_las
        p = str(tmp_path / "g.las")
        _make_ground_las(p)
        rep = assess_las(p)
        assert rep.tiles_total == 1 and rep.tiles_ok == 1
        assert rep.density_pts_m2 > 0
        assert rep.tlo_height_range_m[0] <= rep.tlo_height_range_m[1]
        assert rep.tlo_scale is None  # не выводится из файла

    def test_assess_tiff(self, tmp_path):
        from sima_relief_service import assess_tiff
        p = str(tmp_path / "d.tif")
        _make_dtm_tif(p)
        rep = assess_tiff(p)
        assert rep.resolution_m > 0
        assert rep.extent_area_km2 > 0
        assert rep.crs.startswith("EPSG") or "PROJCS" in rep.crs or rep.crs == ""

    def test_assess_materials_failed_tile(self, tmp_path):
        from sima_relief_service import assess_materials
        good = str(tmp_path / "g.las")
        _make_ground_las(good)
        bad = str(tmp_path / "bad.las")  # не существует → failed
        rep = assess_materials(vls_files=[good, bad])
        assert rep.vls is not None
        assert rep.vls.tiles_total == 2
        assert rep.vls.tiles_ok == 1 and rep.vls.tiles_failed == 1
        assert rep.vls.failed_tiles[0].name == "bad.las"


# --- contract mapping ---------------------------------------------------

class TestContract:

    def test_map_smrf_config(self):
        from sima_relief_service.contract import SmrfParams, map_smrf_config
        cfg = map_smrf_config(SmrfParams(slope=0.3, window=18, threshold=0.5, scalar=1.5))
        assert cfg.slope == 0.3 and cfg.window == 18 and cfg.threshold == 0.5

    def test_filter_kwargs_normalization(self):
        from sima_relief_service.contract import ReliefParams, FilterParams, filter_kwargs
        # spp_min/spp_max приходят из UI-контракта в процентах 0-100
        # (src/api/types.ts, src/pages/Relief.tsx), filter_kwargs переводит их
        # в долю 0.0-1.0, которую ожидает RangeFilter.
        p = ReliefParams(filter=FilterParams(spm_min=-5, spm_max=30, mean_k=8, mult=2.5,
                                              spp_min=0.0, spp_max=95.0))
        kw = filter_kwargs(p)
        assert kw["z_min"] == -5 and kw["z_max"] == 30
        assert kw["neighbours"] == 8 and kw["multiplier"] == 2.5
        assert kw["range_min_pct"] == 0.0 and kw["range_max_pct"] == 0.95


# --- storage ------------------------------------------------------------

class TestStorage:

    def test_session_and_tile_layout(self, tmp_path):
        from sima_relief_service import LocalFSStorage, Session
        st = LocalFSStorage(str(tmp_path / "root"))
        s = Session.new(st, project_id="proj1", session_id="abc")
        td = s.tile_root(st, "tile42")
        assert td.endswith(os.path.join("proj1", "relief", "session-abc", "tile42"))
        assert os.path.isdir(td)
        st.ensure_dir(td)
        f = os.path.join(td, "x.tif")
        Path(f).write_text("x")
        assert st.artifact_size(f) == 1
        assert "x.tif" in st.list_artifacts(td)[0]


# --- tin / shp ----------------------------------------------------------

class TestTinShp:

    def test_build_tin_dxf(self, tmp_path):
        from sima_relief_service.tin import build_tin
        pts = np.array([[0, 0, 10], [10, 0, 12], [0, 10, 11], [10, 10, 13]], float)
        out = str(tmp_path / "tin.dxf")
        build_tin(pts, out)
        txt = Path(out).read_text()
        assert "3DFACE" in txt and "EOF" in txt
        # минимум 2 треугольника
        assert txt.count("3DFACE") >= 2

    def test_build_tin_from_las_min_distance(self, tmp_path):
        """Узлы TIN прорежены по расстоянию: плотная сетка даёт меньше точек."""
        import laspy
        from sima_relief_service.tin import build_tin_from_las
        gx, gy = np.meshgrid(np.arange(0, 20, 1.0), np.arange(0, 20, 1.0))
        gx, gy = gx.ravel(), gy.ravel()
        las = laspy.create(point_format=3, file_version="1.2")
        las.x, las.y = gx, gy
        las.z = np.full(gx.size, 100.0)
        las.classification = np.full(gx.size, 2, dtype=np.uint8)
        inp = str(tmp_path / "ground.las")
        las.write(inp)

        dense = build_tin_from_las(inp, str(tmp_path / "dense.dxf"), min_distance_m=0)
        sparse = build_tin_from_las(inp, str(tmp_path / "sparse.dxf"), min_distance_m=5.0)
        assert Path(dense).read_text().count("3DFACE") > Path(sparse).read_text().count("3DFACE")

    def test_build_tin_too_few_points(self, tmp_path):
        from sima_relief_service.tin import build_tin
        with pytest.raises(ValueError):
            build_tin(np.array([[0, 0, 1], [1, 0, 2]], float), str(tmp_path / "x.dxf"))

    def test_write_points_shp(self, tmp_path):
        from sima_relief_service.shp_io import write_points_shp
        pts = np.array([[100, 100, 95], [110, 110, 96]], float)
        out = str(tmp_path / "alt.shp")
        write_points_shp(pts, out, crs_wkt="EPSG:32642", field_name="alt")
        assert os.path.exists(out)
        assert os.path.exists(out.replace(".shp", ".dbf"))
        # проверим, что OGR читает 3D-точки
        from osgeo import ogr
        ds = ogr.Open(out)
        lyr = ds.GetLayer(0)
        assert lyr.GetFeatureCount() == 2
        f = lyr.GetFeature(0)
        assert f.GetField("alt") == 95.0


# --- steps: existing_dtm + dem-source heights ---------------------------

class TestSteps:

    def test_step_dtm_existing(self, tmp_path):
        from sima_relief_service import steps
        from sima_relief_service.contract import ReliefParams
        dtm = str(tmp_path / "existing.tif")
        _make_dtm_tif(dtm)
        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        result, ground = steps.step_dtm(
            "ignored.las", ReliefParams(), out_dir, "EPSG:32642", 1.0,
            existing_dtm=dtm, save_ground_las=False)
        assert result == dtm
        assert ground is None  # ground_las не строится при existing_dtm

    def test_step_heights_dem_source(self, tmp_path):
        from sima_relief_service import steps
        from sima_relief_service.contract import ReliefParams, HeightsParams
        dtm = str(tmp_path / "d.tif")
        _make_dtm_tif(dtm, size=20)
        params = ReliefParams(heights=HeightsParams(enabled=True, source="dem", min_distance_m=2.0))
        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        out = steps.step_heights(None, params, out_dir, "EPSG:32642", dem_path=dtm, stem="tile1")
        assert out.endswith("_alt.shp") and os.path.exists(out)
        from osgeo import ogr
        assert ogr.Open(out).GetLayer(0).GetFeatureCount() > 0

    def test_step_contours_shp(self, tmp_path):
        from sima_relief_service import steps
        dtm = str(tmp_path / "d.tif")
        _make_dtm_tif(dtm, size=30)
        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        paths = steps.step_contours(dtm, [5.0], out_dir, "EPSG:32642")
        assert len(paths) == 1 and paths[0].endswith(".shp")
        assert os.path.exists(paths[0])


# --- service end-to-end -------------------------------------------------

class TestReliefService:

    def test_run_success_with_existing_dtm(self, tmp_path):
        from sima_relief_service import (ReliefService, ReliefRequest, ReliefParams,
                                          TileInput, DerivativesParams, VectorsParams,
                                          HeightsParams)
        dtm = str(tmp_path / "existing.tif")
        _make_dtm_tif(dtm, size=30)
        params = ReliefParams(
            target_crs="EPSG:32642",
            derivatives=DerivativesParams(slopes=True, aspect=True, tpi=False, interpolation=True),
            vectors=VectorsParams(horizontals=[5.0], tin=False),
            heights=HeightsParams(enabled=True, source="dem", min_distance_m=3.0),
        )
        req = ReliefRequest(params=params, project_id="proj1", resolution=1.0,
                            tiles=[TileInput(name="tile1", existing_dtm=dtm)])
        svc = ReliefService(root_dir=str(tmp_path / "root"))
        res = svc.run(req)
        assert res.job.status == "success"
        assert res.job.tiles_done == 1 and res.job.tiles_failed == 0
        tile = res.job.tiles[0]
        assert tile.status == "done"
        # последовательность шагов зафиксирована в статусах
        names = [s.name for s in tile.steps]
        assert "dtm" in names and "slope" in names and "aspect" in names
        assert "contours" in names and "heights" in names
        # артефакты
        arts = res.artifacts[tile.id]
        kinds = {a.kind for a in arts}
        assert "geotiff" in kinds and "shp" in kinds
        # Q3 форматы: ЦМР/уклон/экспозиция — geotiff; горизонтали/высоты — shp
        layers = {a.layer for a in arts}
        assert {"dtm", "slope", "aspect"} <= layers
        assert "contours" in layers and "heights" in layers

    def test_run_failed_tile_does_not_crash_others(self, tmp_path):
        from sima_relief_service import (ReliefService, ReliefRequest, ReliefParams, TileInput)
        good_dtm = str(tmp_path / "good.tif")
        _make_dtm_tif(good_dtm, size=20)
        params = ReliefParams(target_crs="EPSG:32642")
        # bad-tile: нет ни ВЛС, ни existing_dtm → шаг dtm упадёт
        req = ReliefRequest(params=params, project_id="proj2", resolution=1.0, tiles=[
            TileInput(name="bad"),
            TileInput(name="good", existing_dtm=good_dtm),
        ])
        svc = ReliefService(root_dir=str(tmp_path / "root"))
        res = svc.run(req)
        assert res.job.tiles_done == 1
        assert res.job.tiles_failed == 1
        bad = next(t for t in res.job.tiles if t.name == "bad")
        assert bad.status == "failed" and bad.reason
        # failed_tiles с причинами (требование концепции)
        assert res.job.failed_tiles and res.job.failed_tiles[0].reason

    def test_rerun_creates_new_tile_id(self, tmp_path):
        from sima_relief_service import ReliefService, ReliefRequest, ReliefParams, TileInput
        dtm = str(tmp_path / "e.tif")
        _make_dtm_tif(dtm, size=20)
        params = ReliefParams(target_crs="EPSG:32642")
        req = ReliefRequest(params=params, project_id="proj3", resolution=1.0,
                            tiles=[TileInput(name="t", existing_dtm=dtm)])
        svc = ReliefService(root_dir=str(tmp_path / "root"))
        r1 = svc.run(req)
        r2 = svc.run(req)
        assert r1.job.tiles[0].id != r2.job.tiles[0].id  # история не затирается

    def test_assess_method(self, tmp_path):
        from sima_relief_service import ReliefService, ReliefRequest, ReliefParams, TileInput
        las = str(tmp_path / "g.las")
        _make_ground_las(las)
        tif = str(tmp_path / "d.tif")
        _make_dtm_tif(tif)
        req = ReliefRequest(params=ReliefParams(), project_id="p", resolution=1.0,
                            tiles=[TileInput(name="t", vls_path=las, afs_path=tif)])
        svc = ReliefService(root_dir=str(tmp_path / "root"))
        ma = svc.assess(req)
        assert ma.vls is not None and ma.afs is not None
        assert ma.vls.density_pts_m2 > 0 and ma.afs.resolution_m > 0