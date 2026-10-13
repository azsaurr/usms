"""
USMS Captcha Module.

USMS asks for a captcha after accepting a username and password. A solver is any
callable taking the captcha image (PNG bytes) and returning its text; `solve` is
the built-in one, and a client can be given another.

The model is loaded on first use rather than at import, so a client that never
meets a captcha never pays for reading it.
"""

import io
from collections.abc import Callable
from functools import cache
from typing import TypeAlias

import numpy as np
from PIL import Image

from usms.captcha.model import INPUT_HEIGHT, CaptchaModel

CaptchaSolver: TypeAlias = Callable[[bytes], str]

__all__ = ["CaptchaSolver", "load_model", "solve"]


@cache
def load_model() -> CaptchaModel:
    """Return the shared captcha model, loading it on the first call."""
    return CaptchaModel()


def _to_input(image_bytes: bytes) -> np.ndarray:
    """
    Return an image as the model's [1, 1, 64, W] float input.

    USMS draws its captcha only in the alpha channel - every RGB value is zero - so
    a plain greyscale conversion yields a solid black image. Compositing onto white
    first turns it into dark text on a light background, which is what the network
    was trained on.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    flattened = Image.alpha_composite(Image.new("RGBA", image.size, "white"), image)
    width = int(image.width * INPUT_HEIGHT / image.height)  # truncated, as ddddocr does
    grey = (
        flattened.convert("RGB")
        .resize((width, INPUT_HEIGHT), Image.Resampling.LANCZOS)
        .convert("L")
    )
    return (np.asarray(grey, dtype=np.float32) / 255.0)[None, None]


def solve(image_bytes: bytes) -> str:
    """Return the text of a USMS captcha image, using the built-in model."""
    return load_model().decode(_to_input(image_bytes))
