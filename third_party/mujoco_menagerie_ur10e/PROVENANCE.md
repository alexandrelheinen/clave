# Provenance

This directory is a verbatim copy of `universal_robots_ur10e` from Google
DeepMind's [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie),
at commit `8161bba264d7fa7c99ca301e91e7fb44737676ad`.

Nothing here is authored by CLAVE. The upstream `README.md` records the
URDF to MJCF derivation, and `LICENSE` is the model's own, BSD-3-Clause.
`LICENSE.menagerie` is the collection's licence. The meshes descend from
Universal Robots' published CAD through the ROS-Industrial description.

## Why a copy rather than a submodule

Every other third-party asset in CLAVE arrives through a pinned submodule, which
is the house rule. This one does not, for a reason worth recording rather than
hiding.

Menagerie is a single repository holding 72 models and 2.3 GB. CLAVE uses one of
them, 35 MB. CI checks out submodules recursively on every run, so pinning the
collection would move 2.3 GB per job to obtain 1.5 percent of it. The files are
ASCII OBJ rather than binaries, so committing them costs a one-time 35 MB in
history and nothing per clone beyond that.

The trade is recorded in `docs/decisions.md` as `D-14` and in the documented
deviations section of `CONTRIBUTING.md`.

## Updating

Re-copy the directory from the upstream commit you want, update the hash above
and the entry in `docs/decisions.md`, and re-run the workspace sweep in
`docs/measurements.md`, because a geometry change invalidates every reach number
this project has measured.
