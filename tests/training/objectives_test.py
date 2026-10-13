from __future__ import annotations

import pytest

pytest.importorskip("torch")

from unittest.mock import Mock

import torch

from clave.training import objectives


def test_multilabel_presence() -> None:
    batch_size = 2
    images = torch.zeros((batch_size, 3, 224, 224))
    targets = torch.tensor([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0]])

    logits = torch.tensor([[0.0, -1.0, 2.0], [1.0, 0.5, -0.5]])
    model = Mock(return_value=logits)

    batch = (images, targets)
    loss = objectives.multilabel_presence(model, batch)

    expected_loss = torch.nn.functional.binary_cross_entropy_with_logits(
        logits, targets
    )

    assert torch.isclose(loss, expected_loss)
    model.assert_called_once_with(images)
