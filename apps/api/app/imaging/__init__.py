"""Deterministic image and geometry operations. No AI calls.

Public interface - keep these names and signatures.
Implementations live in submodules and are re-exported here.
"""

from app.imaging.errors import ImageRejected
from app.imaging.geometry import (
    box_area,
    box_iou,
    box_polygon,
    fill_polygons,
    fraction_box_to_px,
    polygon_area_px,
    polygon_box,
    polygons_mask,
)
from app.imaging.masks import resolve_overlaps, segments_to_candidates
from app.imaging.prep import check_photo, load_upload, make_working_copy, to_jev_jpeg
from app.imaging.render import composite, composite_alpha, region_crop, zone_map

__all__ = [
    "ImageRejected",
    "box_area",
    "box_iou",
    "box_polygon",
    "check_photo",
    "composite",
    "composite_alpha",
    "fill_polygons",
    "fraction_box_to_px",
    "load_upload",
    "make_working_copy",
    "polygon_area_px",
    "polygon_box",
    "polygons_mask",
    "region_crop",
    "resolve_overlaps",
    "segments_to_candidates",
    "to_jev_jpeg",
    "zone_map",
]
