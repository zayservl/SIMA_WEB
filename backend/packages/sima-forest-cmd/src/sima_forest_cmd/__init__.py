"""СИМА ЦМД — цифровая модель древостоя, детекция деревьев и сегментация крон."""

from .afs import (
    DEFAULT_EXG_THRESHOLD,
    DEFAULT_REFINE_RADIUS_M,
    TopsCorrection,
    VegetationMask,
    correct_tops,
    resample_mask_to_grid,
    resample_to_grid,
    vegetation_index,
    vegetation_mask,
)
from .agreement import Agreement, crown_iou, rasterize_polygons, read_polygons_shp
from .chm import CHMBuilder, CHMConfig, CHMResult, read_chm
from .cost import (
    CostSurface,
    CostWeights,
    build_cost_surface,
    gradient_magnitude,
    local_std,
    luminance,
    robust_normalize,
)
from .crowns import Crowns, crown_areas_by_tree, crowns_to_polygons, delineate_crowns
from .diameter import estimate_stem_diameter
from .features import (
    DEFAULT_PERCENTILES,
    CrownFeatures,
    crown_features,
    crown_geometry,
    crown_height_structure,
    crown_point_features,
    vertical_complexity,
)
from .treetops import (
    DEFAULT_MAX_HEIGHT_M,
    DEFAULT_MIN_HEIGHT_M,
    DEFAULT_SHRUB_HEIGHT_M,
    TreeTops,
    detect_tree_tops,
    disc_kernel,
    prepare_chm,
    split_by_height,
    to_world,
    window_radius_px,
)
from .vector_io import write_crown_polygons, write_tree_points

__all__ = [
    "CHMBuilder", "CHMConfig", "CHMResult", "read_chm",
    "TreeTops", "detect_tree_tops", "prepare_chm", "to_world",
    "split_by_height", "window_radius_px", "disc_kernel",
    "DEFAULT_MIN_HEIGHT_M", "DEFAULT_MAX_HEIGHT_M", "DEFAULT_SHRUB_HEIGHT_M",
    "Crowns", "delineate_crowns", "crowns_to_polygons", "crown_areas_by_tree",
    "VegetationMask", "TopsCorrection", "vegetation_index", "vegetation_mask",
    "resample_mask_to_grid", "resample_to_grid", "correct_tops",
    "DEFAULT_EXG_THRESHOLD", "DEFAULT_REFINE_RADIUS_M",
    "CostWeights", "CostSurface", "build_cost_surface",
    "robust_normalize", "gradient_magnitude", "local_std", "luminance",
    "CrownFeatures", "crown_features", "crown_geometry",
    "crown_height_structure", "crown_point_features", "vertical_complexity",
    "DEFAULT_PERCENTILES",
    "Agreement", "crown_iou", "rasterize_polygons", "read_polygons_shp",
    "estimate_stem_diameter",
    "write_tree_points", "write_crown_polygons",
]
