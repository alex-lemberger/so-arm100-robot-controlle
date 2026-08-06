import json

import pytest

pytest.importorskip("torch")
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from typer.testing import CliRunner

from htdp.cli import app

runner = CliRunner()


def test_cli_gen_train_eval(tmp_path):
    demos = tmp_path / "demos"
    r1 = runner.invoke(app, ["gen-demos", "--out", str(demos),
                             "--n-train", "2", "--n-test", "2", "--seed", "0"])
    assert r1.exit_code == 0, r1.output
    assert (demos / "meta" / "info.json").exists()

    policy = tmp_path / "policy.pt"
    r2 = runner.invoke(app, ["train-policy", "--demos", str(demos),
                             "--out", str(policy), "--steps", "20"])
    assert r2.exit_code == 0, r2.output
    assert policy.exists()

    report = tmp_path / "report.json"
    r3 = runner.invoke(app, ["eval-policy", "--demos", str(demos),
                             "--policy", str(policy), "--out", str(report)])
    assert r3.exit_code == 0, r3.output
    assert report.exists()
    rep = json.loads(report.read_text())
    assert "policy" in rep and "baseline" in rep

    # --n-positions: fresh eval positions instead of test_positions.json (E1)
    report_n = tmp_path / "report_n.json"
    r4 = runner.invoke(app, ["eval-policy", "--demos", str(demos),
                             "--policy", str(policy), "--out", str(report_n),
                             "--n-positions", "1"])
    assert r4.exit_code == 0, r4.output
    rep_n = json.loads(report_n.read_text())
    assert rep_n["policy"]["n"] == 1  # dataset test split has 2 -> proves fresh-sample path
    assert "ci95" in rep_n["policy"]


def test_cli_domain_randomize_train_and_eval_end_to_end(tmp_path):
    """C1 gate: train a visuomotor policy on DR demos, then eval it under NOVEL DR seeds
    (disjoint from train-time DR seeds since dataset seed=0 and dr_seed_base=5000) -- success
    must beat zero (docs/m2/c1-domain-randomization-scope.md)."""
    demos = tmp_path / "demos"
    r1 = runner.invoke(app, ["gen-demos", "--out", str(demos),
                             "--n-train", "40", "--n-test", "6", "--seed", "0",
                             "--domain-randomize"])
    assert r1.exit_code == 0, r1.output

    vm = tmp_path / "vm.pt"
    r2 = runner.invoke(app, ["train-visuomotor", "--demos", str(demos),
                             "--out", str(vm), "--steps", "6000"])
    assert r2.exit_code == 0, r2.output

    report = tmp_path / "report.json"
    r3 = runner.invoke(app, ["eval-visuomotor", "--demos", str(demos),
                             "--policy", str(vm), "--out", str(report),
                             "--domain-randomize"])
    assert r3.exit_code == 0, r3.output
    rep = json.loads(report.read_text())
    assert rep["policy"]["success_rate"] > 0.0, "DR policy learned nothing under novel DR"
