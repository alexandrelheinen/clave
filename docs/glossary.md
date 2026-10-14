# Physical Variables Glossary: `who_what_where`

This document defines the naming grammar, entity vocabulary, physical
properties, reference frames, and unit conventions for all physical variables
across the CLAVE codebase.

The shared baseline lives in [docs/guidelines.md](guidelines.md). This glossary
is the authoritative reference for every `who`, `what`, `where`, and qualifier.
Units are SI inside the code. A unit suffix appears only on a configuration
key, in the short forms below, or in a comment.

---

## 1. Grammar Specification

All variables representing physical quantities, spatial poses, velocities, and
measurements follow the structured pattern:

```
[qualifier_][who_]what[_where]
```

### Segment Breakdown

| Segment | Required? | Description | Examples |
|---|---|---|---|
| `qualifier` | Optional | Modifies state, condition, or extremity | `target_`, `measured_`, `max_`, `min_` |
| `who` | Contextual | The physical body or entity | `flange`, `object`, `jaw`, `belt`, `camera` |
| `what` | **Mandatory** | The physical property or measurement | `position`, `velocity`, `yaw`, `clearance` |
| `where` | Contextual | The coordinate reference frame | `world`, `belt`, `camera`, `flange` |
| `unit` | No | Absent from a code identifier. Configuration keys may use `_deg`, `_mm`, `_ms` |

### Core Invariants

1. **Code stores SI and the identifier names the quantity.** Distance is
   meters ($m$), velocity is meters per second ($m/s$), acceleration is
   $m/s^2$, angle is radians ($rad$), angular velocity is $rad/s$, mass is
   kilograms ($kg$), time is seconds ($s$), and force is newtons ($N$).
2. **A degree, a millimeter, or a millisecond is converted at the
   configuration or IO boundary.** The configuration key uses one short
   suffix: `_deg`, `_mm`, or `_ms`. The identifier that holds the converted
   value has none.
3. **Compound names maintain left-to-right hierarchy:**
   `target_flange_position_world` $\rightarrow$ `[target_]` (qualifier) + `[flange_]`
   (who) + `[position]` (what) + `[_world]` (where).

---

## 2. The `who` Dimension: Bodies and Entities

The `who` token specifies which physical body or component the quantity
describes.

| Token | Body / Entity | Description | Canonical Components |
|---|---|---|---|
| `object` | Waste item | A detected, tracked, or simulated waste package | `src/clave/tracker/track.py` |
| `track` | Track filter | State estimation instance tracking a single waste object | `src/clave/tracker/track.py` |
| `flange` | Tool mounting plate | The circular wrist mounting face of the robot arm where the tool bolts | `src/clave/world/arm.py`, `src/clave/control/task.py` |
| `end_effector` | End-effector | The complete gripper assembly bolted to the arm flange | `src/clave/world/effector.py` |
| `jaw` / `claw` | Gripper fingers | Opposing actuated fingers of the gripper | `src/clave/world/effector.py` |
| `pads` | Gripper pads | Contact surfaces on the gripper jaws that compress against the object | `src/clave/tracker/markers.py` |
| `pinch` | Pinch center | Geometric center of contact between closed gripper pads | `src/clave/world/arm.py`, `src/clave/tracker/markers.py` |
| `belt` | Conveyor belt | Primary sorting conveyor carrying items from intake to sorter | `src/clave/world/belt.py` |
| `takeaway_belt` | Takeaway conveyor | Secondary conveyor receiving sorted or reject materials | `src/clave/world/scene.py` |
| `camera` | Visual sensor | Overhead or wrist camera producing RGB/depth frames | `src/clave/tracker/belt_frame.py` |
| `chute` / `funnel` | Collection hopper | Receptacle receiving sorted material streams (PET, HDPE, reject) | `src/clave/world/scene.py` |
| `base` | Arm base | Rigid pedestal or mounting chassis of the robot manipulator | `src/clave/world/arm.py` |
| `joint` | Arm joint | Articulated revolute or prismatic actuator axis of the arm | `src/clave/world/arm.py` |
| `anchor` | Queue anchor | Spatial position used to score and stabilize candidate pick order | `src/clave/control/selection.py` |
| `led` | Visual marker | Optical tracking LED on the tool or workspace | `src/clave/control/servo.py` |
| `target` | Interception goal | Commanded destination state or pose | `src/clave/control/task.py` |

---

## 3. The `what` Dimension: Physical Properties

The `what` token names the measured or computed physical quantity.

