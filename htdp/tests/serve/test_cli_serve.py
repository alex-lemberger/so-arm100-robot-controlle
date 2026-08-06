import pytest

pytest.importorskip("fastapi")
from typer.testing import CliRunner

from htdp.cli import app


def test_serve_command_registered():
    result = CliRunner().invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output
    assert "--data-dir" in result.output
