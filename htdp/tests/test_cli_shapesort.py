import json

from typer.testing import CliRunner

from htdp.cli import app

runner = CliRunner()


def test_cli_shapesort_eval_report(tmp_path):
    trials_path = tmp_path / "trials.jsonl"
    trials_path.write_text(
        "\n".join(
            [
                json.dumps({"outcome": "success", "used_fallback": False}),
                json.dumps({"outcome": "success", "used_fallback": True}),
                json.dumps({"outcome": "asr_miss", "used_fallback": False}),
            ]
        )
    )
    out_path = tmp_path / "report.json"

    result = runner.invoke(
        app,
        ["shapesort-eval-report", "--trials", str(trials_path), "--out", str(out_path)],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text())
    assert report["n"] == 3
    assert report["success_rate"] == 2 / 3
    assert report["failure_taxonomy"] == {"success": 2, "asr_miss": 1}
