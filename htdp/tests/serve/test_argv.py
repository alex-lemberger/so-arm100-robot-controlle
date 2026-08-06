from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from htdp.serve.jobs import ALLOWED_KINDS, JobKindError, build_argv


def test_gen_demos_argv_uses_server_paths():
    argv = build_argv("gen-demos", {"n_train": 10, "n_test": 2}, Path("/data"))
    assert argv == ["gen-demos", "--out", "demos", "--n-train", "10", "--n-test", "2"]


def test_unknown_kind_rejected():
    with pytest.raises(JobKindError):
        build_argv("rm-rf", {}, Path("/data"))


def test_out_of_range_arg_rejected():
    with pytest.raises(JobKindError):
        build_argv("gen-demos", {"n_train": 999999}, Path("/data"))


def test_request_cannot_inject_output_path():
    # An attacker-supplied 'out' must be ignored, not forwarded.
    argv = build_argv("gen-demos", {"out": "/etc/passwd", "n_train": 5}, Path("/data"))
    assert "/etc/passwd" not in argv
    assert "demos" in argv


def test_train_policy_argv():
    argv = build_argv("train-policy", {"steps": 100}, Path("/data"))
    assert argv == ["train-policy", "--demos", "demos", "--out", "policy.pt", "--steps", "100"]


def test_eval_policy_argv():
    assert build_argv("eval-policy", {}, Path("/data")) == [
        "eval-policy",
        "--demos",
        "demos",
        "--policy",
        "policy.pt",
    ]


def test_all_allowed_kinds_build():
    for kind in ALLOWED_KINDS:
        build_argv(kind, {}, Path("/data"))  # defaults must be valid
