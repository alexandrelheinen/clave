# Detection-camera video

## Intent

A debug run's playable file is the free camera over the line. The detection
camera, which is what the tracker actually segments, is only drawn as a small
inset when a live window is open, and that inset has no boxes. An operator
who wants to see which objects the gate camera covered has to open a window.
This adds a second file of that camera, with a box on each object the
segmentation covered, asked for on its own because the render is expensive.

## Scope

**In.** A `--camera-video` flag on `clave sim`. When it is set, the run writes
`camera-debug.mp4` of the primary detection camera, at the same size the
tracker segments (`render`), with an axis-aligned box per object present in a
segmentation of that same frame. The report names the file. The flag is off
unless set, and a run that does not set it constructs no extra camera renderer.

**Out.** A box painted on the free camera's own pixels. A box on the
live-window inset. Caching decoded frames or holding more than one archive.
Changing capture cadence, tracker decisions, or what the arm does.

## Acceptance criteria

Ids begin at `AC-CAM-01`. Append-only.

`AC-CAM-01`: When `clave sim` is invoked without `--camera-video`, the flag
is off, the run writes no `camera-debug.mp4`, and it constructs no detection
camera renderer for that file. When `--camera-video` is set and an encoder is
installed, the run writes `camera-debug.mp4` beside the other artifacts.

`AC-CAM-02`: When a camera video was written, the report names its path. When
none was written, the report does not.

`AC-CAM-03`: A box is the inclusive pixel bounds of that object's segmentation
runs on the same frame. Pixels on the border take the overlay colour. Pixels
outside the box stay as the camera rendered them. An object absent from the
segmentation has no box.

`AC-CAM-04`: When `clave sim` is invoked with both `--video` and
`--camera-video`, the free-camera file shall include every detection
camera's frame, each with the boxes `AC-CAM-03` draws, so a reader of that
one file sees the cameras. The separate `camera-debug.mp4` of the primary
detection camera is unchanged. Without `--camera-video` the free-camera
file is the free camera alone, and no detection-camera renderer is built.

`AC-CAM-05`: Each detection view pasted into the free-camera file shall be
at least the configured inset width, so a box around an object is a
rectangle a reader can see, not a mark a few pixels across. The free-camera
image itself is not covered to make room.

`AC-CAM-06`: Those views shall be stacked vertically along the right edge,
in the order the cameras are listed, the first on top. The frame grows to
the right, and downward when the stack is taller than the free camera, so
the arm, the pick zone, and the placing bins stay in the free-camera image.

## Constraints

The colour frame and the segmentation are separate renders of one camera at
one size, at the video cadence, and only when the flag is set. A machine
without `ffmpeg` still finishes the run and records that no file was written.
Odd frame sizes are the caller's `render` tuple; the default `(640, 480)` is
even, which is what the encoder's chroma format expects.

## Design notes

The file is encoded with `StreamSettings`, because the pixels already exist.
Boxes are painted in RGB before the encoder sees the frame. Bounds come from
the same run-length masks `segment_masks` already returns for the tracker, so
a box is the object's pixels and not a projection of its pose. The views
used to sit in a band under the free camera, and that band covered the
placing bins. They now stand in a column on the right (`AC-CAM-06`).
