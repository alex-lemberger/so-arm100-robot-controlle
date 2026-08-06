"""Generate a per-episode contact-sheet image (and an editable curation
manifest) from recorded teleoperation episodes, so a human can quickly
flag which ones to include before building a LeRobot dataset from them.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

EPISODES_ROOT = Path("data/local/episodes")
OUTPUT_DIR = Path("outputs/episode-review")
FRAME_PERCENTAGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
GRID_COLS = 3
GRID_ROWS = 2
THUMB_WIDTH = 480


def discover_episodes() -> list[str]:
    if not EPISODES_ROOT.is_dir():
        raise FileNotFoundError(f"No episodes directory at {EPISODES_ROOT}")
    names = sorted(p.name for p in EPISODES_ROOT.iterdir() if p.is_dir())
    if not names:
        raise FileNotFoundError(f"No episode subdirectories found under {EPISODES_ROOT}")
    return names


def extract_frame(video_path: Path, at_seconds: float, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{at_seconds:.3f}", "-i", str(video_path),
            "-frames:v", "1", str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def build_contact_sheet(episode_dir: Path, out_path: Path) -> None:
    metadata = json.loads((episode_dir / "metadata.json").read_text())
    duration_s = metadata["durationMs"] / 1000
    overview_file = episode_dir / metadata["observations"]["overview"]["file"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        thumbs = []
        for i, pct in enumerate(FRAME_PERCENTAGES):
            # Clamp away from the exact end timestamp — ffmpeg -ss at or past
            # the last frame's pts can return no frame at all. Use a larger
            # margin (0.2s) to account for metadata duration mismatches in WebM files.
            at_seconds = min(pct * duration_s, duration_s - 0.2)
            frame_path = tmp_dir / f"frame_{i}.jpg"
            extract_frame(overview_file, max(at_seconds, 0.0), frame_path)
            image = Image.open(frame_path)
            aspect = image.height / image.width
            image = image.resize((THUMB_WIDTH, int(THUMB_WIDTH * aspect)))
            thumbs.append(image)

        thumb_w, thumb_h = thumbs[0].size
        sheet = Image.new("RGB", (thumb_w * GRID_COLS, thumb_h * GRID_ROWS))
        for i, thumb in enumerate(thumbs):
            col, row = i % GRID_COLS, i // GRID_COLS
            sheet.paste(thumb, (col * thumb_w, row * thumb_h))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out_path, quality=85)


def write_manifest(episode_names: list[str], out_path: Path) -> None:
    lines = [
        "# Curation manifest: one episode folder name per line.",
        "# Delete a line to exclude that episode from the LeRobot dataset build.",
        "# Lines starting with # are ignored.",
        *episode_names,
    ]
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    episode_names = discover_episodes()
    for name in episode_names:
        episode_dir = EPISODES_ROOT / name
        out_path = OUTPUT_DIR / f"{name}.jpg"
        build_contact_sheet(episode_dir, out_path)
        print(f"Wrote {out_path}")

    manifest_path = OUTPUT_DIR / "curated-episodes.txt"
    if manifest_path.exists():
        fallback_path = OUTPUT_DIR / "curated-episodes.txt.new"
        write_manifest(episode_names, fallback_path)
        print(f"{manifest_path} already exists and may contain hand-curated edits — not overwriting it.")
        print(
            f"Wrote the current full episode list to {fallback_path} instead. "
            f"Diff it against {manifest_path} and manually merge in any newly-discovered "
            "episodes you want to include."
        )
    else:
        write_manifest(episode_names, manifest_path)
        print(f"Wrote manifest listing {len(episode_names)} episodes to {manifest_path}")
        print("Review the contact sheets, then edit the manifest to remove any episodes to exclude.")


if __name__ == "__main__":
    main()
