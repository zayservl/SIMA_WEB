"""Сборка конвейера PDAL для ЦМД — без запуска самого PDAL."""

from __future__ import annotations

import pytest

from sima_forest_cmd import CHMBuilder, CHMConfig
from sima_forest_cmd.chm import CHMResult


def pipeline(crs='EPSG:32640', config=None, aoi=None):
    builder = CHMBuilder(output='/tmp/chm', crs=crs, config=config or CHMConfig(), aoi=aoi)
    return builder._build_pipeline('input.las', CHMResult(chm='out_chm.tif'))


def stage(pipe, kind):
    return [s for s in pipe if s.get('type') == kind]


class TestReader:
    def test_ск_передаётся_в_reader(self):
        reader = stage(pipeline(crs='EPSG:32640'), 'readers.las')[0]
        assert reader['override_srs'] == 'EPSG:32640'

    @pytest.mark.parametrize('crs', ['', None])
    def test_без_ск_override_srs_не_добавляется(self, crs):
        # PDAL отвергает пустое значение override_srs; без СК берётся та, что в LAS
        reader = stage(pipeline(crs=crs), 'readers.las')[0]
        assert 'override_srs' not in reader


class TestNormalisation:
    def test_высоты_нормализуются_относительно_земли(self):
        pipe = pipeline()
        hag = stage(pipe, 'filters.hag_delaunay')
        assert len(hag) == 1
        assert hag[0]['allow_extrapolation'] == 'true'

    def test_z_заменяется_превышением_над_землёй(self):
        assigns = [v for s in stage(pipeline(), 'filters.assign') for v in s['value']]
        assert 'Z = HeightAboveGround' in assigns

    def test_нормализация_идёт_до_растеризации(self):
        pipe = pipeline()
        types = [s.get('type', 'writers.gdal') for s in pipe]
        assert types.index('filters.hag_delaunay') < types.index('writers.gdal')

    def test_прореживание_до_отсева_шума(self):
        # статистика elm/outlier иначе считается по неравномерной плотности
        types = [s.get('type', '') for s in pipeline()]
        assert types.index('filters.sample') < types.index('filters.elm')

    def test_переклассификация_по_высоте(self):
        cfg = CHMConfig(low_vegetation_max_m=0.4, medium_vegetation_max_m=6.0)
        assigns = [v for s in stage(pipeline(config=cfg), 'filters.assign') for v in s['value']]
        text = ' '.join(assigns)
        assert 'Classification = 3' in text and '0.4' in text
        assert 'Classification = 4' in text and '6.0' in text
        assert 'Classification = 5' in text


class TestWriters:
    def test_растеризация_максимумом(self):
        writer = [s for s in pipeline() if s.get('type') == 'writers.gdal'][0]
        assert writer['output_type'] == 'max'
        assert writer['filename'] == 'out_chm.tif'

    def test_разрешение_прокидывается(self):
        pipe = pipeline(config=CHMConfig(resolution=0.25))
        writer = [s for s in pipe if s.get('type') == 'writers.gdal'][0]
        assert writer['resolution'] == 0.25
        assert stage(pipe, 'filters.sample')[0]['radius'] == 0.25

    def test_по_умолчанию_один_растр(self):
        assert len([s for s in pipeline() if s.get('type') == 'writers.gdal']) == 1

    def test_дополнительные_каналы_по_запросу(self):
        builder = CHMBuilder(output='/tmp/chm', crs='EPSG:32640',
                             config=CHMConfig(with_intensity=True, with_density=True))
        pipe = builder._build_pipeline(
            'input.las', CHMResult(chm='c.tif', intensity='i.tif', density='d.tif'))
        writers = [s for s in pipe if s.get('type') == 'writers.gdal']
        assert len(writers) == 3
        assert {w.get('dimension') for w in writers} == {None, 'intensity', 'NNDistance'}
        assert len(stage(pipe, 'filters.nndistance')) == 1


class TestAoi:
    def test_обрезка_добавляется_только_с_aoi(self):
        assert len(stage(pipeline(aoi=None), 'filters.crop')) == 0
        assert len(stage(pipeline(aoi='POLYGON((0 0,1 0,1 1,0 1,0 0))'), 'filters.crop')) == 1