| Token | Property | SI Unit | Dimension | Description |
|---|---|---|---|---|
| `position` | Spatial position | $m$ | Vector $(x, y, z)$ | 3D Cartesian coordinates |
| `velocity` | Linear velocity | $m/s$ | Vector $(\dot{x}, \dot{y}, \dot{z})$ | 3D linear rate of change of position |
| `acceleration` | Linear acceleration | $m/s^2$ | Vector $(\ddot{x}, \ddot{y}, \ddot{z})$ | 3D linear rate of change of velocity |
| `speed` | Linear speed | $m/s$ | Scalar $\lVert \mathbf{v} \rVert$ | Magnitude of linear velocity vector |
| `pose` | 6D pose | $m, rad$ | $(x, y, z, \text{orientation})$ | Spatial position combined with orientation |
| `yaw` | Heading angle | $rad$ | Scalar angle | Rotation about the vertical $z$-axis (normal to belt) |
| `pitch` | Pitch angle | $rad$ | Scalar angle | Rotation about the transverse axis |
| `roll` | Roll angle | $rad$ | Scalar angle | Rotation about the longitudinal axis |
| `angle` | Joint/axis angle | $rad$ | Scalar angle | Angular displacement of an articulated joint |
| `angular_velocity` | Angular velocity | $rad/s$ | Vector $(\omega_x, \omega_y, \omega_z)$ | Rotational rate of change |
| `angular_acceleration` | Angular accel. | $rad/s^2$ | Vector $(\alpha_x, \alpha_y, \alpha_z)$ | Rotational acceleration |
| `distance` | Spatial distance | $m$ | Scalar | Euclidean separation between two points |
| `clearance` | Stand-off distance | $m$ | Scalar | Vertical separation above an object or surface |
| `lift` | Lift displacement | $m$ | Scalar | Vertical distance raised during retreat or carry |
| `length` | Longitudinal extent | $m$ | Scalar | Dimension along primary travel axis ($x$) |
| `width` | Lateral extent | $m$ | Scalar | Dimension across travel axis ($y$) |
| `height` | Vertical extent | $m$ | Scalar | Dimension along vertical normal ($z$) |
| `radius` | Radial distance | $m$ | Scalar | Half-diameter of circular or cylindrical geometry |
| `opening` | Jaw opening | $m$ | Scalar | Linear distance between open gripper pads |
| `extent` | Footprint extent | $m$ | Scalar | Major horizontal dimension of an object footprint |
| `mass` | Inertial mass | $kg$ | Scalar | Mass of an object or body |
| `force` | Mechanical force | $N$ | Vector or scalar | Applied or sensed force |
| `torque` | Rotational moment | $N\cdot m$ | Vector or scalar | Applied or sensed joint torque |
| `duration` | Time span | $s$ | Scalar | Elapsed interval between two instants |
| `timestamp` | Time instant | $s$ | Scalar | Monotonic or simulated time instant |
| `bbox` | Bounding box | image coordinates | Tuple $(x_1, y_1, x_2, y_2)$ | 2D bounding box. A comment says when the index is pixels |

---

## 4. The `where` Dimension: Reference Frames

The `where` token designates the coordinate frame in which a vector or pose is
expressed.

| Frame | Origin | Axes Orientation | Typical Usage |
|---|---|---|---|
| `world` | Simulation / cell origin on floor $(0, 0, 0)$ | $+x$: conveyor travel direction<br>$+y$: across conveyor belt<br>$+z$: vertical upward normal from floor | Interception planning, motion limits, safety checking, absolute robot reach |
| `belt` | Belt surface centerline | $+x$: along belt travel<br>$+y$: across belt lateral width<br>$+z$: vertical upward from belt surface | Object tracking, footprint geometry, intake window bounds |
| `camera` | Camera optical focal center | $+z$: along optical axis (view direction)<br>$+x$: image right<br>$+y$: image down (or robot optical frame) | Raw detections, pixel reprojection, visual servoing |
| `base` | Robot arm base pedestal | $+z$: along joint 1 axis<br>$+x, +y$: base mounting plate plane | Forward and inverse kinematics, joint limits |
| `flange` | Robot wrist mounting face | $+z$: perpendicular outwards from flange face<br>$+x, +y$: tool mounting pattern plane | Effector calibration offsets, wrist load sensors |
| `tool` | Tool pinch point | $+z$: along approach direction<br>$+x$: closing axis between pads | Grasp execution, pad contact checks |
| `joint` | Actuator joint space | 1D angular coordinate per revolute joint | Servo targets, motor encoder feedback |
| `image` / `px` | Top-left of sensor array | $+u$: horizontal column index<br>$+v$: vertical row index | Bounding box detections, segmentation masks |

---

## 5. Qualifiers (Prefixes)

Qualifiers specify lifecycle states, control targets, or extremal boundaries.
They precede `who` or `what`:

