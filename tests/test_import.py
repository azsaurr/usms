"""Test importing usms."""

import usms


def test_import() -> None:
    """Test that the package can be imported."""
    assert isinstance(usms.__name__, str)
