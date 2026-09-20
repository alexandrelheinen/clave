# Carrying an estimate between observations

## Intent

Stop the tracker asserting that objects do not drift. It carried a position
and nothing else: a detection replaced it outright, and between detections
the estimate was moved along the belt at the configured belt speed, in the
travel axis only. That model makes two claims, that every object travels at
exactly the belt's speed and that lateral drift is exactly zero, and only
the first is nearly true.

The second is what a pick inherits. Measured on the shipped line, an object
rolling or settling drifts sideways by a mean of 10 mm over half a second
and 41 mm over 2.5 seconds, against a jaw whose narrowest side clearance is
8.7 mm. Downstream of the sensing gate nothing observes it again, so the
drift accumulates unopposed into the pose the arm is sent to.

## Scope

**In.** A velocity estimated per object from successive observations, and a
propagation that uses it. Gains that are configuration and that differ per
axis. A position blended with the observation rather than replaced by it.
A bound on how long a track may go unobserved before it is dropped.

**Out.** Anything that needs an observation the line does not take. This
recovers more from the observations already available; it does not create
new ones, and
[measurements.md](../measurements.md#what-a-velocity-estimate-recovers)
records how little that turns out to be worth. Also out: a full covariance,
cross-axis coupling, and any model of the drift's decay.

## Why an alpha-beta filter

It is the steady-state Kalman filter for a constant-velocity model, written
as two gains per axis instead of a covariance to propagate. `alpha` is the
fraction of the residual applied to the position and `beta` the fraction
applied to the velocity.

Choosing it over a general Kalman filter costs nothing here. There is no
cross-axis coupling to represent, the measurement noise is stationary, and
the steady-state gains are what a Kalman filter converges to anyway. What
it buys is that each tunable is a number between zero and one whose meaning
a reader holds without reading a matrix, and that the model it replaced is
a setting of this one rather than a different object: at `alpha` one and
`beta` zero, this filter replaces the position outright and never learns a
velocity, which is exactly the old behaviour.

## Why the axes are tuned apart

The belt drives travel rigidly and drives nothing across. So the travel
velocity is known from configuration before any observation arrives and the
filter should barely move it, while the lateral velocity has to be learned
entirely from successive observations.

This is measured rather than argued. Letting the filter learn the travel
velocity took the pick-zone median from 45.6 mm to 81.4 mm, because the
residual it learns from on that axis is the segmentation's noise rather than
the object's motion.

The travel gain is small rather than zero, because the feed controller moves
the belt and a velocity frozen at whatever the speed was when the track
opened goes stale.

## Constraints

- **Every gain is configuration**, and a gain outside zero to one fails at
  load: above one it corrects past the observation, below zero it corrects
  away from it.
- **The filter models where an object is going, not what it is.** Extents,
  yaw, height and class come from the observation exactly as before. Only
  the centre is filtered.
- **A track with no detection yet has no estimate**, and falls back to the
  belt model. `GroundTruth` opens a track without opening an estimate,
  because a runtime configured for hardware never sees one.
- **The propagation stays a pure function of the estimate and an instant**,
  so a consumer asking where an object will be at the pick gets the same
  answer whoever asks.

## Acceptance criteria

Ids continue from `learned-tracker.md` at `AC-TRACK-30`. They are
append-only and never reused.

`AC-TRACK-30`: The system shall read a position gain and a velocity gain per
axis from configuration, and shall fail at load when either is absent or
outside zero to one.

`AC-TRACK-31`: The system shall open an estimate on an object's first
detection with the belt's speed along travel and no velocity across it,
because the belt drives one axis and nothing drives the other.

`AC-TRACK-32`: The system shall estimate a lateral velocity from successive
observations, and shall carry an object between observations with the
velocity it estimated rather than the velocity the belt was configured
with.

`AC-TRACK-33`: The system shall move its position estimate less than the
whole way to a single observation, so one bad reading does not become the
estimate.

`AC-TRACK-34`: When two observations arrive at one instant, the system
shall fold the later one at position only, because a velocity correction
divides by the elapsed time.

`AC-TRACK-35`: The system shall leave an observation's extents, yaw, height
and class untouched, filtering only where the object is.

`AC-TRACK-36`: The system shall drop a track that has gone unobserved for
longer than a configured bound, rather than carry its estimate forward, and
shall report how many it dropped.

`AC-TRACK-37`: The system shall read that bound from configuration and fail
at load when it is absent or not above zero.

`AC-TRACK-38`: The system shall drop a segmented mask whose projected
extent is not positive, rather than build a footprint from it, because a
detection of no size is not a detection and refusing to build one ended
the run.

## Why an unobserved track is dropped rather than carried

A propagation is only as good as how recently it was corrected, and nothing
in a record says how old the estimate behind it is. Carried forward without
a bound, a track is dead reckoned for as long as the run lasts: measured
over two minutes before the bound existed, records sitting past the arm's
reach had a median error of 10.2 m and outnumbered the ones inside the
sensing gate nineteen to one. The arm chose its next object from among
them.

Dropping also clears the association gate, which is the less obvious half.
A detection carries no identity and joins the nearest track inside a gate
scaled to that track's own footprint. A stale track sits where nothing is,
so a fresh observation of the real object fails to join it and opens a
duplicate instead. That is why adding cameras over the pick zone made
things worse before this landed, and it is why the two changes belong
together.

## Design notes

**What this does not fix, stated before it was measured and confirmed
after.** The drift the filter learns is a constant velocity and the drift it
learns from is not: increments measured over growing horizons fall away,
because an object that is rolling is also settling. An estimate fitted
inside the gate and extrapolated two seconds past it therefore
over-predicts. Sweeping the lateral gain from 0.1 to 0.8 recovers four
millimetres of a forty-five millimetre median and is flat across that whole
range, which is what a model recovering all it can recover looks like. The
tail gets slightly worse, 123 mm to 131 mm at the ninetieth percentile,
which is the price of extrapolating a decaying drift as though it were
constant.

Four millimetres is worth having and is not a fix. What the measurement
settles is that the remaining error is not the filter's to remove: it is
information the line never collected, because the only detection camera
stands at the belt entrance and the arm works one to two metres downstream.
