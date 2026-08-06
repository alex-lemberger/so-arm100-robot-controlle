from pathlib import Path

from htdp.synth.generate import generate_session
from htdp.validate import validate_session


def test_clean_session_validates(tmp_path: Path) -> None:
    d = generate_session(tmp_path, seed=1)
    assert validate_session(d) == []


def test_tampered_session_fails(tmp_path: Path) -> None:
    d = generate_session(tmp_path, seed=1)
    (d / "streams/events.csv").write_text("corrupt\n", encoding="utf-8")
    problems = validate_session(d)
    assert any("checksum" in p for p in problems)


def test_missing_file_fails(tmp_path: Path) -> None:
    d = generate_session(tmp_path, seed=1)
    (d / "session.json").unlink()
    problems = validate_session(d)
    assert any("session.json" in p for p in problems)
