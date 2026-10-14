---
title: "The CLAVE vision pipeline"
subtitle: "From the camera frame to the grasp pose of each object"
---

# The CLAVE vision pipeline

How CLAVE turns what the belt cameras see into the pose the arm uses to pick
each object, with the mathematics the code runs.

[vision-pipeline.tex](vision-pipeline.tex) carries the same content as a
LaTeX source with numbered propositions and a plotted figure. Every formula
here names the file that implements it. Properties the code states without
proof are proved here, and the ones that can be measured were measured in the
simulator over four seeds of 60 seconds each. The note also records where the
pipeline still depends on the simulator's label.

## Contents

1. [Scope and overview](#1-scope-and-overview)
2. [Frame, clock and propagation](#2-frame-clock-and-propagation)
3. [Optical model of the cameras](#3-optical-model-of-the-cameras)
4. [Instance segmentation](#4-instance-segmentation)
5. [From mask to oriented box](#5-from-mask-to-oriented-box)
6. [Projection into the belt frame](#6-projection-into-the-belt-frame)
7. [Evidence and the intake](#7-evidence-and-the-intake)
8. [Association](#8-association)
9. [Motion estimate: the alpha-beta filter](#9-motion-estimate-the-alpha-beta-filter)
10. [Material fusion](#10-material-fusion)
11. [Lifecycle and the record](#11-lifecycle-and-the-record)
12. [The grasp pose](#12-the-grasp-pose)
13. [From the record to the pose at the instant of the pick](#13-from-the-record-to-the-pose-at-the-instant-of-the-pick)
14. [Measurements](#14-measurements)
15. [Limitations](#15-limitations)
16. [Reproducibility](#16-reproducibility)
17. [Parameters](#17-parameters)
18. [References](#18-references)

## 1. Scope and overview

CLAVE splits responsibility between two processes. Python perceives and
proposes; Rust checks and decides. This note covers only the geometric
perception on the Python side, implemented in `clave.tracker`, and the control
step that turns the perceived record into the pose commanded for the instant of
the pick (`clave.control`). The safety layer, the datagram contract and ROS
publication are out of scope.

The pipeline runs in seven stages, each with its own section:

1. Nadir cameras ([section 3](#3-optical-model-of-the-cameras)).
2. Instance segmentation ([section 4](#4-instance-segmentation)).
3. Moments and the oriented box ([section 5](#5-from-mask-to-oriented-box)).
4. Projection into the belt frame ([section 6](#6-projection-into-the-belt-frame)).
5. Evidence and association ([sections 7](#7-evidence-and-the-intake) and
   [8](#8-association)).
6. The alpha-beta filter and material fusion
   ([sections 9](#9-motion-estimate-the-alpha-beta-filter) and
   [10](#10-material-fusion)), which settle into the `WasteObject` record
   ([section 11](#11-lifecycle-and-the-record)).
7. The grasp pose `GraspMarker` ([section 12](#12-the-grasp-pose)) and the pose
   at the instant of the pick
   ([section 13](#13-from-the-record-to-the-pose-at-the-instant-of-the-pick)).

Three facts bound what *perception* means in the repository as it stands, and a
reader needs them before any formula:

1. **Segmentation is exact.** Masks come from MuJoCo's segmentation buffer,
   which labels each pixel with the geometry covering it. No trained model
   segments the image. Everything after the mask is geometry computed from
   pixels.
2. **Material comes from the simulator's label.** No per-instance classifier
   runs in the loop. The material posterior is fed by `GroundTruth` evidence,
   and the record says so in its `simulated` field.
3. **Detections associate by geometry, and the label rides along.** A detection
   carries no identity and joins the nearest track inside a gate. The
   simulator's label arrives later, through a separate path.

Which pose reaches the arm depends on one configuration key. With
`ground_truth_tracker` set to `false`, the default in
`configs/debug/tracker.yml`, selection and planning consume the poses derived
from vision ([section 12](#12-the-grasp-pose)). With the `--gt` command-line
flag they consume poses read straight from MuJoCo's physics, and the visual
tracker keeps running alongside
([section 12.3](#123-the-alternative-path-the-pose-from-physics)).

## 2. Frame, clock and propagation

**Belt frame.** The belt frame $\mathcal{B}$ has its origin at the center of the
belt, on the centerline and under the arm; $\mathbf{e}_x$ points along belt
travel, $\mathbf{e}_y$ across the belt and $\mathbf{e}_z$ up, with $z$ measured
from the floor. The 3.00 m belt spans $x\in[-1.50, +1.50]$ and its surface sits
at $z_s = 0.90$ m. In the simulator this frame coincides with the world frame,
so no rigid transform separates them.

**Clock.** Every instant is a monotonic integer in nanoseconds, passed as an
argument and never read from a clock of the package's own. The interval between
two instants is

$$
\Delta t(t_0,t_1) = \frac{t_1 - t_0}{10^{9}}\ \text{s},
$$

and may be negative. The consumer decides whether to clamp it at zero, as
`belt_frame.elapsed_seconds` documents.

The belt carries objects along $\mathbf{e}_x$ at a known speed $v_b \ge 0$, so a
point observed at $t_0$ can be carried to any $t_1$ by

$$
\mathbf{p}(t_1) = \mathbf{p}(t_0) + v_b\,\Delta t(t_0,t_1)\,\mathbf{e}_x .
\tag{1}
$$

This is the package's one definition of transport (`belt_frame.carry`).
`propagate` applies (1) to the center of a box and keeps its extents and angle.
A negative or non-finite speed is refused. The speed $v_b$ is not constant over
a run: the feed controller trims it, and the loop copies the current value into
the tracker at every capture (`sim/debug_run.py`).

## 3. Optical model of the cameras

### 3.1 Sensors, lenses and field of view

A camera names the parts it is built from, and its field of view is derived
from them (`configs/world/sorting_line.yml`). The sensor is a Sony IMX264 with
$N_1\times N_2 = 2448\times 2048$ pixels at a pitch of $p = 3.45\ \mu\text{m}$,
and the lenses are Fujinon HF-XA-5M with focal length $f$. The active sensor
sides are

$$
\ell_{\text{long}} = N_1 p = 8.4456\ \text{mm},\qquad
\ell_{\text{short}} = N_2 p = 7.0656\ \text{mm}.
$$

The key `long_axis: across` lays the long side across the belt. MuJoCo reads
`fovy` as the *vertical* field of view, the one along the image rows, and for a
nadir camera turned this way that axis is the across-belt axis $\mathbf{e}_y$.
Hence (`scene.field_of_view`)

$$
\varphi = 2\arctan\left(\frac{\ell_{\text{long}}}{2f}\right),
\qquad
\varphi_{8\,\text{mm}} = 55.65^\circ,\quad
\varphi_{16\,\text{mm}} = 29.57^\circ .
$$

| Identifier | Role | Lens | Position $(c_x, c_y, Z_c)$ in m | Standoff to the belt |
| --- | --- | --- | --- | --- |
| `gate_wide` | detection | 8 mm | $(-1.00,\ 0,\ 1.942)$ | 1.042 m |
| `pick_wide` | detection | 8 mm | $(+0.38,\ 0,\ 1.942)$ | 1.042 m |
| `gate_code_left` | code | 16 mm | $(-1.00,\ +0.33,\ 1.630)$ | 0.730 m |
| `gate_code_center` | code | 16 mm | $(-1.00,\ 0,\ 1.630)$ | 0.730 m |
| `gate_code_right` | code | 16 mm | $(-1.00,\ -0.33,\ 1.630)$ | 0.730 m |

Only the two cameras with the *detection* role feed the geometric pipeline. The
simulation loop selects them by role, never by identifier (`sensors.of_role`),
and the three code cameras are not read in the loop
([section 10.4](#104-barcodes)).

### 3.2 Nadir pinhole projection

Take a rendered image with $W$ columns and $H$ rows. The camera looks straight
down $-\mathbf{e}_z$, so the image plane is parallel to the belt. Under the
pinhole model with a focal length in pixels of

$$
f_{\text{px}} = \frac{H}{2\tan(\varphi/2)},
$$

a point $\mathbf{P} = (X,Y,Z)$ with $Z<Z_c$ projects to continuous column $u$
and row $v$

$$
u = \frac{W}{2} + f_{\text{px}}\,\frac{X - c_x}{Z_c - Z},
\qquad
v = \frac{H}{2} - f_{\text{px}}\,\frac{Y - c_y}{Z_c - Z}.
\tag{2}
$$

The signs encode two orientations the code recorded by measurement rather than
by reasoning (`adapters/detection.py`): the column grows along belt travel, and
the row grows towards $-\mathbf{e}_y$, because row zero is the top of the image
and the far side of the belt.

**Metric scale.** For a horizontal surface at height $h$, one pixel spans

$$
s(h) = \frac{Z_c - h}{f_{\text{px}}} = \frac{2\,(Z_c - h)\tan(\varphi/2)}{H}
\tag{3}
$$

in the belt frame, defined only for $Z_c - h > 0$
(`NadirOptics.meters_per_pixel`). Inverting (2) for points on the plane $Z=h$:

$$
X = c_x + \left(u - \frac{W}{2}\right) s(h),
\qquad
Y = c_y - \left(v - \frac{H}{2}\right) s(h).
\tag{4}
$$

With the image plane parallel to the imaged plane, pixel to meter is a scale
rather than a homography that varies across the frame. The scale does depend on
$h$: a higher surface is closer to the camera and resolves finer.

MuJoCo renders square pixels, with one $f_{\text{px}}$ for both axes. The
horizontal extent of the image therefore follows from the render's aspect ratio
rather than from the sensor:

$$
\text{extent along } \mathbf{e}_x \text{ at } h = W\,s(h) = \frac{W}{H}\,2(Z_c-h)\tan(\varphi/2).
\tag{5}
$$

Scale and coverage of the detection cameras from (3) and (5). The simulation
loop renders at $640\times480$.

| Render | $h$ (m) | $s(h)$ (mm/pixel) | Coverage $y \times x$ (m) |
| --- | --- | --- | --- |
| $640\times480$ | 0.90 (belt) | 2.292 | $1.100 \times 1.467$ |
| $640\times480$ | 0.95 (assumed top) | 2.182 | $1.047 \times 1.396$ |
| $640\times480$ | 1.00 | 2.072 | $0.995 \times 1.326$ |
| native, $H=2448$, $W=2048$ | 0.90 | 0.449 | $1.100 \times 0.920$ |

> **Remark (render aspect).** The declared sensor covers 0.920 m along travel,
> but the $640\times480$ render has a 4:3 aspect in the opposite sense to the
> sensor (1.333 against $2048/2448 = 0.837$) and covers 1.467 m of belt. The
> sweep quoted in `sorting_line.yml`, by which `gate_wide` detects out to
> $x = -0.275$ m, 0.725 m from the camera, agrees with half of 1.467 m and not
> with half of 0.920 m. Along-travel coverage in the simulator is therefore a
> property of the render rather than of the declared hardware. With the real
> optics the two cameras would cover $[-1.46, -0.54]\cup[-0.08, +0.84]$ rather
> than $[-1.73, -0.27]\cup[-0.35, +1.11]$.

## 4. Instance segmentation

### 4.1 The segmentation buffer

With segmentation enabled, MuJoCo's renderer returns an array
$S\in\mathbb{Z}^{H\times W\times 2}$ whose first channel is the identifier of
the geometry visible at each pixel. For each identifier $g$ whose geometry is
named `object_<slot>`, the instance mask is

$$
M_g = \{(u_i, v_i)\in\{0,\dots,W-1\}\times\{0,\dots,H-1\} : S(v_i,u_i,0) = g\}
$$

(`adapters/render.segment_masks`). The mask is exact in the sense that each
pixel belongs to the geometry the rasterizer drew there. It includes the side
faces perspective makes visible, and it excludes whatever another geometry
covers, such as the arm or the effector passing between camera and belt.

A mask is stored as horizontal runs $(r, c_0, n)$, each covering pixels
$(c_0,r),\dots,(c_0+n-1,r)$ (`evidence.PixelMask`). The type refuses frames with
no pixels, empty masks and runs outside the frame.

### 4.2 Discarding identity

The mask dictionary is keyed by geometry name, and the slot in that name is the
same integer the world hands out as `ObjectLabel.object_id`. The detection
adapter iterates over the *values* and never copies a key into evidence
(`detections_from_masks`). The only identity the simulator knows about a pixel
is dropped here, and from this point on a detection does not know which object
it belongs to.

## 5. From mask to oriented box

### 5.1 Moments of order zero, one and two

Let $M$ be a mask of $N = |M|$ pixels, each given by its integer indices
$(x_i, y_i) = (\text{column}, \text{row})$. The code computes
(`oriented_extent`)

$$
\bar x = \frac1N\sum_i x_i,\qquad \bar y = \frac1N\sum_i y_i,
$$

$$
\mu_{20} = \frac1N\sum_i (x_i-\bar x)^2,\qquad
\mu_{02} = \frac1N\sum_i (y_i-\bar y)^2,\qquad
\mu_{11} = \frac1N\sum_i (x_i-\bar x)(y_i-\bar y).
$$

Central moments do not change if each pixel is represented by its center
$(x_i+\tfrac12, y_i+\tfrac12)$ rather than its index, because a common
translation cancels in the differences.

The mask's covariance matrix

$$
\Sigma = \begin{pmatrix}\mu_{20} & \mu_{11}\\ \mu_{11} & \mu_{02}\end{pmatrix}
$$

is symmetric positive semidefinite, with eigenvalues

$$
\lambda_\pm = \frac{\mu_{20}+\mu_{02} \pm \sqrt{(\mu_{20}-\mu_{02})^2 + 4\mu_{11}^2}}{2},
\qquad \lambda_+ \ge \lambda_- \ge 0 .
$$

### 5.2 Principal extents

**Proposition 1.** If $M$ discretizes a uniformly filled rectangle with sides
$a\ge b$, then in the continuous limit $\lambda_+ = a^2/12$ and
$\lambda_- = b^2/12$, so $a = 2\sqrt3\,\sqrt{\lambda_+}$ and
$b = 2\sqrt3\,\sqrt{\lambda_-}$.

*Proof.* In the rectangle's own axes, centered on it, the coordinates
$(\xi,\eta)$ are independent and uniform on $[-a/2,a/2]\times[-b/2,b/2]$. The
covariance is diagonal with
$\operatorname{Var}\xi = \frac1a\int_{-a/2}^{a/2}\xi^2\,d\xi = a^2/12$ and
$\operatorname{Var}\eta = b^2/12$. A rotation preserves the eigenvalues of
$\Sigma$, so the eigenvalues in the image are the same, and since $a\ge b$ the
larger one is $a^2/12$. $\square$

The code defines the extents in pixels as

$$
A = 2\sqrt3\,\sqrt{\lambda_+},\qquad
B = \max\left(2\sqrt3\,\sqrt{\lambda_-},\ 1\right).
$$

By Proposition 1 the estimator is exact for a rectangle, and for any other shape
it returns the uniform rectangle with the same second moments. The one-pixel
floor on $B$ keeps a single-row mask from having zero width. A synthetic
$60\times20$ pixel rectangle turned by $30^\circ$ returns $A = 60.04$ and
$B = 19.99$.

### 5.3 Orientation

**Proposition 2.** The eigenvector of $\lambda_+$ makes, with the column axis,
the angle

$$
\theta = \tfrac12\,\operatorname{atan2}\left(2\mu_{11},\ \mu_{20}-\mu_{02}\right)
\in \left(-\tfrac{\pi}{2}, \tfrac{\pi}{2}\right].
$$

*Proof.* Let $\mathbf{d}(\alpha) = (\cos\alpha, \sin\alpha)$. The variance along
$\mathbf{d}$ is

$$
\sigma^2(\alpha) = \mathbf{d}^\top\Sigma\,\mathbf{d}
= \tfrac{\mu_{20}+\mu_{02}}{2} + \tfrac{\mu_{20}-\mu_{02}}{2}\cos2\alpha + \mu_{11}\sin2\alpha
= \tfrac{\mu_{20}+\mu_{02}}{2} + R\cos(2\alpha - 2\theta),
$$

with $R = \tfrac12\sqrt{(\mu_{20}-\mu_{02})^2+4\mu_{11}^2}$ and
$2\theta = \operatorname{atan2}(2\mu_{11}, \mu_{20}-\mu_{02})$. Its maximum,
equal to $\lambda_+$, falls at $\alpha=\theta$ modulo $\pi$, and the maximizer of
a quadratic form on the unit circle is the eigenvector of the largest
eigenvalue. $\square$

**Orientability.** With $\rho = 1.15$ (`ROUNDNESS`), a mask states an
orientation when

$$
o = \left[\,2\sqrt3\sqrt{\lambda_-} > 0 \ \wedge\ \frac{A}{2\sqrt3\sqrt{\lambda_-}} \ge \rho\,\right]
\iff \frac{\lambda_+}{\lambda_-} \ge \rho^2 = 1.3225 .
$$

When $o$ is false the code uses $\theta = 0$ and flags the angle as
meaningless. The reason is the sensitivity of $\theta$: as
$\lambda_+\to\lambda_-$, $R\to0$ and the argument of $\operatorname{atan2}$
tends to $(0,0)$, so one pixel of noise on the boundary turns $\theta$ by an
arbitrary amount. An arbitrary angle that the control layer treats as measured
is worse than no angle.

### 5.4 Center

The box center is *not* the centroid $(\bar x,\bar y)$. It is the center of the
box aligned with the image axes (`PixelMask.bounds`):

$$
\hat u = \frac{u_{\min}+u_{\max}}{2},\qquad
\hat v = \frac{v_{\min}+v_{\max}}{2},
\tag{6}
$$

with $u_{\min}, u_{\max}, v_{\min}, v_{\max}$ the inclusive extreme indices. The
two centers coincide for a centrally symmetric shape. For an asymmetric one, a
bottle seen from above for instance, they differ, and the axis-aligned center
then depends on how the object is turned in the image.

### 5.5 Confidence

The adapter's confidence in a detection is

$$
c = \min\left(1,\ \frac{N}{400}\right),
$$

which saturates at 400 pixels (`_confidence_of`). In the measurements of
[section 14](#14-measurements), every whole mask exceeds 400 pixels (median
1385, tenth percentile 838), so $c=1$ for all of them: in the current regime the
confidence does not tell one detection from another.

## 6. Projection into the belt frame

### 6.1 The box on the belt

The adapter applies (4) to the center (6) at an *assumed* surface height
$h_a = z_s + 0.05 = 0.95$ m, the same for every object (`sim/debug_run.py`):

$$
x = c_x + \left(\hat u - \frac W2\right)s(h_a),\qquad
y = c_y - \left(\hat v - \frac H2\right)s(h_a).
\tag{7}
$$

The extents convert with the same scale, $L = A\,s(h_a)$ and $\ell = B\,s(h_a)$.
The estimated height above the belt is $\eta = h_a - z_s = 0.05$ m, also a
constant. The result is the oriented box

$$
F = \left(\mathbf{c} = (x,\,y,\,h_a),\ L,\ \ell,\ \psi,\ o\right),
\qquad L \ge \ell > 0,
$$

whose constructor refuses non-positive extents and swapped axes
(`belt_frame.Footprint`). A degenerate mask whose projected extent is zero is
dropped before it becomes evidence. The detections of one frame are sorted by
$x$, so the result does not depend on the dictionary's iteration order.

### 6.2 The sign of the angle

**Proposition 3.** If the major axis makes an angle $\theta$ with the column axis
in the image, it makes an angle $\psi = -\theta$ with $\mathbf{e}_x$ on the belt.

*Proof.* By (4), the linear map from image displacements to belt displacements
is $J = s\,\operatorname{diag}(1,-1)$. The direction $(\cos\theta,\sin\theta)$
maps to $s(\cos\theta, -\sin\theta) = s(\cos(-\theta), \sin(-\theta))$. Since
$J$ is a reflection followed by a scale, it conjugates rotations:
$J R(\theta) J^{-1} = R(-\theta)$. $\square$

The code applies exactly this sign change (`yaw=-yaw`). Forgetting it would
mirror every orientation about the centerline without any other component
noticing.

### 6.3 Geometric error analysis

The back-projection (7) assumes every pixel of the mask lies on the plane
$z = h_a$. Three effects break that assumption.

**Height parallax.** A point at height $z$ and horizontal distance $d$ from the
optical axis projects by (2) to $f_{\text{px}}\,d/(Z_c-z)$, and back-projection
at $h_a$ places it at $\hat d = d\,(Z_c-h_a)/(Z_c-z)$. The radial error is

$$
\hat d - d = d\,\frac{z - h_a}{Z_c - z}.
$$

For $Z_c = 1.942$ and $h_a = 0.95$, a point on the belt ($z=0.90$) at
$d = 0.5$ m appears 24.0 mm closer to the axis, and a point at $z = 1.00$
appears 26.5 mm further out.

**Silhouette of a prism.** The mask is the silhouette of the whole object, not
the projection of its top face. Take a vertical prism of radial width $D$,
bottom at $z_b$ and top at $z_t$, centered at distance $d > D/2$ from the axis.
The outer edge of the silhouette is the top outer edge, because the point at
radius $d+D/2$ projects further out the higher it sits. The inner edge is the
*bottom* inner edge, by the same argument applied to radius $d - D/2 > 0$. With
$a_t = (Z_c-h_a)/(Z_c-z_t)$ and $a_b = (Z_c-h_a)/(Z_c-z_b)$, the back-projected
box center sits at

$$
\hat d = \tfrac12\left[(d + D/2)\,a_t + (d - D/2)\,a_b\right],
$$

and the radial error of the center is

$$
\hat d - d = d\left(\frac{a_t+a_b}{2} - 1\right) + \frac{D}{4}\,(a_t - a_b).
\tag{8}
$$

With the measured median top height, $z_t = 0.96$ m, and $z_b = z_s = 0.90$ m,
$a_t = 1.0102$ and $a_b = 0.9520$, and the coefficient of $d$ is $-0.0189$: an
inward bias of about 19 mm per meter from the axis, plus a constant
$D/4\cdot0.058$ that is 1.5 mm for $D = 0.10$ m. When the object straddles the
axis ($d < D/2$), both silhouette edges are top edges and the bias becomes
$d(a_t - 1)$, small and positive. The model explains the sign and the order of
magnitude of the measured error ([section 14.2](#142-adapter-from-mask-to-box)).
The rest of the gap comes from what the model leaves out: scanned meshes are
not prisms, the underside of a lying object is not flat, and the measurement
reference is the center of mass rather than the geometric center.

**Half-pixel bias.** Pixel index $i$ covers the continuous interval $[i, i+1)$,
centered at $i + \tfrac12$, and the optical axis passes through $u = W/2$. For a
symmetric silhouette with continuous center $u^\star$, the extreme indices give
$\hat u = u^\star - \tfrac12$. Through (7) that shift becomes

$$
\delta x = -\tfrac12\,s(h_a) = -1.09\ \text{mm},
\qquad
\delta y = +\tfrac12\,s(h_a) = +1.09\ \text{mm}.
\tag{9}
$$

For detections within 0.15 m of the axis, where parallax is small, the measured
mean error is $(-1.08, +0.92)$ mm, in agreement with (9). Adding $\tfrac12$ to
$\hat u$ and $\hat v$ would remove the bias.

**Masks clipped by the frame edge.** When part of the object lies outside the
image, the box (6) shrinks on the clipped side and the center moves into the
frame by about half the lost length. Nothing in the adapter notices: a clipped
mask becomes evidence like any other. In [section 14](#14-measurements), 10.5 %
of detections fall in this case, with a median error of 48.6 mm.

## 7. Evidence and the intake

Each detection becomes an envelope

$$
E = (\text{source},\ \text{role},\ t,\ c,\ \text{payload}),
$$

whose payload is a tagged union of five variants: `Detection` (box, mask and
height), `Material` (posterior over the classes), `Code` (decoded symbol),
`Height` (measured top height) and `GroundTruth` (the simulator's label). The
envelope refuses a role that disagrees with the payload and a confidence
outside $[0,1]$ (`evidence.Evidence`). A variant states what was *measured*,
never what should be *done*.

Every reading crosses one door (`intake.Intake.accept`), which applies three
rules:

1. on a deployment declared `HARDWARE`, `GroundTruth` is refused;
2. a source the line does not declare is refused;
3. a source that declares a different role from the reading's is refused.

The simulation loop runs with `Deployment.SIMULATED`, so the first rule does not
act there.

## 8. Association

### 8.1 What the associator may see

Before associating a reading taken at $t$, the tracker carries every open track
$j$ to $t$ (`Track.at`). A track with a motion estimate uses it
([section 9](#9-motion-estimate-the-alpha-beta-filter)); one without applies (1)
to the last observed box. The associator receives one summary per track, with
the propagated box $F_j(t)$ and the label $\lambda_j$ when there is one, and a
*cue* (`Cue`) from the reading. A detection yields a cue with a box and no
label. A `GroundTruth` reading yields a cue with the label $\lambda$ and a box
centered on the true position, of extent $\varepsilon_u = 0.085$ m, the widest
grasp the line handles (`track._cue_of`).

### 8.2 The rule

The shipped implementation is `SimulatorIdentity` (`association.py`). Let
$\mathcal{T}$ be the set of open tracks.

1. If the cue has a label $\lambda$ and some $j\in\mathcal T$ has
   $\lambda_j = \lambda$, the reading joins $j$. If no track carries that label,
   the candidate set becomes $\mathcal T' = \{j : \lambda_j = \varnothing\}$.
   With no label, $\mathcal T' = \mathcal T$.
2. With the cue's center $\mathbf{c}$, each candidate gets a horizontal distance
   and a gate

   $$
   d_j = \left\|\Pi\left(\mathbf{c}_j(t) - \mathbf{c}\right)\right\|_2,
   \qquad
   g_j = \gamma\,L_j,\quad \gamma = 1.5,
   $$

   with $\Pi$ the projection onto $(x,y)$ and $L_j$ the track's major extent.
3. The reading joins

   $$
   j^\star = \operatorname*{arg\,min}_{j\in\mathcal T' :\ d_j \le g_j} d_j,
   $$

   and opens a new track when that set is empty.

The gate scales with the object rather than with a fixed radius, so a large
package reaches further than a small one. A new track gets a strictly
increasing identifier that is never reused, and a uniform posterior.

At each capture the loop delivers the detections of `gate_wide` first, then
those of `pick_wide`, and finally one `GroundTruth` reading per active object
(`sim/debug_run.py`). Two consequences follow from that order:

- a track's position is decided by detection geometry alone, and the label only
  attaches to whichever track already sits near the true position;
- an object seen by both cameras in one capture receives two detections at the
  same instant, and the second corrects only the position
  ([section 9.4](#94-two-detections-at-one-instant)).

> **Remark (tracks opened by the label).** When a `GroundTruth` reading finds no
> track with its label and no unlabeled track inside the gate, it opens a new
> track whose box is the cue's, centered on the true position
> (`Tracker._open`). The `simulated` field of that record lists only
> `material`, not the position. In the measurements of
> [section 14](#14-measurements), 37 of 1315 records (2.8 %) are in this case.
> It weighs little, because until a detection reaches them such tracks age and
> retire after 1.5 s, but it is a path by which a simulator position reaches a
> record without being declared as one.

### 8.3 The dominant failure mode

When a track's prediction misses by more than its gate, the next detection of
the same object opens a duplicate. The original track, which holds the label,
stops receiving detections, carries on by estimate until it retires, and in the
meantime describes a place where no object is. This is the identity
fragmentation that `docs/measurements.md` already diagnoses, and it is the
largest source of the error tail measured in
[section 14.3](#143-tracker-the-record).

## 9. Motion estimate: the alpha-beta filter

### 9.1 Model and recursion

Each horizontal axis has a state $(p, v)$ and a constant-velocity model. The
first detection opens the estimate with the belt's speed along travel and zero
velocity across (`motion.begin`):

$$
\mathbf{p}_0 = (x, y),\qquad \mathbf{v}_0 = (v_b,\ 0).
$$

For a new observation $z$ at instant $t$, with $T = t - t_{k}$, each axis
follows (`motion.fold`)

$$
p^- = p_k + v_k T,\qquad r = z - p^-,\qquad
p_{k+1} = p^- + \alpha\,r,\qquad v_{k+1} = v_k + \beta\,\frac{r}{T}\quad (T>0),
\tag{10}
$$

and when $T \le 0$ only the position is corrected, $v_{k+1} = v_k$. The
estimate's instant becomes $\max(t, t_k)$. Between observations the predicted
position is $p(t) = p_k + v_k (t - t_k)$ (`Estimate.at`).

Gains configured in `configs/perception/fusion.yml`:

| Axis | $\alpha$ | $\beta$ | Eigenvalues of $\Phi$ | Steady-state Kalman $\beta$ (DWNA) |
| --- | --- | --- | --- | --- |
| along ($x$) | 0.80 | 0.05 | 0.936 and 0.214 | 0.611 |
| across ($y$) | 0.70 | 0.20 | 0.600 and 0.500 | 0.409 |

The asymmetry is deliberate. Along travel the belt imposes the velocity
rigidly: the small $\beta$ keeps segmentation noise from being learned as
velocity, and it is not zero because the feed controller changes $v_b$. Across
the belt nothing drives the object, so every drift has to be learned from
observations.

### 9.2 Stability

**Proposition 4.** With a fixed period $T$ and an object at constant velocity,
the error $\mathbf{e}_k = (p_k - p^\star_k,\ v_k - v^\star)$ evolves without
noise as $\mathbf{e}_{k+1} = \Phi\,\mathbf{e}_k$, with

$$
\Phi = \begin{pmatrix} 1-\alpha & (1-\alpha)T \\ -\beta/T & 1-\beta \end{pmatrix},
\qquad
\det(\lambda I - \Phi) = \lambda^2 - (2-\alpha-\beta)\lambda + (1-\alpha).
$$

The filter is asymptotically stable if and only if $0<\alpha<2$ and
$0<\beta<4-2\alpha$, and its steady-state error for a constant velocity is zero.

*Proof.* With $z_{k+1} = p^\star_{k+1} = p^\star_k + v^\star T$, the residual is
$r = -(e_p + e_v T)$. Substituting into (10) gives
$e_p' = (1-\alpha)(e_p + e_v T)$ and
$e_v' = e_v - \tfrac{\beta}{T}(e_p + e_v T)$, which is $\Phi\,\mathbf e$. The
characteristic polynomial follows from the trace $2-\alpha-\beta$ and the
determinant $(1-\alpha)(1-\beta) + \beta(1-\alpha) = 1-\alpha$. By the Jury
criterion for $\lambda^2 + a_1\lambda + a_0$, both roots lie in the open unit
disc if and only if $|a_0|<1$, $1+a_1+a_0>0$ and $1-a_1+a_0>0$, which is
$0<\alpha<2$, $\beta>0$ and $4 - 2\alpha - \beta > 0$. Since the recursion is
linear and homogeneous in the error, $\mathbf e_k\to 0$ and the steady-state
error is zero. $\square$

The eigenvalues in the gain table follow from that polynomial. Along travel, the
slow mode of 0.936 per capture is a time constant of
$-T/\ln 0.936 \approx 7.6$ s at $T = 0.5$ s: the filter corrects a wrong
along-travel velocity over several seconds, on purpose. Across the belt, the
modes of 0.6 and 0.5 decay in about one capture.

### 9.3 Noise attenuation

**Proposition 5.** If the true position is constant and the observation carries
white noise of variance $\sigma^2$, the steady-state variances are

$$
\frac{\operatorname{Var} p}{\sigma^2} = \frac{2\alpha^2 + 2\beta - 3\alpha\beta}{\alpha(4-2\alpha-\beta)},
\qquad
\frac{\operatorname{Var} v}{\sigma^2} = \frac{1}{T^2}\,\frac{2\beta^2}{\alpha(4-2\alpha-\beta)} .
$$

These are the classical variance reduction ratios of the alpha-beta filter
[1, 2]; the proof solves the discrete Lyapunov equation
$P = \Phi P \Phi^\top + \sigma^2\mathbf{k}\mathbf{k}^\top$ with
$\mathbf k = (\alpha, \beta/T)$. With the configured gains and $T = 0.5$ s:

| Axis | $\operatorname{Var}p/\sigma^2$ | $\operatorname{Var}v/\sigma^2$ (s$^{-2}$) |
| --- | --- | --- |
| along | 0.670 | 0.0106 |
| across | 0.571 | 0.190 |

A Monte Carlo run of $2\times10^5$ steps through `motion.fold` itself reproduces
all four values to three digits.

> **Remark (relation to the Kalman filter).** The code's comments describe the
> filter as the steady-state Kalman filter for a constant-velocity model. The
> structure is the same, but the configured gains do not lie on the steady-state
> Kalman curve of the standard discrete white noise acceleration (DWNA) model,
> $\beta = 2(2-\alpha) - 4\sqrt{1-\alpha}$ [3], which would give
> $\beta = 0.611$ and $0.409$. Nor do they lie on the Benedict-Bordner curve,
> $\beta = \alpha^2/(2-\alpha)$, which would give 0.533 and 0.377. The
> configured values were tuned by sweeping against the simulator's label
> (`fusion.yml`), and they describe an alpha-beta filter that smooths velocity
> harder than either criterion would.

### 9.4 Two detections at one instant

In the overlap of the two cameras, $x\in[-0.35, -0.27]$ m in the current
render, an object yields two detections at the same $t$. The second arrives
with $T = 0$ and applies only $p \leftarrow p + \alpha(z_2 - p)$. Its effect on
the position is a weighted average of the two observations, with weight
$\alpha$ for the second and $\alpha(1-\alpha)$ for the first.

### 9.5 What a detection updates

After the filter, the track's box becomes that of the latest observation, with
extents $L$, $\ell$, angle $\psi$ and $o$ copied from it and the horizontal
center replaced by the filtered position (`Tracker._fold`). The filter models
where the object is going, not its size or its orientation: a record's angle is
always the last mask's, with no smoothing and no angular rate.

## 10. Material fusion

### 10.1 The posterior

A track's posterior is a distribution $\pi$ over the 12 outcomes
$\Omega = \{\text{M-01},\dots,\text{M-11},\text{reject}\}$, uniform when the
track opens (`fusion.Posterior`). Each reading enters with weight

$$
w = c\cdot 2^{-\max(0,\Delta t)/\tau},\qquad \tau = 2.0\ \text{s},
$$

where $\Delta t$ is the reading's age at the instant it is folded
(`weight_of`). The clamp at zero keeps an out-of-order reading, with
$\Delta t<0$, from outweighing a fresh one. The weight function does not
receive the source, so no sensor priority can be expressed.

### 10.2 The floored update

Given a likelihood $\boldsymbol\ell$ and a floor $\epsilon = 5\times10^{-4}$, the
update is a tempered Bayes product followed by the floor operator
(`Posterior.fold`):

$$
q_k = \frac{\pi_k\,\max(\ell_k,\epsilon)^{w}}{\sum_j \pi_j\,\max(\ell_j,\epsilon)^{w}},
\qquad
\pi' = \Phi_\epsilon(q),
\tag{11}
$$

$$
\Phi_\epsilon(q)_k = \epsilon + (1 - |\Omega|\epsilon)\,
\frac{(q_k - \epsilon)_+}{\sum_j (q_j-\epsilon)_+},
\tag{12}
$$

with $(\cdot)_+ = \max(\cdot,0)$. When $w\le0$ nothing changes.

**Proposition 6.** If $0<\epsilon<1/|\Omega|$ and some $q_j>\epsilon$, then
$\Phi_\epsilon(q)$ is a distribution, $\Phi_\epsilon(q)_k\ge\epsilon$ for every
$k$, and $q_i \le q_k \Rightarrow \Phi_\epsilon(q)_i \le \Phi_\epsilon(q)_k$.

*Proof.* The sum is $|\Omega|\epsilon + (1-|\Omega|\epsilon)\cdot 1 = 1$. Each
term is $\epsilon$ plus a non-negative share, because $1-|\Omega|\epsilon>0$.
The map $q\mapsto (q-\epsilon)_+$ is non-decreasing and the remaining factors
are common to every $k$, which preserves the order. $\square$

The code records why the construction is this one: lifting values to the floor
and then renormalizing would push some of them back under it. Proposition 6
shows that (12) makes the floor exact.

### 10.3 The simulator's label

For `GroundTruth` of class $m$, the likelihood is $\ell_m = 1$ and
$\ell_k = \epsilon$ for $k\ne m$, with $c = 1$ and zero age, so $w = 1$.

**Proposition 7.** From any posterior with $\pi_m \ge \pi_k$ for every $k$, the
uniform one included, one `GroundTruth` fold reaches
$\pi'_m = 1 - 11\epsilon = 0.9945$ and $\pi'_k = \epsilon$ for $k\ne m$, and that
point is fixed under further folds of the same class.

*Proof.* From uniform, $q_m = 1/(1+11\epsilon)$ and
$q_k = \epsilon/(1+11\epsilon) < \epsilon$. Then $(q_k-\epsilon)_+ = 0$ for
$k\ne m$, and (12) gives $\pi'_m = \epsilon + (1-12\epsilon) = 1-11\epsilon$.
From that point, $q_k = \epsilon^2/Z < \epsilon$ for $k \ne m$, with
$Z = (1-11\epsilon) + 11\epsilon^2 < 1$, and the same computation returns the
same point. The general case with $\pi_m$ largest is analogous, because
$q_k \le \epsilon\,\pi_k/\pi_m \le \epsilon$. $\square$

This is exactly what was measured: the median material confidence of the
records is 0.9945, and the class is right in 100 % of them. The material
confidence therefore measures no perception at all.

### 10.4 Barcodes

A decoded code passes its modulo-10 check digit (UPC-A, EAN-8, EAN-13) and
resolves through a catalog to the packaging components $C$ (`codes.py`). The
likelihood spreads over the components, $\ell_k = 1/|C|$ for $k\in C$ and
$\ell_k = \epsilon$ elsewhere, and the weight shrinks with the current
certainty:

$$
w_{\text{code}} = w\,\left(1 - \max_k \pi_k\right).
$$

A code therefore never overturns a confident belief. With the posterior
saturated by the label at 0.9945, a code would enter with a weight of at most
$0.9\times0.0055\approx 0.005$. In the current simulation loop no code camera is
read and no code reaches the tracker; decoding is exercised only by the yield
measurement in `tracker/measure.py`.

### 10.5 Material from a classifier

The rule for the `Material` variant exists and folds a classifier's posterior
straight in through (11). Nothing in the loop produces it. The trained
perception stage (`docs/architecture.md`) classifies the whole frame, with a
multilabel $(B,11)$ output for $96\times96$ inputs, and assigns no material to
an instance, so it cannot feed a track.

## 11. Lifecycle and the record

### 11.1 Retirement

Let $t^{\text{obs}}_j$ be the instant of track $j$'s last detection. Before
describing the tracks at $t$, the tracker drops every $j$ with

$$
\Delta t(t^{\text{obs}}_j, t) > T_r = 1.5\ \text{s}
$$

(`Tracker._retire`). That is three capture intervals: a track survives two
missed detections and dies on the third. A `GroundTruth` reading updates the
track's last update but not $t^{\text{obs}}$, so the label does not keep alive
a track the cameras no longer see.

### 11.2 The `WasteObject` record

For each surviving track, the record at $t$ holds (`Tracker._settle`):

- the propagated box $F(t)$, centered at $(p_x(t), p_y(t), h_a)$ from the
  filter, or from (1) when there is no filter;
- the material $\hat m = \operatorname{arg\,max}_k \pi_k$ and the confidence
  $\max_k\pi_k$;
- the validity

  $$
  t_{\text{valid}} = t + \frac{\max\left(0,\ x_{\text{exit}} - p_x(t)\right)}{v_b},
  $$

  where $x_{\text{exit}}$ is the downstream edge of the reachable window, found
  by sweeping the compiled model (`belt.window_exit`), with 1.034 m as the
  loop's fallback;
- the mass band $[\rho_{\min}V,\ \rho_{\max}V]$, with $V = L\,\ell\,\eta$ and the
  densities the world declares for the class; the band is absent when no object
  in the world has that class.

The record stores no grasp quantity of its own and derives them from the box:

$$
\mathbf{g} = \mathbf{c},\qquad
\chi = \psi + \frac{\pi}{2},\qquad
w_g = \ell,\qquad
\mathbf{n} = \mathbf{e}_z .
$$

The grasp point is the center, the closing axis is the minor axis, the opening
is the minor extent, and the normal is vertical because nothing on the line
measures a surface tilt.

## 12. The grasp pose

### 12.1 Construction from the record

The grasp pose (`markers.marker_for`) combines the record with the parameters of
the effector, a Robotiq 2F-85 whose dimensions were read off the compiled model
(`configs/world/sorting_line.yml`, block `effector`):

| Quantity | Symbol | Value |
| --- | --- | --- |
| Closing height above the belt | $h_g$ | 0.030 m |
| Flange to pinch point | $\ell_f$ | 0.1558 m |
| Pad thickness along the closing direction | $t_p$ | 0.008 m |
| Widest jaw opening | $w_{\max}$ | 0.085 m |

With the record $(\mathbf g = (x,y,\cdot),\ \chi,\ w_g,\ o)$:

$$
\mathbf{p}_{\text{pinch}} = (x,\ y,\ z_s + h_g) = (x,\ y,\ 0.930),
$$

$$
\mathbf{p}_{\text{flange}} = \mathbf{p}_{\text{pinch}} + \ell_f\,\mathbf{e}_z = (x,\ y,\ 1.0858),
$$

$$
\mathbf{p}_{\pm} = \mathbf{p}_{\text{pinch}} \pm \left(\frac{w_g}{2} + \frac{t_p}{2}\right)\left(\cos\chi,\ \sin\chi,\ 0\right)
\quad \text{(when } o\text{)},
$$

$$
\text{reachable} \iff w_g \le w_{\max} .
$$

The horizontal position, the closing axis and the opening come from pixels. The
height does not: no sensor on the line measures depth, and the closing plane is
a configured distance above the belt that does not depend on the object. An
unoriented object ($o$ false) gets no axis; its marker draws a ring of four
pads and the pose commands no tool rotation. The destination channel is the one
for class $\hat m$, or the reject channel when the class is outside the
taxonomy. The marker's velocity and yaw rate stay empty on this path, because
the record does not carry them.

### 12.2 The pose as an element of SE(3)

The tool is held pointing down, so the pose has four degrees of freedom:
position and a turn about $\mathbf{e}_z$. An equivalent matrix form for the
flange is

$$
T = \begin{pmatrix} R_z(\chi)\,R_x(\pi) & \mathbf{p}_{\text{flange}} \\ \mathbf{0}^\top & 1\end{pmatrix},
\qquad R_x(\pi) = \operatorname{diag}(1,-1,-1),
$$

where $R_x(\pi)$ turns the tool axis to $-\mathbf{e}_z$ and $R_z(\chi)$ lines the
pads' closing direction up with the object's minor axis. A parallel jaw is
symmetric under a half turn, so $\chi$ and $\chi+\pi$ describe the same grasp,
and the angle lives in $S^1/\pi$. The matrix states what the pose means; the
code does not build it, and carries the pair $(\mathbf p_{\text{flange}}, \chi)$
instead.

### 12.3 The alternative path: the pose from physics

With `--gt`, the pose comes from `ground_truth_markers`, which reads MuJoCo's
state every 50 ms. It differs from the vision pose in four ways:

- the point is the body's center of mass (`xipos`), not the center of a box in
  the image;
- the width and the closing axis come from a principal component analysis of
  the mesh vertices, rotated into the world and projected onto the plane: with
  the scatter $C = \sum_i \tilde{\mathbf q}_i\tilde{\mathbf q}_i^\top$ of the
  centered vertices, the minor eigenvector $\mathbf m$ gives
  $\chi = \operatorname{atan2}(m_y, m_x)$, and the width is
  $\max_i \tilde{\mathbf q}_i\cdot\mathbf m - \min_i \tilde{\mathbf q}_i\cdot\mathbf m$,
  the true extent rather than a second-moment equivalent;
- the closing plane follows the object,
  $z_g = \min\left(\max(z_c,\ z_s + z_{\text{floor}}),\ z_s + 0.150\right)$, with
  $z_c$ the height of the mesh's geometric center and $z_{\text{floor}}$ the
  smallest clearance of the open jaw;
- the linear velocity and the yaw rate $\omega_z$ come from the body's spatial
  velocity (`cvel`), and the validity uses the measured along-travel speed when
  it exceeds 0.01 m/s.

This path is the reference vision is measured against
([section 14](#14-measurements)), and it is the one the video command in
`AGENTS.md` uses.

## 13. From the record to the pose at the instant of the pick

### 13.1 Filtering and ordering

The selector (`control/selection.py`) only orders a marker that is reachable
($w_g \le w_{\max}$), whose validity has not lapsed ($t_{\text{valid}} > t$),
whose flange lies in the region the arm is trusted over, and that passes the
pickability condition. Among candidates the cost is

$$
J = \left\|\mathbf p_{\text{current flange}} - \mathbf a\right\| + w_e\,v_x\,(t_{\text{valid}} - t),
\qquad w_e = 1.0,
$$

where $\mathbf a$ is the candidate's anchor carried to the current instant and
$v_x$ is the measured along-travel velocity, or $v_b$ when none was measured.
The second term is the distance the object still travels before it leaves the
window, so an object about to leave outranks a nearer one.

### 13.2 Predicting the position

The pose is commanded for the instant $t_p$ at which the plan says the jaws
close, not for the capture instant. With $\tau = t_p - t$ and the marker's
velocity $\mathbf v$, or $(v_b, 0, 0)$ when it is missing as on the vision path
(`control/task.py`), the predicted position is (`trajectory.where_carried`)

$$
\mathbf p(t_p) = \mathbf p + \mathbf v \odot \left(\tau,\ \min(\tau, h_d),\ 0\right),
\qquad h_d = 0.30\ \text{s},
$$

with $\odot$ the elementwise product. The along-travel component is carried for
the whole interval, because the belt sustains it; the across component only for
$h_d$, because drift is a transient; the vertical one not at all.

### 13.3 Predicting the turn

When the marker has an axis $\chi$ and a rate $\omega$, the commanded turn is
(`Task._yaw_at_pick`)

$$
\chi(t_p) =
\begin{cases}
\operatorname{wrap}(\chi + \omega\tau), & |\omega\tau| \le \pi/4,\\
\chi, & \text{otherwise},
\end{cases}
\qquad \operatorname{wrap}(\alpha) = \left((\alpha+\pi) \bmod 2\pi\right) - \pi .
$$

The $\pi/4$ bound comes from the jaw's symmetry: $\chi$ and $\chi+\pi/2$ are the
two grasps furthest apart, so a predicted turn beyond $\pi/4$ is no better than
the measurement. On the vision path $\omega$ does not exist and
$\chi(t_p) = \chi$. Finally, of $\chi(t_p)$ and $\chi(t_p)+\pi$, the one nearer
the tool's current turn is chosen (`pick.nearer_parallel_yaw`), which spares the
wrist a half turn.

## 14. Measurements

### 14.1 Procedure

The measurements used the repository's code unmodified, in two stages, both
with the world `configs/world/sorting_line.yml`, a $640\times480$ render,
captures every 0.5 s from both detection cameras and $h_a = 0.95$ m, as in the
simulation loop. Four seeds (7, 11, 23 and 42) ran for 60 simulated seconds
each, at the belt speed the layout drew, without the feed controller, and with
the arm parked at its initial pose, without the control loop. The reference is
each body's center of mass (`xipos`), the same point the physics pose uses, and
only bodies resting on the belt, with $z_s - 0.05 < z \le z_s + 0.15$, are
counted.

1. **Adapter.** Each mask is converted on its own by `detections_from_masks`,
   and the geometry name the adapter discards is used by the evaluation only, to
   pair the detection with its body. The true width and axis come from the same
   vertex analysis as
   [section 12.3](#123-the-alternative-path-the-pose-from-physics).
2. **Tracker.** The `Tracker` runs as in the loop, with `SimulatorIdentity`, the
   fusion settings and the `GroundTruth` evidence. Each record is paired with
   its body through its track's internal label, which only the evaluation reads.

### 14.2 Adapter: from mask to box

Detection adapter error against the center of mass. There are 1353 detections,
1211 of them with the whole mask inside the frame.

| Quantity | Median | p90 | Max |
| --- | --- | --- | --- |
| Center error, whole mask (mm) | 4.0 | 14.5 | 23.5 |
| Center error, mask clipped by the frame edge (mm), 142 cases | 48.6 | 81.6 | 91.6 |
| Width $\ell$ minus true width (mm) | -1.7 | +6.6 | n/a |
| Closing axis error, oriented masks (degrees) | 1.4 | 4.5 | 41.4 |

Oriented masks: 1186 of 1211 (97.9 %). The tenth percentile of the width error
is -4.5 mm. The top height above the belt has a median of 0.060 m, a p10 of
0.030 m and a p90 of 0.068 m.

The center error grows with distance from the optical axis and points inward,
as (8) predicts. A linear fit of the radial error against distance gives
-26.8 mm/m with an intercept of +3.0 mm, against -18.9 mm/m for the prism model.
The tangential error has a median absolute value of 1.05 mm. The radial error by
distance from the axis of the camera that produced the detection, in 0.1 m
bins, with negative values pointing at the axis:

| Distance $d$ (m) | Median (mm) | p10 (mm) | p90 (mm) | Prism model (8) at the bin center, $D = 0.10$ m (mm) |
| --- | --- | --- | --- | --- |
| 0.0 to 0.1 | -0.9 | -2.8 | +1.2 | +0.5 |
| 0.1 to 0.2 | -3.2 | -5.7 | -0.2 | -1.4 |
| 0.2 to 0.3 | -2.3 | -7.5 | -0.7 | -3.3 |
| 0.3 to 0.4 | -3.6 | -10.7 | -2.7 | -5.2 |
| 0.4 to 0.5 | -10.4 | -16.4 | -3.9 | -7.1 |
| 0.5 to 0.6 | -13.5 | -19.6 | -7.9 | -9.0 |
| 0.6 to 0.7 | -15.8 | -22.0 | -9.0 | -10.8 |

Three readings follow from these tables.

- Geometry from an exact mask is off by a few millimeters near the axis. Away
  from it the error reaches 15 mm, dominated by the assumed height rather than
  by discretization.
- The width that sets the jaw opening is off by -4.5 to +6.6 mm between p10 and
  p90, the same order as the jaw's narrowest side clearance of 8.7 mm
  (`fusion.yml`).
- The closing axis is the most robust quantity in the pipeline, with a median of
  1.4° and a p90 of 4.5°. The maximum of 41.4° shows isolated large errors whose
  cause these measurements did not isolate.

### 14.3 Tracker: the record

Horizontal error of the `WasteObject` center against the center of mass, over
the same four seeds:

| Records | $n$ | Median (mm) | p90 (mm) |
| --- | --- | --- | --- |
| With a detection in their history | 1278 | 15.8 | 345 |
| of which detected in the same capture | 957 | 9.3 | 56 |
| of which not detected in the same capture | 321 | 179 | 479 |
| Opened by the label alone ([section 8.2](#82-the-rule)) | 37 | 107 | 342 |

Records updated by a detection in the same capture are off by 9.3 mm at the
median, a little more than the adapter, because the filter lags the observation
($\alpha<1$). The tail comes from records with no recent detection: inside the
cameras' coverage, $x\in[-1.25, 1.10]$ m, their medians run from 171 to 236 mm.
Those records exist only because another track took the object's detections,
which is the identity fragmentation of
[section 8.3](#83-the-dominant-failure-mode). Near the belt entry, where objects
drop and bounce, the median reaches 345 mm. The material class is right in
100 % of the records, at a confidence of 0.9945, for the reasons in
[section 10](#10-material-fusion).

## 15. Limitations

This section gathers what the earlier sections established, in order of effect
on the pose.

1. **Association.** Identity fragmentation produces records hundreds of
   millimeters off and is the largest source of pose error
   ([section 14.3](#143-tracker-the-record)).
2. **Height.** The object height is assumed rather than measured,
   $\eta = 0.05$ m for every object. That produces the radial bias of
   [section 14.2](#142-adapter-from-mask-to-box), down to -16 mm at the edge of
   coverage, and leaves the closing plane blind to the object ($z = 0.930$ m
   always). The mass band inherits the same constant.
3. **Clipped masks.** One detection in ten is clipped by the frame edge and is
   off by 48.6 mm at the median, and nothing flags it.
4. **Along-travel coverage.** Camera coverage in the simulator is that of the
   4:3 render rather than of the declared sensor
   ([section 3.2](#32-nadir-pinhole-projection)). With the real optics, the band
   from -0.54 to -0.08 m would have no camera.
5. **Material and identity.** The material is the simulator's label. The label
   decides which track receives the material, though not its position. A
   simulator position can reach a record undeclared through the path described
   in [section 8.2](#82-the-rule).
6. **Orientation.** The angle is not filtered and vision estimates no yaw rate.
   A jaw that closes half a second after the capture arrives at the last mask's
   angle even when the object has turned since.
7. **Center.** The center is that of the image-aligned box, which differs from
   the centroid for asymmetric shapes and carries the half-pixel bias (9) of
   about 1.1 mm.
8. **Segmentation.** Masks are exact because they come from the rasterizer. In a
   real system segmentation would be a model with an error of its own, added to
   everything above.

## 16. Reproducibility

The figures in sections 3 and 9 follow from the formulas and the configuration
cited, and can be recomputed by hand. Those in section 14 come from two
evaluation scripts that import `clave` without changing it and render with
`MUJOCO_GL=egl`. The scripts are not part of the repository; the procedure in
[section 14.1](#141-procedure) is enough to rebuild them. The reference pose and
the debug videos come from

```bash
clave sim --seconds 30 --gt --log-level DEBUG --no-progress --no-window --video --out runs/debug/<id>
```

and the same command without `--gt` makes the arm follow the vision poses.

## 17. Parameters

| Symbol | Value | Meaning | Source |
| --- | --- | --- | --- |
| $z_s$ | 0.90 m | belt surface | `world/sorting_line.yml` |
| $h_a$ | $z_s + 0.05$ m | assumed top height | `sim/debug_run.py` |
| $W\times H$ | $640\times480$ | render size | `sim/debug_run.py` |
| $T$ | 0.5 s | capture interval | `sim/debug_run.py` |
| $\rho$ | 1.15 | orientability threshold | `adapters/detection.py` |
| $N_{\text{sat}}$ | 400 px | confidence saturation | `adapters/detection.py` |
| $\gamma$ | 1.5 | gate, in multiples of $L_j$ | `association.py` |
| $\varepsilon_u$ | 0.085 m | extent of an unmeasured track | `arm.max_grasp_width` |
| $\alpha_x, \beta_x$ | 0.80, 0.05 | along-travel gains | `perception/fusion.yml` |
| $\alpha_y, \beta_y$ | 0.70, 0.20 | across-belt gains | `perception/fusion.yml` |
| $\epsilon$ | $5\times10^{-4}$ | posterior floor | `perception/fusion.yml` |
| $\tau$ | 2.0 s | evidence half life | `perception/fusion.yml` |
| $T_r$ | 1.5 s | retirement bound | `perception/fusion.yml` |
| $h_g$ | 0.030 m | closing plane | `world/sorting_line.yml` |
| $\ell_f$ | 0.1558 m | flange to pinch | `world/sorting_line.yml` |
| $t_p$ | 0.008 m | pad thickness | `world/sorting_line.yml` |
| $w_{\max}$ | 0.085 m | widest opening | `world/sorting_line.yml` |
| $w_e$ | 1.0 | exit weight in the ordering | `runtime/control.yml` |
| $h_d$ | 0.30 s | across-belt drift horizon | `runtime/control.yml` |

## 18. References

1. T. R. Benedict and G. W. Bordner. Synthesis of an optimal set of radar
   track-while-scan smoothing equations. *IRE Transactions on Automatic
   Control*, 7(4):27-32, 1962.
2. P. R. Kalata. The tracking index: a generalized parameter for alpha-beta and
   alpha-beta-gamma target trackers. *IEEE Transactions on Aerospace and
   Electronic Systems*, AES-20(2):174-182, 1984.
3. Y. Bar-Shalom, X. R. Li and T. Kirubarajan. *Estimation with Applications to
   Tracking and Navigation*. Wiley, 2001.
