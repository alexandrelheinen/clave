# Implementation Plan

No task carries `(P)`. Decoding is a prerequisite for publishing, and publishing
is a prerequisite for the report.

- [x] 1. Decode a published decision

- [x] 1.1 Read the contract's CBOR into plain data
  - Carry the object identity, the material class, the confidence, the channel,
    the pick point, the yaw and the window, refusing a contract version the
    decoder does not know before reading any field past it.
  - Report undecodable bytes to the caller rather than raising out of a loop.
  - Write the failing tests first.
  - Observable: a golden vector from the contract decodes into every documented
    field, and a vector with a changed version is refused by version.
  - _Requirements: 1.4, 2.1_
  - _Boundary: clave.ros.decisions_

- [x] 2. Publish it

- [x] 2.1 Give the runtime a sink for published bytes
  - The bridge already drains the socket the Rust side publishes onto; hand each
    datagram to an optional consumer without changing what it counts.
  - Observable: a stub sink receives one payload per published decision and the
    decision count is unchanged.
  - _Requirements: 1.1, 1.2_
  - _Boundary: clave.runtime.bridge_

- [x] 2.2 Build and publish the message
  - One `vision_msgs/Detection3DArray` per decision on `/clave/pick_decisions`,
    with the class and the channel as two hypotheses and the frame named from
    configuration. Import ROS lazily so the module loads without it.
  - Observable: a subscriber on a real ROS 2 graph receives the documented
    fields; the test skips where ROS is absent.
  - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Boundary: clave.ros.publisher_
  - _Depends: 1.1, 2.1_

- [x] 2.3 Degrade without ROS
  - `clave run-sitl --ros` on a machine with no ROS installation runs the loop
    and reports that nothing was published.
  - Observable: the run completes, the report names the missing dependency, and
    the exit status is zero.
  - _Requirements: 1.3_
  - _Boundary: clave.runtime.loop_
  - _Depends: 2.2_

- [x] 3. Document and report

- [x] 3.1 Write the consumer contract
  - Topic, message type, quality of service, frame, units and the meaning of
    every field, beside the CDDL it extends.
  - Observable: a reader can implement a subscriber without opening a source
    file, including the two documented reuses of a field.
  - _Requirements: 1.5, 2.2, 2.3, 2.4_
  - _Boundary: documentation_

- [x] 3.2 Write the report
  - State what was proven, that FRET has no subscriber yet, and that no arm
    moved.
  - Observable: a reader can tell what this step demonstrates and what it does
    not.
  - _Requirements: none directly; closes the step_
  - _Depends: 2.3, 3.1_
