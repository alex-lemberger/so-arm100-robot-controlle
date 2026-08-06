# tests/learn/test_rollout.py
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.learn.obs import OBS_DIM
from htdp.learn.policy import ACTConfig, ACTPolicy
from htdp.learn.rollout import RolloutResult, rollout_policy
from htdp.learn.train import Normalizer


def _dummy_norm():
    stats = {
        "observation.state": {"mean": [0.0] * OBS_DIM, "std": [1.0] * OBS_DIM,
                              "min": [0.0] * OBS_DIM, "max": [1.0] * OBS_DIM},
        "action": {"mean": [0.0] * 8, "std": [1.0] * 8,
                   "min": [0.0] * 8, "max": [1.0] * 8},
    }
    return Normalizer(stats)


def test_rollout_untrained_policy_runs_without_crashing():
    torch.manual_seed(0)
    net = ACTPolicy(ACTConfig(chunk=8))
    res = rollout_policy(net, _dummy_norm(), (0.50, -0.15), max_chunks=5)
    assert isinstance(res, RolloutResult)
    assert isinstance(res.success, bool)
    assert res.steps > 0


def test_rollout_is_deterministic():
    torch.manual_seed(0)
    net = ACTPolicy(ACTConfig(chunk=8))
    a = rollout_policy(net, _dummy_norm(), (0.50, -0.15), max_chunks=5)
    b = rollout_policy(net, _dummy_norm(), (0.50, -0.15), max_chunks=5)
    assert a.cube_final_xy == b.cube_final_xy


def _dummy_vm_norm():
    from htdp.learn.obs import PROPRIO_DIM
    from htdp.learn.train import VisuomotorNormalizer

    p = {"mean": [0.0] * PROPRIO_DIM, "std": [1.0] * PROPRIO_DIM}
    a = {"mean": [0.0] * 8, "std": [1.0] * 8}
    return VisuomotorNormalizer(p, a)


def test_visuomotor_rollout_runs_and_is_deterministic():
    from htdp.learn.policy import VisuomotorACTConfig, VisuomotorACTPolicy
    from htdp.learn.rollout import rollout_visuomotor_policy

    torch.manual_seed(0)
    net = VisuomotorACTPolicy(VisuomotorACTConfig(chunk=8))
    a = rollout_visuomotor_policy(net, _dummy_vm_norm(), (0.50, -0.15), max_chunks=4)
    b = rollout_visuomotor_policy(net, _dummy_vm_norm(), (0.50, -0.15), max_chunks=4)
    assert isinstance(a, RolloutResult)
    assert a.steps > 0
    assert a.cube_final_xy == b.cube_final_xy


def test_visuomotor_rollout_domain_randomize_off_by_default(tmp_path):
    """DR must be opt-in for eval too (docs/m2/c1-domain-randomization-scope.md): the canonical
    B3 rollout gate/numbers must not shift silently."""
    from unittest.mock import patch

    from htdp.learn.policy import VisuomotorACTConfig, VisuomotorACTPolicy
    from htdp.learn.rollout import rollout_visuomotor_policy

    torch.manual_seed(0)
    net = VisuomotorACTPolicy(VisuomotorACTConfig(chunk=8))
    with patch("htdp.replay.domain_randomization.randomize_scene") as spy:
        rollout_visuomotor_policy(net, _dummy_vm_norm(), (0.50, -0.15), max_chunks=2)
    spy.assert_not_called()


def test_visuomotor_rollout_domain_randomize_perturbs_scene_once(tmp_path):
    """domain_randomize=True calls randomize_scene exactly once (per-episode, matching demo-gen's
    per-episode DR), seeded by dr_seed."""
    from unittest.mock import patch

    from htdp.learn.policy import VisuomotorACTConfig, VisuomotorACTPolicy
    from htdp.learn.rollout import rollout_visuomotor_policy

    torch.manual_seed(0)
    net = VisuomotorACTPolicy(VisuomotorACTConfig(chunk=8))
    with patch(
        "htdp.replay.domain_randomization.randomize_scene", side_effect=lambda *a, **k: None
    ) as spy:
        rollout_visuomotor_policy(
            net, _dummy_vm_norm(), (0.50, -0.15), max_chunks=2,
            domain_randomize=True, dr_seed=3,
        )
    spy.assert_called_once()


def test_visuomotor_rollout_writes_video(tmp_path):
    pytest.importorskip("imageio")
    from htdp.learn.policy import VisuomotorACTConfig, VisuomotorACTPolicy
    from htdp.learn.rollout import rollout_visuomotor_policy

    torch.manual_seed(0)
    net = VisuomotorACTPolicy(VisuomotorACTConfig(chunk=8))
    out = tmp_path / "rollout.mp4"
    rollout_visuomotor_policy(net, _dummy_vm_norm(), (0.50, -0.15), max_chunks=2, video_out=out)
    assert out.exists() and out.stat().st_size > 10_000
