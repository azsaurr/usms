# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["ddddocr==1.6.1", "onnx"]
# ///
"""
Export ddddocr's OCR model into the numpy-runnable form in `src/usms/captcha/`.

Run once, offline, whenever the model needs regenerating:

    uv run tools/export_captcha_model.py

`common_old.onnx` is the model ddddocr itself uses by default. Its final MatMul
scores 8210 classes, most of them CJK; only the CTC blank and a-z0-9 are kept,
which shrinks that layer from 8.4 MB to 38 KB and means decoding can never pick a
character USMS does not draw.
"""

import json
from pathlib import Path

import ddddocr
import numpy as np
import onnx
from ddddocr.models.charset_manager import CharsetManager
from onnx import numpy_helper

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "src" / "usms" / "captcha"
ALLOWED = "abcdefghijklmnopqrstuvwxyz0123456789"

# Initializer names of the final MatMul weights and bias in common_old.onnx.
FINAL_WEIGHTS, FINAL_BIAS = "135_quantized", "136"


def _attribute(attribute: onnx.AttributeProto) -> object:
    value = onnx.helper.get_attribute_value(attribute)
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, onnx.TensorProto):
        return numpy_helper.to_array(value).tolist()
    return list(value) if isinstance(value, (list, tuple)) else value


def main() -> None:
    """Write graph.json and weights.npz."""
    model = onnx.load(Path(ddddocr.__file__).parent / "common_old.onnx")

    charsets = CharsetManager()
    charsets.load_default_charset(old=True)
    charset = charsets.get_charset()
    keep = [0] + [charset.index(character) for character in ALLOWED]  # 0 is the CTC blank

    initializers = {i.name: numpy_helper.to_array(i) for i in model.graph.initializer}
    initializers[FINAL_WEIGHTS] = initializers[FINAL_WEIGHTS][:, keep]
    initializers[FINAL_BIAS] = initializers[FINAL_BIAS][keep]

    nodes = [
        {
            "op": node.op_type,
            "in": list(node.input),
            "out": list(node.output),
            "attr": {a.name: _attribute(a) for a in node.attribute},
        }
        for node in model.graph.node
    ]

    # npz keys cannot hold ':', which several ONNX tensor names contain.
    np.savez_compressed(
        OUTPUT_DIR / "weights.npz",
        **{name.replace(":", "__"): value for name, value in initializers.items()},
    )
    graph = {
        "input": model.graph.input[0].name,
        "output": model.graph.output[0].name,
        "nodes": nodes,
        "charset": ["", *ALLOWED],
    }
    (OUTPUT_DIR / "graph.json").write_text(json.dumps(graph), encoding="utf-8")


if __name__ == "__main__":
    main()
