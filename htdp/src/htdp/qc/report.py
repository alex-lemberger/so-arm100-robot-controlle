from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from htdp.io.canonical import dump_json

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


def write_reports(report: dict[str, object], out_dir: Path) -> None:
    dump_json(report, out_dir / "qc_report.json")
    html = _ENV.get_template("report.html.j2").render(report=report)
    (out_dir / "qc_report.html").write_text(html, encoding="utf-8", newline="\n")
