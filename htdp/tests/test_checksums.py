from pathlib import Path
from htdp.io.checksums import sha256_bytes, write_checksums, verify_checksums


def test_sha256_bytes_known_value():
    assert (
        sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_checksums_roundtrip_and_tamper_detection(tmp_path: Path):
    (tmp_path / "streams").mkdir()
    f = tmp_path / "streams" / "a.csv"
    f.write_text("x\n1\n", encoding="utf-8")
    write_checksums(tmp_path)
    assert verify_checksums(tmp_path) == []
    f.write_text("x\n2\n", encoding="utf-8")  # tamper
    assert "streams/a.csv" in verify_checksums(tmp_path)
