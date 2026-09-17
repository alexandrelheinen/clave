//! The pose an object is predicted to hold when the effector arrives.

use crate::window::MonotonicNanos;

/// A point in the belt frame, in meters.
///
/// The belt frame has its origin at the center of the belt, under the arm, with
/// `x` running along belt travel, `y` across the belt, and `z` measured from the
/// floor the line stands on rather than from the belt surface. A 3.00 m belt
/// therefore runs from `x = -1.50` to `x = +1.50`, and its surface sits at
/// `z = 0.90`. The frame is the one the line is calibrated in, and it is the
/// same frame the effector is commanded in.
///
/// The origin is where it is because the world places it there, not because a
/// belt center is a better datum than a belt edge. Every coordinate this
/// project has measured, every committed golden vector and the safety
/// envelope's own bounds are expressed against it, so the documents were
/// corrected to the frame rather than the frame moved to the documents.
#[derive(Debug, Clone, Copy, PartialEq)]
#[expect(
    clippy::struct_field_names,
    reason = "the unit belongs in the name of a published wire field a consumer reads standalone"
)]
pub struct BeltPoint {
    x_meters: f64,
    y_meters: f64,
    z_meters: f64,
}

impl BeltPoint {
    /// Returns the point at these belt frame coordinates.
    #[must_use]
    pub const fn new(x_meters: f64, y_meters: f64, z_meters: f64) -> Self {
        Self {
            x_meters,
            y_meters,
            z_meters,
        }
    }

    /// Returns the coordinate along belt travel, in meters.
    #[must_use]
    pub const fn x_meters(self) -> f64 {
        self.x_meters
    }

    /// Returns the coordinate across the belt, in meters.
    #[must_use]
    pub const fn y_meters(self) -> f64 {
        self.y_meters
    }

    /// Returns the coordinate normal to the belt surface, in meters.
    #[must_use]
    pub const fn z_meters(self) -> f64 {
        self.z_meters
    }
}

/// The pose an object is predicted to hold at one instant.
///
/// The pose is planar, meaning a point and a yaw, which describes a top-down
/// pick. A tilted object or a gripper approaching off-vertical needs a full
/// orientation, and widening this raises the contract version.
///
/// The pose is a prediction for `reference_time`, not an observation from the
/// frame the object was captured in. The contract checks that
/// `reference_time` falls inside the pick window; it cannot check that an
/// upstream estimator predicted rather than observed, and that is the honest
/// limit of this boundary.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PickPose {
    point: BeltPoint,
    yaw_radians: f64,
    reference_time: MonotonicNanos,
}

impl PickPose {
    /// Returns the pose predicted for `reference_time`.
    #[must_use]
    pub const fn new(point: BeltPoint, yaw_radians: f64, reference_time: MonotonicNanos) -> Self {
        Self {
            point,
            yaw_radians,
            reference_time,
        }
    }

    /// Returns the predicted point in the belt frame.
    #[must_use]
    pub const fn point(self) -> BeltPoint {
        self.point
    }

    /// Returns the predicted rotation about the belt normal, in radians.
    #[must_use]
    pub const fn yaw_radians(self) -> f64 {
        self.yaw_radians
    }

    /// Returns the instant this pose is predicted for.
    #[must_use]
    pub const fn reference_time(self) -> MonotonicNanos {
        self.reference_time
    }
}
