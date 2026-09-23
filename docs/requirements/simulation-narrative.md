# Narrating a simulation

## Intent

A run that misbehaves currently leaves a report and a progress bar. The report
says how many visits were served and how far the jaw was from the belt, after
the arm has already finished. The bar redraws the terminal while that is
happening. Neither one says, at the moment it matters, why the arm chose an
object, how it intended to reach it, whether it closed on it, where it tried
to put it, or that something had already gone wrong.

This spec makes the task layer tell that story while the run is in progress,
and makes a small watch sit beside it for the failures the task layer cannot
see: the jaw touching the belt, a vertical acceleration the plan never asked
for, and a flange that is no longer where it was commanded. The story is a
debug log. A normal run is unchanged, and an operator who wants the story
turns the bar off so the two do not write over each other.

## Scope

**In.** The decisions the task machine already makes: which object, by which
plan, which phase of that plan, a re-aim whose choice changed, a miss, an
abandonment, a fault. The queue rebuilds that change who is next. The close,
the lift, and the place, which are the three moments a visit succeeds or
fails. A watch that opens one episode for jaw-to-belt contact, vertical
acceleration, tracking lag, and a servo refusal. The `--no-progress` flag on
`clave sim`.

**Out.** A second controller. The watch reports; it does not stop the arm,
change a gain, or refuse a pose. The runtime loop in `clave.runtime.loop`,
which does not run this task machine. Training logs. Anything at INFO: the
report printed at the end of a run stays the report.

## What is worth a line

A line exists because the arm's behavior changed, or because a watch episode
began. A condition that stays true is not a new event. A physics tick that
continues the same phase is not a new event. A capture that repeats the same
re-aim is not a new event. The narrative does not follow either loop. The
physics step is 2 ms and the capture is half a second; both are faster than
the decisions a person can read, and a line at either rate is noise.

| Event | Why it changes what the arm does | What the line has to say |
| --- | --- | --- |
| Queue rebuilt | The order of candidates changed, or it was rebuilt and did not | Why (`appeared`, `retired`, `anchor`), and whether the head changed. A head replaced while it is still waiting is the churn that sends the arm elsewhere |
| Queue has no head | Nothing is served | That no visit will start |
| Plan committed | The arm leaves park and flies a timed visit | The object, the material, the chute, the duration, and the phases in order, which is the manner of the visit |
| Reference-only track begins | The arm follows a marker at approach height | The object, and that this profile does not grasp |
| Flange outside the trusted region | The arm goes home instead of committing, and the object is not marked missed | That the recovery is the park pose, because a plan that starts outside the region is refused forever |
| No interception | The object is skipped | How much belt it had left, or that the grasp pose would put the jaw in the belt |
| Re-aim took | The approach arc is bent onto a fresher estimate. The arrival time stays | The drift, in millimetres. One line when this becomes the decision |
| Re-aim held | The plan is kept because the drift is inside the aim tolerance | The drift. One line when this becomes the decision. A later capture that holds again is the same decision |
| Re-aim solved | The visit is solved again from the fresh estimate | The drift and the new duration. One line when this becomes the decision |
| Visit abandoned | The plan is discarded and the object is missed | The reason already recorded on the visit |
| Phase becomes descend | The flange comes down onto the object, moving with the belt | That this is the descent |
| Phase becomes hold | The jaw is commanded shut | That the grasp instant has been reached |
| Close measured | The first tick of the hold is when a pick is decided | The gap from the pinch to the nearest object. Past the pinch-miss watch, or with nothing in reach, the close is a fail and the later delivery says so |
| Phase becomes retreat | The jaw lifts clear, still shut | That the hold is over |
| Phase becomes deliver | The arm carries across to a chute | The object, the material, and the chute. If the close already failed, the line says the release is being flown anyway |
| Visit ends | The plan has run out | The lift of the nearest object. Success only when that lift reaches the same 10 mm the report already uses for a held grasp |
| Place | An object's centre crossed a chute mouth | The body, the material, the chute. Success when the chute is the material's channel. Fail, naming both channels, when it is not |
| Servo fault | The task machine tears the plan up and holds | The refusal text |
| Reference-only visit completes | The dwell finished inside tolerance | The arrival gap. This profile's success is arriving, not grasping |
| Jaw touches the belt | The pads are in the belt. A grasp from there is not the one that was planned | The clearance, which is negative when the geometry is inside the belt |
| Vertical acceleration spike | A slip or a lurch. The plan's own acceleration is bounded at 2.50 m/s² | The sampled peak and the watch |
| Flange lags the command | The arm is not where this tick told it to be | The lag and the watch |
| Servo refuses a pose | The command was not written | The refusal text. This is the instant. The fault line above is the task machine's answer on the next capture |

