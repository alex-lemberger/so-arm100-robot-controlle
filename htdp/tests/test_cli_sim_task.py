import pytest
from typer.testing import CliRunner

from htdp.cli import app

runner = CliRunner()


def test_sim_task_reports_metrics():
    pytest.importorskip("mujoco")
    pytest.importorskip("mink")
    res = runner.invoke(app, ["sim-task"])
    assert res.exit_code == 0
    assert "place_error" in res.stdout
