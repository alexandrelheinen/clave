"""Errors from the category model.

Kept out of the GTSAM module so loading a configuration does not import it.
"""

from clave.errors import ClaveError


class BeliefError(ClaveError):
    """A category model cannot be loaded or applied."""
