"""Adapters for the shortlisted pick-policy architectures.

ACT and Diffusion Policy load from lerobot, which packages the reference
implementations. PPO loads from stable-baselines3. Behavior cloning has no
upstream and is implemented here as the deliberate simple comparator.

Imports are inside the builders: importing this module must not require torch.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clave.candidates.base import Candidate, CandidateSpec, Stage
from clave.candidates.fixture import (
    ACTION_DIMENSION,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    STATE_DIMENSION,
    frame,
    state,
)

ACT = CandidateSpec(
    name="act",
    stage=Stage.POLICY,
    license="MIT",
    source="lerobot.policies.act",
    requires="lerobot",
)

DIFFUSION_POLICY = CandidateSpec(
    name="diffusion-policy",
    stage=Stage.POLICY,
    license="MIT",
    source="lerobot.policies.diffusion",
    requires="lerobot",
)

PPO = CandidateSpec(
    name="ppo-mlp",
    stage=Stage.POLICY,
    license="MIT",
    source="stable_baselines3.PPO",
    requires="stable_baselines3",
)

BEHAVIOR_CLONING = CandidateSpec(
    name="behavior-cloning-baseline",
    stage=Stage.POLICY,
    license="MIT, implemented in this project",
    source="clave.candidates.policy",
    requires=None,
)


def _lerobot_features() -> Any:
    """Describe CLAVE's observation and action spaces in lerobot's vocabulary."""
    from lerobot.configs.types import FeatureType, PolicyFeature

    inputs = {
        "observation.image": PolicyFeature(
            type=FeatureType.VISUAL, shape=(3, FRAME_HEIGHT, FRAME_WIDTH)
        ),
        "observation.state": PolicyFeature(
            type=FeatureType.STATE, shape=(STATE_DIMENSION,)
        ),
    }
    outputs = {
        "action": PolicyFeature(type=FeatureType.ACTION, shape=(ACTION_DIMENSION,))
    }
    return inputs, outputs


def _build_act() -> Any:
    """Build the action chunking transformer from lerobot."""
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy

    inputs, outputs = _lerobot_features()
    return ACTPolicy(ACTConfig(input_features=inputs, output_features=outputs)).eval()


def _build_diffusion_policy() -> Any:
    """Build Diffusion Policy from lerobot."""
    from lerobot.policies.diffusion.configuration_diffusion import DiffusionConfig
    from lerobot.policies.diffusion.modeling_diffusion import DiffusionPolicy

    inputs, outputs = _lerobot_features()
    return DiffusionPolicy(
        DiffusionConfig(input_features=inputs, output_features=outputs)
    ).eval()


def _build_ppo() -> Any:
    """Build a PPO policy network over a continuous action space.

    The environment only supplies observation and action shapes; no training
    happens, and the episode is never stepped.
    """
    import gymnasium as gym
    import numpy as np
    from stable_baselines3 import PPO

    env = gym.make("Pendulum-v1")
    del np
    return PPO("MlpPolicy", env, device="cpu").policy.eval()


def _build_behavior_cloning() -> Any:
    """Build the simple comparator: a small convolutional encoder and a head.

    It exists so a later benchmark can show what the sophisticated policies are
    worth. Anything it matches was not worth its cost.
    """
    import torch
    from torch import nn

    class BehaviorCloning(nn.Module):
        """Map a frame and a state to an action in one forward pass."""

        def __init__(self) -> None:
            super().__init__()
            self.vision = nn.Sequential(
                nn.Conv2d(3, 16, 5, stride=2, padding=2),
                nn.ReLU(),
                nn.Conv2d(16, 32, 5, stride=2, padding=2),
                nn.ReLU(),
                nn.AdaptiveAvgPool2d(1),
                nn.Flatten(),
            )
            self.head = nn.Sequential(
                nn.Linear(32 + STATE_DIMENSION, 128),
                nn.ReLU(),
                nn.Linear(128, ACTION_DIMENSION),
            )

        def forward(self, image: Any, robot_state: Any) -> Any:
            """Return an action for one observation."""
            return self.head(torch.cat([self.vision(image), robot_state], dim=-1))

    return BehaviorCloning().eval()


def _observation_batch() -> Any:
    """Build one lerobot-shaped observation batch from the fixture."""
    import torch

    return {
        "observation.image": torch.from_numpy(frame()).unsqueeze(0),
        "observation.state": torch.from_numpy(state()).unsqueeze(0),
    }


def forward_lerobot(model: Any) -> Callable[[], Any]:
    """Return a callable running one lerobot policy forward pass.

    `select_action` caches an action chunk and dequeues from it on subsequent
    calls, so timing it repeatedly measures a list pop rather than the network.
    The queue is reset before every call, which measures the cost of producing a
    fresh chunk. That is the number a conveyor has to absorb whenever the scene
    changes, and it is the honest worst case.
    """
    import torch

    batch = _observation_batch()

    def run() -> Any:
        model.reset()
        with torch.no_grad():
            return model.select_action(batch)

    return run


def forward_ppo(model: Any) -> Callable[[], Any]:
    """Return a callable running one PPO policy forward pass."""
    import torch

    observation = torch.zeros((1, 3))

    def run() -> Any:
        with torch.no_grad():
            return model(observation)

    return run


def forward_behavior_cloning(model: Any) -> Callable[[], Any]:
    """Return a callable running one behavior cloning forward pass."""
    import torch

    image = torch.from_numpy(frame()).unsqueeze(0)
    robot_state = torch.from_numpy(state()).unsqueeze(0)

    def run() -> Any:
        with torch.no_grad():
            return model(image, robot_state)

    return run


POLICY_CANDIDATES: tuple[tuple[Candidate, Callable[[Any], Callable[[], Any]]], ...] = (
    (Candidate(ACT, _build_act), forward_lerobot),
    (Candidate(DIFFUSION_POLICY, _build_diffusion_policy), forward_lerobot),
    (Candidate(PPO, _build_ppo), forward_ppo),
    (Candidate(BEHAVIOR_CLONING, _build_behavior_cloning), forward_behavior_cloning),
)