A re-aim is one decision. The first time the machine takes the arc, holds
the plan, or solves the visit again, the narrative says so, and it says so
again when that choice changes or the object changes. The capture loop
repeats the same choice for as long as the approach lasts. The report
already keeps every one of those refreshes, drift included, so a drift that
grows is still on the visit. The narrative does not reprint it.

## The line

One logger, `clave.control.story`, one level, `DEBUG`. One event, one line.
The line is a sentence with a fixed skeleton, so a person can read it and a
test can grep it:

```
t=   1.250s because <cause>, I will <action>, chute <channel>: <outcome>
```

Rules:

- **Time is simulated time**, in seconds, three decimal places, width 8, so
  a column of lines lines up. It is not wall time.
- **The because clause is the cause.** It names the event and the number that
  made it matter: a drift, a gap, a clearance, a refusal.
- **The action is what the arm will do about it**, in the first person,
  starting at `I will`. Fetching an object says `to fetch` or `serve`.
  Putting one down says `put` and names the chute. A watch says `report`.
- **The object is `object <track id> (<material name>, <class id>)`.** The
  track id is the identity the task layer serves. Under the ground-truth
  feed that id is the spawn serial. The material is the taxonomy name and
  its id, from `clave.taxonomy`. An unknown class is the raw identifier. A
  missing one is `unknown material`.
- **The chute is the channel on the candidate**, appended as `, chute <id>`
  when one is known. A line with no chute omits the clause rather than
  inventing one.
- **The outcome is exactly `success`, `fail`, or `pending`**, last, after a
  colon. `pending` means the arm has committed and the result is not known
  yet. `success` and `fail` are verdicts. A watch is `fail`: the condition
  is a departure from the plan, and the log does not stop the arm.
- **Nothing is emitted above DEBUG.** Formatting is skipped unless the
  logger is enabled for DEBUG, so an INFO run pays nothing for the story.
  The warnings the task machine already emits for an abandonment and a fault
  stay warnings. They are the one-line notice an operator sees without
  asking for the story.
- **A watch is one episode, not one sample.** Contact, acceleration, and lag
  each report when the episode begins and stay silent while it holds. The
  episode ends only after the condition has stayed clear for the quiet
  interval, a tenth of a second. Acceleration and lag count as clear below
  half their watch. A sample between the watch and that floor does not end
  the episode and does not open a new one, and one sample under the floor
  does not end it either: the figure is read every physics step, and a
  second difference of flange height crosses 25 m/s² on a tenth of a
  millimetre of jitter. A refusal reports when its text changes. The same
  text is not repeated until the servo has accepted for the quiet interval.
- **The first acceleration sample is zero.** The figure is a second
  difference of flange height. Comparing the first rise with a seed of zero
  is not a spike the arm produced.
- **Numbers in the sentence are the unit a person reads** (millimetres, or
  m/s² written `m/s^2`). The watches themselves are SI, and they are named
  constants in `clave.control.story` rather than keys in the control
  configuration: they do not change a command, and a missing debug threshold
  must not fail a run at load.

### Watches

| Watch | Value | Why this value |
| --- | --- | --- |
| Pinch miss | 0.040 m | The jaw opens 0.085 m, so half of that is 0.0425 m. Forty millimetres is inside the opening and far past the 8.7 mm of side clearance the narrowest object leaves. An object there is not between the pads |
| Acceleration | 25 m/s², clear below 12.5 | The commanded ceiling is 2.50 m/s². The smallest slip lurch on record is 52.9 m/s² (`docs/measurements.md`). Twenty-five is an order above the command and about half the slip, so a planned move does not trip it and a slip does. The sample is a second difference at the physics step, not the planner's analytic acceleration. Clearing is the quiet interval below 12.5, not one sample |
| Tracking lag | 0.050 m, clear below 0.025 | After the lead term the settled error is 1.0 to 1.25 mm. The visits that lost the command fell 50 to 80 mm behind it. Fifty millimetres is that failure, not the arrival tolerance. Clearing is the quiet interval below 25 mm |
| Episode quiet | 0.10 s | The shipped physics step is 2 ms, so this is fifty steps. A belt contact on record has lasted one tick, and the acceleration sample reaches the watch on a tenth of a millimetre of jitter at that step. One quiet sample is that chatter. A tenth of a second is longer than those contacts and shorter than the half-second capture, so a later distinct event is still a line |
| Collision | jaw geom touching the belt geom | The same pair the report already counts as `belt_contacts`. The line adds the clearance |

