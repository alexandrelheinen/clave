//! The fixed set of material classes a decision may carry.

use serde::{Deserialize, Serialize};

/// A material class from the taxonomy in `docs/waste-taxonomy.md`.
///
/// The taxonomy owns this set, not this crate. Adding, merging, or retiring a
/// class there raises [`CONTRACT_VERSION`](crate::CONTRACT_VERSION) and
/// invalidates every golden vector, which is why the taxonomy marks its
/// identifiers append-only and names this contract as the consumer a rename
/// breaks. A retired class keeps its variant and its discriminant rather than
/// having either reused.
///
/// The discriminant of a variant is the numeric part of its taxonomy
/// identifier, so `M-01` is 1. The wire carries the variant name rather than
/// the discriminant, which is what keeps a reordering from silently remapping
/// every label.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[repr(u16)]
pub enum MaterialClass {
    /// `M-01`, polyethylene terephthalate, resin code 1.
    Pet = 1,
    /// `M-02`, high-density polyethylene, resin code 2.
    Hdpe = 2,
    /// `M-03`, polypropylene, resin code 5.
    Pp = 3,
    /// `M-04`, plastics outside codes 1, 2 and 5, including film.
    OtherPlastic = 4,
    /// `M-05`, non-ferrous metal packaging, chiefly beverage cans and foil.
    Aluminum = 5,
    /// `M-06`, steel and tinplate packaging, chiefly food cans.
    Ferrous = 6,
    /// `M-07`, container glass of any color.
    Glass = 7,
    /// `M-08`, old corrugated containers.
    Cardboard = 8,
    /// `M-09`, paperboard, newsprint and office paper.
    MixedPaper = 9,
    /// `M-10`, liquid packaging board.
    BeverageCarton = 10,
    /// `M-11`, material not recoverable in this stream.
    Residue = 11,
}

impl MaterialClass {
    /// Every class in the fixed set, in taxonomy order.
    pub const ALL: [Self; 11] = [
        Self::Pet,
        Self::Hdpe,
        Self::Pp,
        Self::OtherPlastic,
        Self::Aluminum,
        Self::Ferrous,
        Self::Glass,
        Self::Cardboard,
        Self::MixedPaper,
        Self::BeverageCarton,
        Self::Residue,
    ];

    /// Returns the taxonomy identifier of this class, such as `M-01`.
    ///
    /// The identifier is the stable name. A display name may change; this may
    /// not.
    #[must_use]
    pub const fn taxonomy_id(self) -> &'static str {
        match self {
            Self::Pet => "M-01",
            Self::Hdpe => "M-02",
            Self::Pp => "M-03",
            Self::OtherPlastic => "M-04",
            Self::Aluminum => "M-05",
            Self::Ferrous => "M-06",
            Self::Glass => "M-07",
            Self::Cardboard => "M-08",
            Self::MixedPaper => "M-09",
            Self::BeverageCarton => "M-10",
            Self::Residue => "M-11",
        }
    }
}

impl From<MaterialClass> for u16 {
    #[expect(
        clippy::as_conversions,
        reason = "the enum is repr(u16) and every discriminant is declared in its definition"
    )]
    fn from(value: MaterialClass) -> Self {
        value as Self
    }
}
