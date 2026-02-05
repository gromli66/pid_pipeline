"""
API Routers.
"""

from app.api import diagrams
from app.api import detection
from app.api import cvat
from app.api import segmentation
from app.api import skeleton
from app.api import junction
from app.api import graph
from app.api import validation

__all__ = [
    "diagrams",
    "detection",
    "cvat",
    "segmentation",
    "skeleton",
    "junction",
    "graph",
    "validation",
]