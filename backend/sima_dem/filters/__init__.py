"""Фильтры LAS-точек.

Порт из legacy `relief_analysis/*_filt.py`. Без PDAL — чистый laspy+numpy.
4 фильтра:
  - ManualFilter: порог по Z[z_min:z_max]
  - StatFilter: статистический m·sigma фильтр
  - RangeFilter: перцентильный фильтр
  - OutlierFilter: статистическое удаление выбросов (PDAL filters.outlier)
"""

from .manual_filter import ManualFilter
from .stat_filter import StatFilter
from .range_filter import RangeFilter
from .outlier_filter import OutlierFilter

__all__ = ["ManualFilter", "StatFilter", "RangeFilter", "OutlierFilter"]