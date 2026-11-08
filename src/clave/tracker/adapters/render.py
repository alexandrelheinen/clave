"""The one bridge between this package and the simulator.

Every other module in `clave.tracker` works from data a test can write as a
literal. This one turns a MuJoCo segmentation render into that data, and it is
the only module in the package that imports MuJoCo. The import sits inside the
function rather than at module scope, so the package stays importable on a
machine with no simulator, which is the property the quality gate rests on.

Nothing here converts a coordinate or decides anything. It reads pixels and
hands back runs.
"""

from __future__ import annotations

from typing import Any

from clave.tracker.adapters.masks import pixel_mask_from_array
from clave.tracker.evidence import PixelMask

INSTANCE_PREFIX = "object_"
"""How the world names the geometry of a pooled object.

This is the one place the convention is written down. The name is read to find
the instances and is then thrown away by the detection adapter, because the
slot in it is the same integer the world hands out as `ObjectLabel.object_id`.
"""


def segment_masks(model: Any, segmentation: Any) -> dict[str, PixelMask]:
    """Return one instance mask per object visible in a segmentation render.

    MuJoCo renders geometry ids per pixel, so the masks are exact rather than a
    projection estimate, and an object absent from the render is simply absent
    from the result.

    Args:
        model: The compiled model, used to map geometry ids to names.
        segmentation: The segmentation buffer, height by width by two.

    Returns:
        Masks by the geometry name the render was keyed under. The caller is
        expected to discard that key: it carries the simulator's identity, and
        nothing downstream may be able to recover it.
    """
    import mujoco
    import numpy as np

    ids = segmentation[:, :, 0]
    masks: dict[str, PixelMask] = {}
    for geom_id in np.unique(ids):
        if geom_id < 0 or geom_id >= model.ngeom:
            continue
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(geom_id))
        if name is None or not name.startswith(INSTANCE_PREFIX):
            continue
        packed = pixel_mask_from_array(np.asarray(ids == geom_id))
        if packed is not None:
            masks[name.removesuffix("_geom")] = packed
    return masks
