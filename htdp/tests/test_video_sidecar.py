import pytest
from pydantic import ValidationError

from htdp.ingest.video import VideoIngestError, VideoSidecar


def test_valid_sidecar():
    s = VideoSidecar(name="frontal", fps=30.0)
    assert s.name == "frontal" and s.fps == 30.0


def test_video_ingest_error_is_runtime_error():
    assert issubclass(VideoIngestError, RuntimeError)


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        VideoSidecar(name="", fps=30.0)


def test_nonpositive_fps_rejected():
    with pytest.raises(ValidationError):
        VideoSidecar(name="frontal", fps=0.0)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        VideoSidecar(name="frontal", fps=30.0, codec="h264")
