from __future__ import annotations


def sanitize(label: str) -> str:
    """Reduce a label to BIDS-safe alphanumerics (drop separators/punctuation)."""
    return "".join(c for c in label if c.isalnum())


def entity_stem(sub: str, task: str, tracksys: str) -> str:
    return f"sub-{sub}_task-{task}_tracksys-{tracksys}"
