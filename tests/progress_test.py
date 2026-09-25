"""The frame bar used while training and validating."""

import numpy as np

from clave.data.dataset import DatasetDescription, DatasetFile
from clave.progress import Progress, examples_in, frame_total


def _description() -> DatasetDescription:
    """Two archives in the train part, one of them unlisted."""
    files = (
        DatasetFile("rollout_000.npz", "a" * 64, 10, 150, 0),
        DatasetFile("rollout_001.npz", "b" * 64, 10, 150, 1),
    )
    return DatasetDescription(
        digest="c" * 64,
        seed=0,
        config_digest="d" * 64,
        example_count=300,
        parts={"train": ["rollout_000", "rollout_001"]},
        composition={},
        files=files,
    )


def test_frame_total_sums_one_part() -> None:
    """The bar length is the frames the archives say they hold."""
    assert frame_total(_description(), "train") == 300
    assert frame_total(_description(), "validation") is None


def test_a_missing_archive_record_has_no_known_length() -> None:
    """A part that names a file the description does not list cannot be sized."""
    description = _description()
    broken = DatasetDescription(
        digest=description.digest,
        seed=description.seed,
        config_digest=description.config_digest,
        example_count=description.example_count,
        parts={"train": ["rollout_000", "rollout_009"]},
        composition={},
        files=description.files,
    )
    assert frame_total(broken, "train") is None


def test_examples_in_reads_a_tensor_a_list_and_an_action_chunk() -> None:
    """Each adapter's batch shape counts as frames on the bar."""
    images = np.zeros((4, 3, 8, 8))
    assert examples_in((images, None)) == 4
    assert examples_in((["a", "b"], None)) == 2
    assert examples_in({"observation.image": images}) == 4


def test_the_bar_keeps_the_latest_metric_and_closes() -> None:
    """Loss and agreement stay visible as frames complete."""
    with Progress(10, "epoch 1/10", "frame") as bar:
        bar.update(4, loss=0.5)
        bar.update(2, loss=0.25)
        assert bar.completed == 6
        assert bar.metrics == {"loss": 0.25}
    assert bar.completed == 6
