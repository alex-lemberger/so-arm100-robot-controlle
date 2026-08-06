# tests/learn/test_eval.py
import json

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.learn.dataset import CUBE_REGION, generate_demos
from htdp.learn.eval import EVAL_SEED, baseline_at, eval_positions, evaluate, wilson_ci
from htdp.learn.train import train


def test_wilson_ci_known_values():
    # Wilson score interval, z=1.96. Reference values computed from the closed form.
    lo, hi = wilson_ci(4, 6)
    assert lo == pytest.approx(0.3000, abs=1e-3)
    assert hi == pytest.approx(0.9032, abs=1e-3)
    lo, hi = wilson_ci(27, 40)
    assert lo == pytest.approx(0.5202, abs=1e-3)
    assert hi == pytest.approx(0.7992, abs=1e-3)


def test_wilson_ci_edges():
    lo, hi = wilson_ci(0, 10)
    assert lo == 0.0
    assert 0.0 < hi < 0.5
    lo, hi = wilson_ci(10, 10)
    assert hi == 1.0
    assert 0.5 < lo < 1.0
    assert wilson_ci(0, 0) == (0.0, 1.0)  # no data -> no information


def test_eval_positions_fresh_sample(tmp_path):
    """--n-positions path: fresh in-region positions from EVAL_SEED, disjoint from the
    legacy test_positions.json split (train=seed, test=seed+1000, eval=2000)."""
    ds = generate_demos(tmp_path / "demos", n_train=2, n_test=3, seed=0)
    legacy = eval_positions(ds, n_positions=None)
    assert len(legacy) == 3  # no n -> test_positions.json, unchanged default

    fresh = eval_positions(ds, n_positions=5)
    assert len(fresh) == 5
    (xlo, xhi), (ylo, yhi) = CUBE_REGION
    for x, y in fresh:
        assert xlo <= x <= xhi and ylo <= y <= yhi
    assert set(fresh).isdisjoint(set(legacy))
    assert fresh == eval_positions(ds, n_positions=5)  # deterministic
    assert fresh != eval_positions(ds, n_positions=5, eval_seed=EVAL_SEED + 1)


def test_baseline_succeeds(tmp_path):
    rep = baseline_at([(0.50, -0.15), (0.48, -0.12)])
    assert rep["n"] == 2
    assert rep["success_rate"] == 1.0  # scripted teacher always places
    assert rep["ci95"] == pytest.approx(wilson_ci(2, 2))


def test_evaluate_end_to_end_smoke(tmp_path):
    ds = generate_demos(tmp_path / "demos", n_train=2, n_test=2, seed=0)
    ckpt = train(ds, tmp_path / "policy.pt", steps=50, batch=16, chunk=8, seed=0)
    positions = json.loads((ds / "meta" / "test_positions.json").read_text())
    rep = evaluate(ckpt, [tuple(p) for p in positions], out_path=tmp_path / "report.json")
    assert set(rep) == {"policy", "baseline"}
    assert "success_rate" in rep["policy"] and "success_rate" in rep["baseline"]
    assert "ci95" in rep["policy"] and "ci95" in rep["baseline"]
    assert (tmp_path / "report.json").exists()


def test_policy_beats_zero_on_held_out(tmp_path):
    # Regression guard for the 0%->100% fix: a small policy must achieve nonzero
    # held-out success. Catches reverts of the obs-landmine / kinematic-exec /
    # receding-horizon fixes that silently zeroed success.
    import json

    from htdp.learn.rollout import load_policy, rollout_policy

    ds = generate_demos(tmp_path / "demos", n_train=30, n_test=6, seed=0)
    ckpt = train(ds, tmp_path / "policy.pt", steps=2500, batch=32, seed=0)
    net, norm = load_policy(ckpt)
    positions = [tuple(p) for p in json.loads((ds / "meta" / "test_positions.json").read_text())]
    results = [rollout_policy(net, norm, p) for p in positions]
    success_rate = sum(r.success for r in results) / len(results)
    assert success_rate > 0.0, f"policy learned nothing (success_rate={success_rate})"


def test_evaluate_visuomotor_domain_randomize_off_by_default(tmp_path):
    """C1: DR must be opt-in for eval too, so committed B3/E1 numbers don't shift silently
    (docs/m2/c1-domain-randomization-scope.md)."""
    from unittest.mock import patch

    from htdp.learn.eval import evaluate_visuomotor
    from htdp.learn.rollout import rollout_visuomotor_policy as real
    from htdp.learn.train import train_visuomotor

    ds = generate_demos(tmp_path / "demos", n_train=2, n_test=2, seed=0)
    ckpt = train_visuomotor(ds, tmp_path / "vm.pt", steps=50, batch=16, chunk=8, seed=0)
    positions = [tuple(p) for p in json.loads((ds / "meta" / "test_positions.json").read_text())]

    with patch("htdp.learn.rollout.rollout_visuomotor_policy") as spy:
        spy.side_effect = real
        evaluate_visuomotor(ckpt, positions)
    for _, kwargs in spy.call_args_list:
        assert kwargs.get("domain_randomize", False) is False


def test_evaluate_visuomotor_domain_randomize_uses_distinct_seed_per_position(tmp_path):
    """Each held-out position gets its own DR seed (dr_seed_base + index) — the C1 'novel DR
    seeds' eval cell needs independent scene draws per position, not one shared randomization."""
    from unittest.mock import patch

    from htdp.learn.eval import evaluate_visuomotor
    from htdp.learn.rollout import rollout_visuomotor_policy as real
    from htdp.learn.train import train_visuomotor

    ds = generate_demos(tmp_path / "demos", n_train=2, n_test=2, seed=0)
    ckpt = train_visuomotor(ds, tmp_path / "vm.pt", steps=50, batch=16, chunk=8, seed=0)
    positions = [tuple(p) for p in json.loads((ds / "meta" / "test_positions.json").read_text())]

    with patch("htdp.learn.rollout.rollout_visuomotor_policy") as spy:
        spy.side_effect = real
        evaluate_visuomotor(ckpt, positions, domain_randomize=True, dr_seed_base=5000)

    seeds = [kwargs["dr_seed"] for _, kwargs in spy.call_args_list]
    assert all(kwargs.get("domain_randomize") is True for _, kwargs in spy.call_args_list)
    assert seeds == [5000, 5001]


def test_visuomotor_policy_beats_zero_on_held_out(tmp_path):
    """B3 capstone gate: a policy that sees ONLY the front image + proprio (no privileged cube or
    target xyz) must achieve nonzero held-out success under true physics. Proves the CNN localises
    the cube and goal from pixels and drives a friction grasp closed-loop. seed=0 measured 4/6."""
    import json

    from htdp.learn.rollout import load_visuomotor_policy, rollout_visuomotor_policy
    from htdp.learn.train import train_visuomotor

    ds = generate_demos(tmp_path / "demos", n_train=40, n_test=6, seed=0)
    ckpt = train_visuomotor(ds, tmp_path / "vm.pt", steps=6000, batch=32, seed=0)
    net, norm = load_visuomotor_policy(ckpt)
    positions = [tuple(p) for p in json.loads((ds / "meta" / "test_positions.json").read_text())]
    results = [rollout_visuomotor_policy(net, norm, p) for p in positions]
    success_rate = sum(r.success for r in results) / len(results)
    assert success_rate > 0.0, f"visuomotor policy learned nothing (success_rate={success_rate})"
