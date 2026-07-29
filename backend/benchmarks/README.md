# Бенчмаркинг сервиса рельефа

Замер времени и точности `sima-relief-service` на датасете триплетов
`test_data/dsm_dataset` (ОФП + ВЛС + эталонная ЦМР).

## Состав

| Файл | Назначение |
|---|---|
| `relief_bench.py` | харнесс: отбор триплетов, прогон конвейера, замеры, метрики |
| `results/results.jsonl` | сырые результаты, по одной записи на тайл |
| `results/run.log` | лог прогона (локальный, в git не попадает — `*.log` в `.gitignore`) |
| `results/benchmark_tiles.csv` | сводная таблица по тайлам (экспорт из ноутбука) |
| `results/benchmark_by_layer.csv` | время и объём по выходным слоям |
| `../relief_benchmark.ipynb` | анализ, графики, выводы |

## Воспроизведение

Полный прогон (123 триплета, ≈15 мин на 1 потоке):

```bash
cd backend
.venv/bin/python benchmarks/relief_bench.py \
    --root "/Users/sergeyzay/Documents/НЕДРА/СИМА/test_data/dsm_dataset" \
    --out benchmarks/results
```

Пробный прогон на нескольких тайлах с сохранением артефактов:

```bash
.venv/bin/python benchmarks/relief_bench.py --limit 3 --keep-outputs --out /tmp/bench
```

Затем анализ — `backend/relief_benchmark.ipynb` (ядро `sima-backend`;
регистрируется командой `.venv/bin/python -m ipykernel install --user
--name sima-backend --display-name "SIMA backend (.venv)"`). Ноутбук по умолчанию
читает готовый `results.jsonl`; чтобы перезапустить расчёт из ноутбука, установить
`RUN_BENCHMARK = True`.

## Ограничение методологии

ВЛС датасета хранит **ТЛО** (`Z = HeightAboveGround`), а не абсолютные отметки.
Абсолютные Z восстанавливаются по эталонной ЦМР (`restore_absolute`), поэтому
сравнение с эталоном измеряет точность **реконструкции поверхности сервисом**
(SMRF → IDW → заполнение дыр), а не независимую точность съёмки. Подробнее —
в шапке ноутбука и docstring `relief_bench.py`.
