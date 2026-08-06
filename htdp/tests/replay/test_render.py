import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("imageio")

from htdp.replay.render import render_episode


def test_render_writes_nonempty_mp4(tmp_path):
    out = render_episode(tmp_path / "demo.mp4", every=40)
    assert out.exists() and out.stat().st_size > 10_000
    with pytest.raises(FileExistsError):
        render_episode(out, every=40)
