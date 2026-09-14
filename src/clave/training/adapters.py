"""Turning a dataset into batches, per training stage.

Reading happens through the dataset module, which owns the archive format, and
always from the training split alone. Reading validation or test here would be
invisible in any later number.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.candidates.fixture import STATE_DIMENSION
from clave.data.dataset import load_split
from clave.data.examples import Example, Rollout
from clave.data.expert import decide
from clave.taxonomy import MATERIAL_CLASSES

CLASS_INDEX = {entry.id: index for index, entry in enumerate(MATERIAL_CLASSES)}

TRAIN_SPLIT = "train"


def training_examples(dataset: Path) -> tuple[Example, ...]:
    """Load every example in the training split.

    The dataset's digest is verified before anything is read, so training can
    never consume a dataset whose contents changed since it was described.

    Args:
        dataset: The dataset directory.

    Returns:
        Examples from the training split only.
    """
    rollouts: tuple[Rollout, ...] = load_split(dataset, TRAIN_SPLIT)
    return tuple(example for rollout in rollouts for example in rollout.examples)


def _as_chw(frame: NDArray[np.uint8]) -> NDArray[np.float32]:
    """Convert a height-width-channel frame to channel-first float in [0, 1]."""
    converted: NDArray[np.float32] = np.transpose(
        frame.astype(np.float32) / 255.0, (2, 0, 1)
    )
    return converted


def classification_batches(
    examples: tuple[Example, ...], batch_size: int
) -> Iterator[tuple[Any, Any]]:
    """Yield image batches with multi-label presence targets.

    A frame holds several objects, so a single-label target would be ill posed.
    The target is a multi-hot vector over the taxonomy classes.

    Args:
        examples: Training examples.
        batch_size: Examples per batch.

    Yields:
        Image tensor and target tensor pairs.
    """
    import torch

    for start in range(0, len(examples), batch_size):
        chunk = examples[start : start + batch_size]
        images = torch.from_numpy(np.stack([_as_chw(item.frame) for item in chunk]))
        targets = torch.zeros((len(chunk), len(MATERIAL_CLASSES)))
        for row, item in enumerate(chunk):
            for label in item.labels:
                targets[row, CLASS_INDEX[label.material_class]] = 1.0
        yield images, targets


def detection_batches(
    examples: tuple[Example, ...], batch_size: int
) -> Iterator[tuple[Any, Any]]:
    """Yield image batches with boxes, using visible labels alone.

    A label whose object is outside the frame has no pixels to regress toward,
    so including it would teach the detector to predict a box where there is
    nothing. An example with no visible label is skipped rather than yielded
    with an empty target.

    Args:
        examples: Training examples.
        batch_size: Examples per batch.

    Yields:
        A list of images and a list of target dictionaries, which is the shape
        torchvision detectors expect.
    """
    import torch

    usable = [item for item in examples if item.visible_labels]
    for start in range(0, len(usable), batch_size):
        chunk = usable[start : start + batch_size]
        images = [torch.from_numpy(_as_chw(item.frame)) for item in chunk]
        targets = []
        for item in chunk:
            boxes, labels = [], []
            for label in item.visible_labels:
                x_min, y_min, x_max, y_max = label.bbox or (0, 0, 0, 0)
                # torchvision rejects a degenerate box, and a one pixel object
                # at the frame edge produces one.
                if x_max <= x_min or y_max <= y_min:
                    continue
                boxes.append([float(x_min), float(y_min), float(x_max), float(y_max)])
                labels.append(CLASS_INDEX[label.material_class] + 1)
            if not boxes:
                continue
            targets.append(
                {
                    "boxes": torch.tensor(boxes, dtype=torch.float32),
                    "labels": torch.tensor(labels, dtype=torch.int64),
                }
            )
        if len(targets) == len(images) and targets:
            yield images, targets


def policy_batches(
    examples: tuple[Example, ...], batch_size: int, window_exit: float
) -> Iterator[tuple[Any, Any, Any]]:
    """Yield observation batches paired with the expert's decision.

    Demonstrations are the only pick signal the simulation produces, because the
    arm is inert and no reward can be earned by acting.

    Args:
        examples: Training examples.
        batch_size: Examples per batch.
        window_exit: Belt coordinate where the reachable window ends.

    Since v0.6.2 the observation carries the manipulator's joint angles, so the
    policy can see where its own arm is. An example recorded before that, or any
    real photograph, carries none, and its state is zeroed rather than dropped so
    the two remain mixable in one batch.

    Yields:
        Image, state and target position triples.
    """
    import torch

    demonstrated = []
    for item in examples:
        decision = decide(item.labels, window_exit)
        if decision is not None:
            demonstrated.append((item, decision))

    for start in range(0, len(demonstrated), batch_size):
        chunk = demonstrated[start : start + batch_size]
        images = torch.from_numpy(np.stack([_as_chw(item.frame) for item, _ in chunk]))
        actions = torch.tensor(
            [list(decision.position) for _, decision in chunk], dtype=torch.float32
        )
        states = torch.zeros((len(chunk), STATE_DIMENSION), dtype=torch.float32)
        for row, (item, _) in enumerate(chunk):
            if item.arm_joints:
                width = min(len(item.arm_joints), STATE_DIMENSION)
                states[row, :width] = torch.tensor(item.arm_joints[:width])
        yield images, states, actions


ACT_FRAME_SIZE = 96


def act_batches(
    examples: tuple[Example, ...],
    batch_size: int,
    window_exit: float,
    chunk_size: int,
) -> Iterator[dict[str, Any]]:
    """Yield lerobot-shaped batches for an action chunking policy.

    ACT predicts a chunk of future actions rather than one, so each observation
    is paired with the expert's next `chunk_size` decisions. Where the rollout
    runs out, the chunk is padded and the pad mask says so, which is lerobot's
    own convention for a short horizon.

    Frames are resized to the square input the policy was configured with.

    Args:
        examples: Training examples.
        batch_size: Observations per batch.
        window_exit: Belt coordinate where the reachable window ends.
        chunk_size: Actions predicted per observation.

    Yields:
        Batches carrying observation.image, observation.state, action and
        action_is_pad.
    """
    import torch
    import torch.nn.functional as functional

    decisions: list[tuple[Example, Any]] = []
    for item in examples:
        decision = decide(item.labels, window_exit)
        if decision is not None:
            decisions.append((item, decision))

    for start in range(0, len(decisions), batch_size):
        chunk = decisions[start : start + batch_size]
        images = torch.from_numpy(np.stack([_as_chw(item.frame) for item, _ in chunk]))
        images = functional.interpolate(
            images, size=(ACT_FRAME_SIZE, ACT_FRAME_SIZE), mode="bilinear"
        )
        states = torch.zeros((len(chunk), STATE_DIMENSION), dtype=torch.float32)
        for row, (item, _) in enumerate(chunk):
            if item.arm_joints:
                width = min(len(item.arm_joints), STATE_DIMENSION)
                states[row, :width] = torch.tensor(item.arm_joints[:width])
        actions = torch.zeros((len(chunk), chunk_size, 6), dtype=torch.float32)
        pad = torch.ones((len(chunk), chunk_size), dtype=torch.bool)
        for row in range(len(chunk)):
            absolute = start + row
            for step in range(chunk_size):
                ahead = absolute + step
                if ahead >= len(decisions):
                    break
                future = decisions[ahead][1]
                actions[row, step, :3] = torch.tensor(list(future.position))
                pad[row, step] = False
        yield {
            "observation.image": images,
            "observation.state": states,
            "action": actions,
            "action_is_pad": pad,
        }