The grasp verdict at the end of a visit uses the 10 mm lift already named
`GRASPED_METERS` in the debug run. This spec does not move that threshold.

## The progress bar

`clave sim` draws a tqdm bar over the physics steps. The bar and the log
share the terminal, and a bar that redraws a line erases the story. The
default stays a bar, because a long run with no debug output wants one.

`--no-progress` runs the same loop over a plain range. It does not change a
timestep, a capture, or a decision. The choice is recorded in the run's
metadata with the other parameters, so a filed run says whether a bar was
on.

## Acceptance criteria

Ids begin at `AC-STORY-01`. They are append-only and never reused.

`AC-STORY-01`: When the story logger is not enabled for DEBUG, the narrative
shall emit nothing.

`AC-STORY-02`: A narrative line shall carry simulated time, a because clause,
an action beginning `I will`, the object when one is known, the chute when
one is known, and an outcome token that is exactly `success`, `fail`, or
`pending`.

`AC-STORY-03`: The task machine shall narrate each decision that changes the
visit: committing a plan and naming its phases, beginning a motion-only
track, refusing an interception, abandoning a visit, re-aiming, a servo
fault, and each phase change of an active visit among descend, hold, retreat,
and deliver.

`AC-STORY-04`: The close shall name the gap from the pinch to the nearest
object. A gap past the pinch-miss watch, or no object in reach, shall be
`fail` and shall be remembered, so a later delivery of that visit says the
jaw closed on nothing. The end of a visit shall name the lift and shall be
`success` only when the lift reaches the grasp threshold the report uses.

`AC-STORY-05`: A place shall name the body, the material, and the chute. The
chute the material belongs in shall be `success`. Any other chute shall be
`fail` and shall name both channels.

`AC-STORY-06`: The watch shall report a jaw-to-belt contact, a vertical
acceleration above its watch, a flange lagging its command by more than its
watch, and a servo refusal. A condition that remains true shall be one line,
reported again only after it has cleared.

`AC-STORY-07`: `clave sim --no-progress` shall iterate the physics steps
without a tqdm bar. The bar shall remain the default.

`AC-STORY-08`: A known material class shall be named with its taxonomy name
and its id. An absent class shall be named `unknown material`.

`AC-STORY-09`: A queue rebuild shall narrate why it rebuilt and whether the
head changed, including a head replaced while it was still waiting and a
queue that came back empty.

`AC-STORY-10`: The narrative shall not emit a line because a physics tick or
a capture ran. A re-aim shall be a line only when its action or its object
differs from the previous re-aim of the visit; the visit shall still record
every refresh. A watch condition shall be reported again only after it has
stayed clear for the quiet interval, so a sample that crosses the threshold
at the physics rate is not a new line.

## Design notes

**Why a sentence and not a key-value record.** The failure this is for is a
person watching a run and not being able to say what the arm thought it was
doing. A record of fields is what the report and the telemetry already are.
The sentence is the order of the decision: cause, manner, object, chute,
verdict. The tokens are stable so a test can still find them.

**Why the task machine narrates and the debug run measures.** The machine
knows which decision it took. It does not know the jaw's clearance, the
lift, or which mouth an object crossed: those are read from the world, once
a tick, in the debug run. Splitting the lines the same way keeps the machine
testable without a simulator and keeps the measurements where the bodies are.

**Why the directory of materials is filled by the caller.** A candidate
carries a channel and not a material class, and under the tracker the track
id is minted rather than copied from the spawn serial. Noting both into one
map would attach one object's material to the other's id, since both series
start at 1. The ground-truth feed notes serials. The tracker feed notes
track ids. The place line reads the material off the body that crossed,
which does not go through that map.

**Why the watch does not stop the arm.** Stopping is the safety layer's
decision, and it already refuses a pose outside the region. A debug line
that also commanded a stop would be a second policy, silent at INFO and
active at DEBUG, which is the opposite of a watch.
