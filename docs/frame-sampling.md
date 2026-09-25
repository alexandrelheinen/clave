# Sampling frames along the belt

Consecutive captures of a nadir camera are the same objects a fraction of a
second later. Training on every frame spends an epoch learning that
repetition. The corpus stays as recorded. A training run names a sample: a
list of frame indexes, drawn from the belt speed and the camera's footprint
along travel, and stored under its own digest.

The only quantity a designer chooses is how many looks to keep while an
object crosses that footprint. Everything else is already on the archive or
on the camera.

## The footprint is along travel

The cameras look straight down, so the belt footprint of a field angle is

```text
L = 2 H tan(theta / 2)
```

`H` is the standoff from the lens to the belt plane, and `theta` is the full
field angle of the image axis being measured. That identity is right. Two
substitutions are not.

`H` is not the camera's z coordinate. `gate_wide` stands at z = 1.942 m and
the belt surface is at 0.90 m, so the standoff is 1.042 m.

`theta` is not `fovy`. On this line the long sensor axis lies across the
belt, and `fovy` is that across-belt angle. The angle that decides how long
an object stays in frame is the shorter image axis, along travel.
[measurements.md](measurements.md) already records it: `gate_wide` covers
0.920 m along travel and 1.100 m across. `pick_wide` uses the same sensor,
the same lens, and the same standoff, so it covers the same 0.920 m. Using
`fovy` in the formula returns the width, 1.100 m, and the dwell comes out
too long.

The sample therefore reads the along-travel extent of the camera the loader
uses. It does not take a field angle from the training file.

## How many frames that extent is worth

An object crosses the footprint in

```text
T = L / V
```

seconds, where `V` is the belt speed stored on that rollout. The corpus
captures every `dt` seconds (`capture_interval_seconds` in
[configs/data/corpus.yml](../configs/data/corpus.yml), 0.2 s). The number of
frames in one crossing is

```text
K = T / dt = L / (V * dt)
```

`K` is a real number. It changes with the rollout, because the corpus grid
uses three belt speeds and one spacing does not appear in this formula.
Spacing changes how many objects share a frame. It does not change how fast
the picture scrolls.

Let `N` be the number of looks to keep per crossing. The stride, in frames,
is

```text
M = floor(K / N)
```

A stride of `M` keeps about `N` frames each time the belt moves one
footprint. The formula that multiplies `N` by `T / dt` does the opposite: it
skips `N` times as many frames as the crossing contains, and the run keeps
almost nothing.

When `K <= N`, `floor` returns 0. A stride of 0 is not a sample. The run
keeps every frame of that rollout. That is the case `N` greater than
`T / dt`: more looks were asked for than the camera took.

For `gate_wide` at `L = 0.920` m and `dt = 0.2` s:

| Belt speed | Frames in one crossing `K` | Stride at `N = 3` | Stride at `N = 5` |
| --- | ---: | ---: | ---: |
| 0.25 m/s | 18.4 | 6 | 3 |
| 0.30 m/s | 15.3 | 5 | 3 |
| 0.35 m/s | 13.1 | 4 | 2 |

A faster belt replaces the scene sooner, so the stride gets shorter and a
larger share of the frames remains. That is the direction the dwell asks
for.

The training half has 72 rollouts of 150 frames, 24 at each speed. A stride
with phase 0 keeps 2232 frames when `N = 3` and 4200 when `N = 5`.

## Time on the development machine

One epoch over all 10800 frames, one frame per step, takes 61 minutes. That
is the mean of two measured epochs, 3673 s and 3635 s, at 0.34 s per frame.
The minute between archives was that step. Opening the archive was a few
seconds of it, so a thinner index scales with the frames kept.

| Looks per crossing | Frames kept | One epoch | Ten epochs |
| --- | ---: | ---: | ---: |
| every frame | 10800 | 61 min | 10.2 h |
| `N = 5` | 4200 | 24 min | 3.9 h |
| `N = 3` | 2232 | 13 min | 2.1 h |

`N = 3` removes about 8 hours from the ten epochs. `N = 5` removes about 6.
Scoring every frame of the validation half once, after training, adds 15
minutes. That pass is a quarter of one full epoch and does not restore the
ten hours.

`N = 3` is the setting that makes a proof-of-concept epoch short enough to
wait for. `N = 5` keeps a closer look at each crossing and leaves the epoch
at about 24 minutes. The value lives in the training configuration. It is the
only free parameter of the sampler.

A point on the belt is the right object for this count. A bottle has length,
so that one bottle is visible for slightly longer than `T`. The picture as a
whole is new after the belt has moved `L`, which is the quantity above. Extra
length would add frames, and the thin sample would get thicker. Leaving it
out keeps the rule to numbers the archive and the camera already have.

## The draw is an index, and the index is stored

Inside one rollout the indexes are

```text
phase, phase + M, phase + 2M, ...
```

while they fall inside the frame count. `phase` is an integer from `0` to
`M - 1`, drawn once per rollout from the sample seed. Without that draw every
kept frame sits at the same position in the gate, and the model can learn the
phase instead of the object. The draw is what makes the subset a sample of
the crossing.

The indexes are the training set. They are written as a manifest, one list
per archive, naming the dataset digest, the camera, `N`, the seed, the
along-travel extent, and `dt`. The manifest is hashed and uploaded as an
object. D1 gains a row for that digest: which dataset it samples, which
camera, which `N`, which seed, and how many frames it kept. The pixels stay
where the corpus put them. A second copy of the images would say the same
thing as the index and would cost another upload.

A training run records the sample digest beside the dataset digest. Two runs
that share a corpus and differ in `N`, in the seed, or in the sampler, do
not share a sample digest, so a checkpoint cannot be mistaken for one trained
on a different pick. Recomputing the indexes from `N` at the start of each
run would hide a later edit to the sampler inside an old result. The stored
list is the pick that run used.

Train and validation each have their own manifest. They already have
different rollouts. They also get different phases, so the two picks are not
the same rule applied in lockstep. `clave train` keeps refusing a manifest
whose dataset is the validation half.

The order of an epoch is a separate permutation of that fixed list, from the
training seed. The permutation changes every epoch and is not uploaded. The
set of frames does not change, and the set is the artifact.

## What the score still sees

The manifest used to select a checkpoint can be the thinned validation
pick, and that pick is stored too. The score that is published against the
gates is computed on every frame of the validation half. That half is a
quarter of the training half, so reading it once is cheap beside ten thinned
epochs, and a gate measured on a thinned pick would move whenever `N`
moved. The published row names both digests: the sample the weights saw, and
the full validation half the score was computed on.
