# Feeding the line at a rate the arm can hold

## Intent

Make throughput a quantity the line sets rather than one it happens to
have. Today objects appear every `interval_seconds` drawn from `[0.8, 2.5]`,
belt speed is drawn once from `[0.25, 0.35]` and never moves again, and the
two are unrelated: nothing states how many objects per second the line is
supposed to carry, and nothing reacts when the arm cannot keep up.

This spec gives the line a feed rate in objects per second, a way to measure
what it is actually achieving, and a controller that trims belt speed to
hold one against the other.

## Scope

**In.** Feeding by distance along the belt rather than by elapsed time. A
configured rate setpoint. A measurement of the rate the line is achieving.
A proportional-integral controller from the error to belt speed, with the
speed bounded. The rate, the setpoint and the commanded speed reported per
run.

**Out.** Estimating the rate from perception, which would make the loop
depend on the tracker whose estimate
[measurements.md](../measurements.md#why-the-jaw-still-holds-nothing)
records as unusable downstream of the gate. The counter here reads the
simulator, and says so. Also out: varying the feed by material class,
modelling a hopper or a metering screw, and any claim that a particular
rate is what a real facility runs.

## Why belt speed can only regulate a rate if the feed is by distance

The reason the feed model changes at all, and it is arithmetic rather than
preference.

With objects released every `T` seconds, the arrival rate is `1/T` whatever
the belt does. Speeding the belt up spreads the same objects over more
metres; slowing it down packs them closer. The rate never moves, so a
controller with belt speed as its only actuator has no authority over the
quantity it is asked to regulate.

With objects released every `s` metres of belt travel, which is what a
metering feeder does on a real line, the arrival rate is

$$r = \frac{v}{s}$$

and belt speed is the throughput knob directly. That is the model this spec
adopts: `spawn.interval_seconds` is replaced by `spawn.spacing_meters`.

The controller is then not trivial, because `s` is drawn per object from a
range rather than fixed. The realised rate wanders around `v/\bar{s}`, and
the loop trims `v` to hold the measured rate at setpoint.

## Where the setpoint comes from

From what the arm sustains, measured, not from a number chosen because it
sounds like a sorting line. A visit costs the interception, the descent, the
dwell and the retreat, and the arm returns toward park between visits, so
the achievable rate is one over that cycle. The measurement is taken with
the shipped geometry and recorded in
[measurements.md](../measurements.md), and the configured setpoint cites it.

A setpoint above what the arm holds is not an error and is not clamped: a
line fed faster than it can be picked is an ordinary condition, and what it
produces is objects reaching the end unpicked, which the report already
counts separately.

## Constraints

- **Belt speed stays inside its configured range.** The existing
  `speed_meters_per_second` pair becomes the controller's saturation limits
  rather than a distribution to draw one value from. A controller that can
  stop the belt, or run it past what the drive does, is modelling a machine
  nobody built.
- **The integral term does not wind up against saturation.** A line fed
  slower than the setpoint sits on the upper limit for as long as that
  lasts, and an integrator that keeps accumulating there overshoots when
  the condition clears.
- **The measured rate is a rate, not a count.** It is counted over a window
  long enough to contain several objects, because a rate estimated from the
  gap between two arrivals is dominated by the randomness of the spacing.
- **The controller reads the simulator and says so.** Counting arrivals is
  ground truth, and a runtime configured for hardware must not silently get
  a loop that depends on it.
- **Belt speed is still randomised per run.** The starting speed is drawn
  from the range as it is today, so a rollout does not begin from the same
  operating point every time.

## Acceptance criteria

Ids begin at `AC-RATE-01`. They are append-only and never reused.

`AC-RATE-01`: The system shall release objects at a spacing drawn from a
configured range of metres of belt travel, and shall fail at load when that
range is absent.

`AC-RATE-02`: The system shall read a feed rate setpoint in objects per
second from configuration, and shall fail at load when it is absent or not
above zero.

`AC-RATE-03`: The system shall measure the rate at which objects enter the
line, over a configured window, and shall report it.

`AC-RATE-04`: The system shall command belt speed from the error between
the setpoint and the measured rate, through a proportional term and an
integral term whose gains are configuration.

`AC-RATE-05`: The system shall hold the commanded belt speed inside the
configured range at all times.

`AC-RATE-06`: When the commanded speed is saturated, the system shall stop
accumulating integral error in the direction that would drive it further
into saturation.

`AC-RATE-07`: When the setpoint is reachable inside the speed range, the
system shall settle the measured rate onto it, proved by a test that starts
the line off setpoint and reads the error after it settles.

`AC-RATE-08`: When the setpoint is above what the speed range can deliver,
the system shall run at the upper limit and report the shortfall rather
than fail.

`AC-RATE-09`: The system shall report the setpoint, the measured rate and
the commanded speed for every run, so a reader can tell a line that held
its rate from one that saturated.

`AC-RATE-10`: The system shall derive no part of the loop from perception,
and a test shall prove the counter reads the simulator rather than the
tracker.

`AC-RATE-11`: The system shall leave an object's rotation to physics while it
rides the belt, and a test shall prove the driven constraint does not pin it:
taking the spin about the belt normal out was measured and made the line worse,
because pinning a body's rotation while the belt drags it turns the contact
into a reaction that tips the parcel over.

## Design notes

**Why proportional-integral and not proportional alone.** A proportional
controller against a rate leaves steady-state error, because holding the
rate at setpoint needs a non-zero speed and a proportional term produces
output only from error. The integral term is what lets the loop sit on the
setpoint with the error at zero. Derivative earns nothing here: the measured
rate is already a windowed average, so it carries the noise a derivative
term would amplify and none of the lead it would buy.

**Why the window is a count and not a filter.** A first-order filter on the
inter-arrival time would be smaller code and would make the loop's dynamics
depend on two time constants that interact, the filter's and the
integrator's. Counting arrivals over a fixed window gives a delay that is
stated rather than emergent.

**What this does not fix.** Nothing here makes the arm pick better. A line
fed at a rate the arm can hold still misses every object whose pose is
wrong, which is the open defect in [roadmap.md](../roadmap.md). What it
does is stop the feed rate from being an accident, so that when the pick
works the throughput figure means something.
