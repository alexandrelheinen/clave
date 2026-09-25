# Training memory budget

Status: draft

## Intent

A proof-of-concept training run has to finish on the development machine.
That machine's virtual machine is capped at 7806 MB, and a full-resolution
batch killed the process three times. The training step keeps a resident
budget of 1 GiB so the run stops itself instead of taking the machine down.

## Scope

**In scope:**

- A configured resident-memory ceiling and a configured classifier and
  detector input side.
- Resizing each training and validation image to that side. Detector boxes
  scale with the image.
- Stopping a training run when the resident set exceeds the ceiling.
- Recording the side on the checkpoint so validation resizes the same way.

**Out of scope:**

- Re-recording the corpus. The archives stay at the camera resolution.
- Raising the virtual machine's memory cap.
- Matching the accuracy of a full-resolution batch.

## Acceptance criteria

`AC-MEM-01`: When a training batch is built, the system shall resize each
image to `input_side_pixels` from the memory configuration.

`AC-MEM-02`: When a detection batch is resized, the system shall scale each
box by the same width and height factors as the image.

`AC-MEM-03`: When the process resident set exceeds
`resident_limit_bytes`, the system shall stop the training run before the
next batch.

`AC-MEM-04`: When a checkpoint is written, the system shall store
`input_side_pixels` in it. When that checkpoint is scored, the system shall
resize validation images to the stored side.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-MEM-01` | `test_ac_mem_01_a_batch_is_resized_to_the_configured_side` |
| `AC-MEM-02` | `test_ac_mem_02_boxes_scale_with_the_image` |
| `AC-MEM-03` | `test_ac_mem_03_a_run_stops_when_resident_memory_exceeds_the_budget` |
| `AC-MEM-04` | `test_ac_mem_04_a_checkpoint_records_the_input_side` |

## Constraints

The numbers live in `configs/training/memory.yml`. One gibibyte is
`1073741824` bytes. The proof-of-concept side is 224 pixels, the input
ResNet-50 was built for.

## Follow-up

Raise `resident_limit_bytes` and `input_side_pixels`, and the batch sizes in
the training files, when a machine can hold a full-resolution batch. Until
then this budget is the proof of concept. The published corpus does not
change.
