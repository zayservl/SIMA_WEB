"""СИМА — вычислительная библиотека ЦМР/ЦМД/рельефа.

Порт legacy QGIS-плагина `23_04_12_digital_elevation_1-46-315/` в чистый Python.
Без QGIS, PyQt5. С использованием GDAL, PDAL, rasterio, laspy, scipy, numpy.

Модули:
  - check_classification: проверка наличия ground-класса в LAS
  - ground: ЦМР (SMRF + растеризация ground-точек)
  - dsm: построение DSM из LAS
  - curvature: уклоны и экспозиции
  - filters: 4 фильтра LAS-точек (manual, stat, range, outlier)
  - crop: обрезка LAS по полигону
  - height: извлечение отметок высот
  - raster: утилиты растров (gauss_smooth, median, tpi, vectorize)
  - pipeline: оркестрация конвейера рельефа
"""

__version__ = "0.1.0"