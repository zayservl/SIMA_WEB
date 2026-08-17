"""ReliefService — оркестратор конвейера рельефа (чистый Python).

run(request) -> ReliefResult: для каждой пары/тайла выполняет последовательность
шагов (steps.py), трекает статусы (status.py), пишет артефакты в сессионное
хранилище (storage.py), применяет детерминизм (determinism.py). Упавший тайл →
status 'failed' + reason, остальные продолжаются (требование концепции:
«пропуск тайла + failed_tiles с причинами»). Без raise на одном тайле.

Готов к обёртке в реальный backend-сервис: шаги трекаются как discrete status-
обновления (можно пробросить в Celery task per tile), хранилище абстрагировано
(Storage → S3), статусы — dataclass-модель (→ БД/Redis).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable

from .contract import ReliefRequest, ReliefParams
from .determinism import DeterminismContext
from .status import Job, OutputArtifact, Tile
from .storage import LocalFSStorage, Session, Storage, _new_id
from . import steps as S
from .assessment import CrsCheck, MaterialAssessment, assess_materials, check_pair_crs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ms(start_iso: str) -> int:
    try:
        start = datetime.fromisoformat(start_iso)
        return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    except Exception:  # noqa: BLE001
        return 0


@dataclass
class ReliefResult:
    job: Job
    session: Session
    assessment: Optional[MaterialAssessment] = None
    artifacts: dict = field(default_factory=dict)  # tile_id -> list[OutputArtifact]


class ReliefService:
    """Сервис рельефа: оркестрация шагов по тайлам с трекингом статусов."""

    def __init__(
        self,
        storage: Optional[Storage] = None,
        root_dir: Optional[str] = None,
        reject_crs_mismatch: bool = True,
        save_measured_mask: bool = False,
    ) -> None:
        """
        Args:
            storage: хранилище артефактов; по умолчанию локальная ФС.
            root_dir: корень локального хранилища.
            reject_crs_mismatch: отбраковывать тайлы, у которых СК облака и
                снимка различаются. Выключать имеет смысл только когда СК в
                файлах заведомо объявлена неверно, а фактические координаты
                совпадают.
            save_measured_mask: сохранять рядом с ЦМР маску измеренных ячеек
                (слой `dtm_measured`). Нужна, чтобы отделить точность построения
                рельефа от точности заполнения пустот.
        """
        self.storage: Storage = storage or LocalFSStorage(root_dir or "output")
        self.reject_crs_mismatch = reject_crs_mismatch
        self.save_measured_mask = save_measured_mask
        # Результаты сверки СК по тайлам: tile_id → CrsCheck. Заполняется в run().
        self.crs_checks: dict[str, CrsCheck] = {}

    # --- публичный API ---

    def assess(self, request: ReliefRequest) -> MaterialAssessment:
        """Оценка материалов ВЛС/АФС (Q3 «Оценка файлов»)."""
        vls_files = [t.vls_path for t in request.tiles if t.vls_path] or None
        afs_files = [t.afs_path for t in request.tiles if t.afs_path] or None
        return assess_materials(vls_files=vls_files, afs_files=afs_files)

    def run(self, request: ReliefRequest) -> ReliefResult:
        """Запустить конвейер рельефа по всем тайлам запроса."""
        det = DeterminismContext.from_params(request.params.deterministic, request.params.seed)
        det.apply_env()

        session = Session.new(self.storage, request.project_id, request.session_id)
        job = Job(
            id=_new_id("job"), project_id=request.project_id, type="relief",
            status="running", session_id=session.session_id, started_at=_now_iso(),
            output_dir=session.root, params=None,
        )
        job.tiles_total = len(request.tiles)

        crs = request.params.target_crs
        resolution = request.resolution

        for tile_in in request.tiles:
            tile_id = _new_id("tile")
            tile_dir = session.tile_root(self.storage, tile_id)
            tile = Tile(
                id=tile_id, name=tile_in.name, kind="pair",
                status="running", started_at=_now_iso(), output_dir=tile_dir,
            )
            job.tiles.append(tile)

            # Отбраковка до расчёта: приведения координат в конвейере нет,
            # поэтому пара с разными СК даёт молча смещённый результат.
            check = self._check_crs(tile, tile_in) if self.reject_crs_mismatch else None
            if check is not None and check.blocking:
                tile.status = "skipped"
                tile.reason = check.reason
                tile.finished_at = _now_iso()
                tile.duration_ms = _ms(tile.started_at or _now_iso())
                self.crs_checks[tile.id] = check
                continue

            try:
                arts = self._run_tile(tile, tile_in, request.params, crs, resolution, tile_dir)
                self.artifacts_for(tile, arts)
                tile.status = "done"
            except _StepFailed as e:
                tile.status = "failed"
                tile.reason = str(e)
            except Exception as e:  # noqa: BLE001 — не ронять весь конвейер из-за одного тайла
                tile.status = "failed"
                tile.reason = f"{type(e).__name__}: {e}"
                self._fail_current_step(tile, str(e))
            finally:
                tile.finished_at = _now_iso()
                tile.duration_ms = _ms(tile.started_at or _now_iso())

        job.finished_at = _now_iso()
        job.recompute()
        if job.tiles_done == job.tiles_total and job.tiles_total > 0:
            job.status = "success"
        elif job.tiles_done > 0:
            job.status = "success"  # частичный успех: есть результаты, failed_tiles показаны
        else:
            job.status = "failed"

        artifacts = {t.id: t.output_files for t in job.tiles}
        return ReliefResult(job=job, session=session, assessment=None, artifacts=artifacts)

    # --- внутреннее ---

    def _check_crs(self, tile: Tile, tile_in) -> CrsCheck:
        """Сверить СК пары и записать результат отдельным шагом тайла.

        Шаг видим в таймлайне наравне с расчётными: он объясняет, почему тайл
        пропущен, и подтверждает сверку там, где она прошла. Неопределённая СК
        расчёт не блокирует — сверять нечем, а `target_crs` всё равно
        переопределяет систему при чтении облака.
        """
        check = check_pair_crs(tile_in.vls_path, tile_in.afs_path)
        st = tile.step("crs_check")
        st.mark_running(_now_iso())
        ms = _ms(st.started_at or _now_iso())
        if check.blocking:
            st.mark_failed(_now_iso(), ms, check.reason or "СК не совпадают")
        elif check.status == "match":
            st.mark_done(_now_iso(), ms, "СК облака и снимка совпадают")
        else:
            st.mark_skipped(check.reason or "сверять не с чем: в паре один материал")
        self.crs_checks[tile.id] = check
        return check

    def _step(self, tile: Tile, name: str, fn: Callable) -> object:
        """Выполнить один шаг с трекингом статуса. На провал — _StepFailed."""
        st = tile.step(name)
        st.mark_running(_now_iso())
        tile.current_step = name
        try:
            res = fn()
            st.mark_done(_now_iso(), _ms(st.started_at or _now_iso()))
            return res
        except Exception as e:  # noqa: BLE001
            st.mark_failed(_now_iso(), _ms(st.started_at or _now_iso()), str(e))
            raise _StepFailed(f"{name}: {e}") from e

    def _fail_current_step(self, tile: Tile, reason: str) -> None:
        for st in tile.steps:
            if st.status == "running":
                st.mark_failed(_now_iso(), _ms(st.started_at or _now_iso()), reason)
        if tile.current_step:
            st = tile.step(tile.current_step)
            if st.status not in ("failed", "done", "skipped"):
                st.mark_failed(_now_iso(), 0, reason)

    def _run_tile(
        self, tile: Tile, tile_in, params: ReliefParams, crs: str, res: float, out_dir: str,
    ) -> list[OutputArtifact]:
        """Последовательность шагов для одного тайла. Возвращает артефакты."""
        arts: list[OutputArtifact] = []
        las = tile_in.vls_path
        if not las and not tile_in.existing_dtm:
            raise ValueError("нет ни ВЛС, ни существующей ЦМР для тайла")

        # 1. crop
        las = self._step(tile, "crop", lambda: S.step_crop(las, tile_in.aoi, out_dir))
        # 2. filter
        las = self._step(tile, "filter", lambda: S.step_filter(las, params, out_dir, res))
        # 3. DTM
        dtm, ground_las, measured = self._step(tile, "dtm", lambda: S.step_dtm(
            las, params, out_dir, crs, res, existing_dtm=tile_in.existing_dtm,
            save_ground_las=True, save_measured_mask=self.save_measured_mask))
        arts.append(S._artifact(dtm, "geotiff", "dtm"))
        if ground_las and os.path.exists(ground_las):
            arts.append(S._artifact(ground_las, "las", "ground_las"))
        if measured and os.path.exists(measured):
            arts.append(S._artifact(measured, "geotiff", "dtm_measured"))
        # 3b. DSM (ЦММ) — optional, gated by params.dsm.enabled
        if params.dsm.enabled:
            dsm = self._step(tile, "dsm", lambda: S.step_dsm(las, params, out_dir, crs, res))
            arts.append(S._artifact(dsm, "geotiff", "dsm"))
        # 4. smooth
        smoothed = None
        if params.smoothing.enabled:
            smoothed = self._step(tile, "smooth", lambda: S.step_smooth(dtm, params, out_dir, res))
            if smoothed:
                arts.append(S._artifact(smoothed, "geotiff", "dtm_smooth"))
        base = S.resolve_base_raster(dtm, smoothed)

        # 5. derivatives
        if params.derivatives.slopes:
            slope = self._step(tile, "slope", lambda: S.step_slope(base, crs, out_dir, params.derivatives.slopes_res))
            arts.append(S._artifact(slope, "geotiff", "slope"))
        if params.derivatives.aspect:
            asp = self._step(tile, "aspect", lambda: S.step_aspect(base, crs, out_dir, params.derivatives.aspect_res))
            arts.append(S._artifact(asp, "geotiff", "aspect"))
        if params.derivatives.tpi:
            tpi = self._step(tile, "tpi", lambda: S.step_tpi(base, params, out_dir, crs, res))
            arts.append(S._artifact(tpi, "geotiff", "tpi"))

        # 6. vectors
        if params.vectors.horizontals:
            contours = self._step(tile, "contours", lambda: S.step_contours(
                base, params.vectors.horizontals, out_dir, crs))
            for c in contours:
                arts.append(S._artifact(c, "shp", "contours"))
        if params.vectors.tin:
            tin = self._step(tile, "tin", lambda: S.step_tin(
                ground_las or las, params.heights.min_distance_m, out_dir, crs,
                stem=os.path.splitext(os.path.basename(tile_in.name))[0]))
            arts.append(S._artifact(tin, "dxf", "tin"))

        # 7. heights
        if params.heights.enabled:
            heights = self._step(tile, "heights", lambda: S.step_heights(
                ground_las or las, params, out_dir, crs, dem_path=dtm,
                stem=os.path.splitext(os.path.basename(tile_in.name))[0]))
            arts.append(S._artifact(heights, "shp", "heights"))

        return arts

    def artifacts_for(self, tile: Tile, arts: list[OutputArtifact]) -> None:
        tile.output_files = arts


class _StepFailed(Exception):
    """Сигнал провала шага для обработчика тайла."""
    pass