| Qualifier | Meaning | Example |
|---|---|---|
| `target_` | Commanded goal or setpoint | `target_flange_position_world`, `target_yaw_world` |
| `current_` | Live instantaneous measurement | `current_joint_angles`, `current_pose_world` |
| `measured_` | Sensor reading before filtering | `measured_object_position_camera` |
| `estimated_` | State filter or tracker belief | `estimated_object_velocity_belt` |
| `min_` | Lower allowable bound | `min_approach_clearance_z`, `min_jaw_opening` |
| `max_` | Upper allowable bound | `max_belt_speed`, `max_acceleration` |
| `peak_` | Maximum observed over an interval | `peak_speed`, `peak_acceleration` |
| `initial_` | Boundary condition at start of arc | `initial_position_world` |
| `final_` | Boundary condition at end of arc | `final_velocity_world` |

---

## 6. Units

Code identifiers carry no unit. A length is meters, an angle is radians, a
duration is seconds. Conversion from another unit happens where configuration
is read and where a person or a wire is written.

A configuration key may append one short suffix when the stored number is
not SI:

| Suffix | Unit in the file | SI after loading |
|---|---|---|
| `_deg` | Degrees ($^{\circ}$) | radians, $\frac{\pi}{180}$ per degree |
| `_mm` | Millimeters | meters, $10^{-3}$ |
| `_ms` | Milliseconds | seconds, $10^{-3}$ |

`yaw_deg: 90` is `yaw` in radians after it is loaded. `spacing: 0.35` is
already meters and takes no suffix. A comment may name the unit. A versioned
wire field keeps the name its contract shipped until that version moves.

---

## 7. Abstraction and Omission Rules

Clarity and modularity require omitting unnecessary segments:

### 1. Omitting `who` (Entity Abstraction)
When an algorithm or utility is generic and operates on spatial points regardless
of which physical body is moving, omit `who`:

```python
# Generic trajectory interpolation: works for flange, object, or camera
def interpolate(
    start_position_world: NDArray[np.float64],
    end_position_world: NDArray[np.float64],
    fraction: float,
) -> NDArray[np.float64]: ...

# Frame transformation: works for any body
def to_camera_frame(
    position_world: NDArray[np.float64],
    camera_pose_world: Pose,
) -> NDArray[np.float64]: ...
```

### 2. Omitting `where` (Frame Abstraction)
When a quantity is invariant across reference frames (scalars like distance,
speed, duration, or mass), omit `where`:

```python
# Speed is frame-invariant magnitude; duration is scalar time
def peak_speed(segment: Segment) -> float: ...
def descent_seconds(approach_clearance_z: float, approach_speed: float) -> float: ...
```

### 3. Axis-Specific Qualifiers
When referencing a single Cartesian component rather than a 3D vector, indicate
the axis before the frame:

```python
approach_clearance_z: float       # Clearance along z axis (meters)
belt_surface_height_world: float  # Height of belt surface along world z (meters)
```

---

## 8. Cross-Reference Index: Legacy to Standard

This index lists common variable renamings across CLAVE:

| Legacy Identifier | Standardized Identifier | Domain Module |
|---|---|---|
| `grasp` | `pinch_position_belt` | `src/clave/tracker/markers.py` |
| `flange` (in marker) | `flange_position_world` | `src/clave/tracker/markers.py` |
| `pads` | `pad_positions_belt` | `src/clave/tracker/markers.py` |
| `closing_axis` | `closing_yaw_belt` | `src/clave/tracker/markers.py`, `selection.py` |
| `anchor` | `anchor_position_belt` | `src/clave/control/selection.py` |
| `park_position` | `park_position_world` | `src/clave/control/settings.py` |
| `belt_surface` | `belt_surface_height_world` | `src/clave/control/task.py` |
| `position` (in Goal) | `target_position_world` | `src/clave/control/task.py` |
| `yaw` (in Goal) | `target_yaw_world` | `src/clave/control/task.py` |
| `z_offset` | `approach_clearance_z` | `src/clave/control/pick.py`, `trajectory.py` |
| `belt_velocity` | `belt_velocity_world` | `src/clave/control/pick.py`, `world/belt.py` |
| `object_position` | `object_position_belt` | `src/clave/control/pick.py`, `trajectory.py` |
| `center` (footprint) | `center_belt` | `src/clave/tracker/belt_frame.py` |
| `yaw` (footprint) | `yaw_belt` | `src/clave/tracker/belt_frame.py` |
| `pinch_point` | `pinch_position_world` | `src/clave/world/arm.py` |
| `ee_pos` | `end_effector_position_world` | `src/clave/world/arm.py` |
| `tool_yaw` | `tool_yaw_world` | `src/clave/world/arm.py` |
