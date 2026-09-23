"""Moving the arm to the poses the tracker points at.

Five modules, split where the decisions differ. `selection` orders the
markers into a queue, `task` runs the phases of one visit, `guidance` bounds
the path between two poses, and `servo` turns a commanded pose into joint
angles. Only the first three make decisions; the servo compiles a model.
`story` narrates those decisions at debug level and decides nothing.

Nothing here grasps. No gripper exists, so what is delivered is the motion and
the evidence that the motion reached the pose it was given.
"""
