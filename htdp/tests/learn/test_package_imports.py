def test_learn_imports_without_torch():
    import htdp.learn  # noqa: F401  # must not import torch at module load
    from htdp.learn.errors import LearnUnavailable

    assert issubclass(LearnUnavailable, RuntimeError)
