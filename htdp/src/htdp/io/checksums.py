import hashlib
from pathlib import Path

_CHECKSUM_FILE = "checksums.sha256"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _iter_files(session_dir: Path) -> list[Path]:
    return sorted(p for p in session_dir.rglob("*") if p.is_file() and p.name != _CHECKSUM_FILE)


def write_checksums(session_dir: Path) -> Path:
    lines = [
        f"{sha256_file(p)}  {p.relative_to(session_dir).as_posix()}"
        for p in _iter_files(session_dir)
    ]
    out = session_dir / _CHECKSUM_FILE
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


def verify_checksums(session_dir: Path) -> list[str]:
    recorded: dict[str, str] = {}
    cfile = session_dir / _CHECKSUM_FILE
    for line in cfile.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        recorded[rel] = digest
    mismatches: list[str] = []
    present = {p.relative_to(session_dir).as_posix() for p in _iter_files(session_dir)}
    for rel, digest in recorded.items():
        path = session_dir / rel
        if not path.exists() or sha256_file(path) != digest:
            mismatches.append(rel)
    mismatches.extend(rel for rel in present - set(recorded))  # unexpected new files
    return sorted(set(mismatches))
