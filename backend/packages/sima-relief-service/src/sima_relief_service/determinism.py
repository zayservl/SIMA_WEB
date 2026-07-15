"""Детерминизм/воспроизводимость расчёта рельефа.

PDAL SMRF и GDAL-операции детерминированы сами по себе. Сид нужен для
потенциально стохастических шагов (напр. сэмплирование высот из DEM при
нефиксированной сетке). Здесь — контекст seed + утилиты, готовые к прокидыванию
в шаги. Воспроизводимость — требование ТЗ (#3) и контракта ReliefParams.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class DeterminismContext:
    enabled: bool = False
    seed: int = 0

    @classmethod
    def from_params(cls, deterministic: bool, seed: int) -> "DeterminismContext":
        return cls(enabled=deterministic, seed=int(seed))

    def env_overrides(self) -> dict:
        """Переменные окружения для детерминизма GPU/CLib-стеков (задел).

        Сейчас влияния на CPU-расчёт рельефа нет, но контрактом заложено —
        фронтенд передаёт deterministic/seed, BE должен их пробрасывать.
        """
        return {
            "PYTHONHASHSEED": str(self.seed) if self.enabled else "0",
            "SIMA_DETERMINISTIC": "1" if self.enabled else "0",
            "SIMA_SEED": str(self.seed),
        }

    def apply_env(self) -> None:
        for k, v in self.env_overrides().items():
            os.environ[k] = v