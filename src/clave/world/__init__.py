"""The simulated sorting line.

Importing this package imports no physics engine. MuJoCo is loaded when a scene
is built, so the configuration and object set are readable without it.
"""

from clave.world.belt import Conveyor, ReachReport, SpawnedObject, reach_report
from clave.world.config import Range, WorldConfigError, load, require, require_range
from clave.world.objects import ObjectSpec, channels, material_classes, parse
from clave.world.scene import BeltGeometry, SceneLayout, build, layout

__all__ = [
    "BeltGeometry",
    "Conveyor",
    "ObjectSpec",
    "Range",
    "ReachReport",
    "SceneLayout",
    "SpawnedObject",
    "WorldConfigError",
    "build",
    "channels",
    "layout",
    "load",
    "material_classes",
    "parse",
    "reach_report",
    "require",
    "require_range",
]
