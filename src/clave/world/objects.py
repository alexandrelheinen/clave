"""The waste object set.

Every object carries a material class identifier from the taxonomy, so a rollout
recorded in this world is labeled by construction rather than by a labeling pass
afterwards.

Objects are parametric primitives sized from their real counterparts, not
scanned meshes. That gives correct mass, footprint and grasp width for belt
dynamics, and gives nothing at all for appearance. A perception model trained on
these frames alone would learn shape, which is a limitation this project records
rather than hides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clave.taxonomy import BY_ID, channel_of
from clave.world.config import Range, require, require_range


@dataclass(frozen=True)
class ObjectSpec:
    """One kind of waste object that can appear on the belt.

    Attributes:
        name: Identifier used in the scene and in recorded rollouts.
        material_class: Taxonomy identifier of the form `M-NN`.
        shape: Primitive geometry, one of `cylinder` or `box`.
        size: Half-extents range, interpreted per shape.
        density: Density range in kilograms per cubic meter.
    """

    name: str
    material_class: str
    shape: str
    size: tuple[Range, Range]
    density: Range

    @property
    def channel(self) -> str:
        """The channel this object routes to by default."""
        return channel_of(self.material_class)


def parse(entries: list[dict[str, Any]]) -> tuple[ObjectSpec, ...]:
    """Read the object set from configuration.

    Args:
        entries: The `objects` list from the world configuration.

    Returns:
        The parsed object specs.

    Raises:
        WorldConfigError: If a key is missing, a range is invalid, or a material
            class is not in the taxonomy. An unknown class names the offending
            object, because a mislabeled object silently corrupts every rollout
            recorded from this world.
    """
    from clave.world.config import WorldConfigError

    specs: list[ObjectSpec] = []
    for index, entry in enumerate(entries):
        where = f"objects[{index}]"
        name = require(entry, "name", where)
        material_class = require(entry, "material_class", f"objects.{name}")
        if material_class not in BY_ID:
            raise WorldConfigError(
                f"object {name!r} declares material class {material_class!r}, "
                f"which is not in the taxonomy"
            )
        shape = require(entry, "shape", f"objects.{name}")
        if shape not in ("cylinder", "box"):
            raise WorldConfigError(
                f"object {name!r} declares shape {shape!r}; "
                f"expected 'cylinder' or 'box'"
            )
        specs.append(
            ObjectSpec(
                name=name,
                material_class=material_class,
                shape=shape,
                size=(
                    require_range(entry, "size_a_meters", f"objects.{name}"),
                    require_range(entry, "size_b_meters", f"objects.{name}"),
                ),
                density=require_range(entry, "density_kg_per_m3", f"objects.{name}"),
            )
        )
    return tuple(specs)


def channels(specs: tuple[ObjectSpec, ...]) -> tuple[str, ...]:
    """List the distinct channels an object set needs, in a stable order.

    Args:
        specs: The object set.

    Returns:
        Channel identifiers, deduplicated and sorted, so the bin layout does not
        depend on the order objects happen to be declared in.
    """
    return tuple(sorted({spec.channel for spec in specs}))


def material_classes(specs: tuple[ObjectSpec, ...]) -> tuple[str, ...]:
    """List the distinct material classes an object set covers."""
    return tuple(sorted({spec.material_class for spec in specs}))
