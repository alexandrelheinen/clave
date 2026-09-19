# Provenance

This directory is a verbatim copy of `robotiq_2f85` from Google DeepMind's
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie), at
commit `8161bba264d7fa7c99ca301e91e7fb44737676ad`.

That is the same commit `third_party/mujoco_menagerie_ur10e` was taken at, so
the arm and the gripper on it come from one pin rather than two.

Nothing here is authored by CLAVE. The upstream `README.md` records the URDF
to MJCF derivation from the ROS-Industrial `robotiq_2f_85_gripper_visualization`
package, and `LICENSE` is the model's own. `LICENSE.menagerie` is the
collection's licence.

## Why a copy rather than a submodule

The same reason the arm is a copy, recorded in that directory's own
`PROVENANCE.md` and in `docs/decisions.md` as `D-14`. Menagerie is one
repository holding 72 models and 2.3 GB; this is 4.2 MB of it. CI checks out
submodules recursively on every run, so pinning the collection to obtain
0.2 percent of it would move 2.3 GB per job. The files are ASCII OBJ rather
than binaries.

## Why this model and not a suction cup

Settled in
[docs/research/sorting-outputs-and-effectors.md](../../docs/research/sorting-outputs-and-effectors.md)
against what a municipal packaging line would actually install, which is
suction. Menagerie carries no suction model and MuJoCo has no vacuum
primitive, so a suction pick would be a weld appearing when the tool is near
enough: that proves the plumbing runs and says nothing about whether a grasp
would hold. A jaw closing is contact physics the solver works out.

## Updating

Re-copy the directory from the upstream commit you want, update the hash
above, and re-measure the flange to pinch offset and the jaw stroke recorded
in `docs/measurements.md`. Both are read from the compiled model rather than
from this file, so a re-copy that moves them shows up as a failing test
rather than as silent drift.
