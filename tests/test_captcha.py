"""
Test the built-in captcha solver.

The fixtures are real USMS captchas whose answers USMS itself accepted, named after
those answers.
"""

from pathlib import Path

import pytest

from usms.captcha import load_model, solve

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "captcha").glob("*.png"))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
def test_solver_reads_real_usms_captchas(fixture) -> None:
    """Test that the solver reproduces answers USMS accepted."""
    assert solve(fixture.read_bytes()) == fixture.stem


def test_model_only_emits_characters_usms_draws() -> None:
    """Test that the trimmed model cannot decode to anything outside a-z0-9."""
    charset = load_model().charset

    assert charset[0] == ""  # the CTC blank
    assert "".join(charset[1:]) == "abcdefghijklmnopqrstuvwxyz0123456789"


def test_fixtures_are_present() -> None:
    """Test that the parametrised test above is not silently running zero cases."""
    assert len(FIXTURES) >= 3
