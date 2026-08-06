from pathlib import Path
from htdp.io.canonical import dump_json, write_csv


def test_dump_json_is_sorted_and_stable(tmp_path: Path):
    p = tmp_path / "a.json"
    dump_json({"b": 1, "a": 2}, p)
    assert p.read_text(encoding="utf-8") == '{\n  "a": 2,\n  "b": 1\n}\n'


def test_write_csv_fixed_precision(tmp_path: Path):
    p = tmp_path / "m.csv"
    write_csv([{"x": 1.23456789, "n": "k"}], ["x", "n"], p)
    assert p.read_text(encoding="utf-8") == "x,n\n1.234568,k\n"
