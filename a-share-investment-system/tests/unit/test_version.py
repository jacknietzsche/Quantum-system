"""Unit tests for shared.version."""


def test_version_exists():
    from shared.version import VERSION

    assert isinstance(VERSION, str)
    assert len(VERSION) > 0


def test_version_format():
    from shared.version import VERSION

    parts = VERSION.split(".")
    assert len(parts) >= 2  # at least major.minor
