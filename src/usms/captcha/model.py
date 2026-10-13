"""
USMS Captcha Model Module.

Runs the text-recognition network that reads the USMS login captcha, using numpy
alone. The network is ddddocr's `common_old.onnx`, exported once by
`tools/export_captcha_model.py` into `graph.json` (the node list) and
`weights.npz` (the initializers), with its 8210 output classes cut down to the CTC
blank plus a-z0-9 - the only characters USMS draws.

onnxruntime would run the original file directly, but it publishes no musllinux
wheels, and Home Assistant OS is Alpine. This interpreter covers exactly the 17
operator types that graph uses, and nothing else.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np

MODEL_DIR = Path(__file__).parent

# The network was trained on 64 px high input; width scales with the aspect ratio.
INPUT_HEIGHT = 64

# ONNX `Cast` target codes used by the graph.
_CAST_TYPES = {1: np.float32, 6: np.int32}


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _dynamic_quantize_linear(x: np.ndarray) -> tuple[np.ndarray, np.float32, np.uint8]:
    """ONNX DynamicQuantizeLinear: quantize to uint8 over a range that includes zero."""
    low, high = min(0.0, float(x.min())), max(0.0, float(x.max()))
    scale = np.float32((high - low) / 255.0) if high > low else np.float32(1.0)
    zero_point = np.uint8(np.clip(np.rint(-low / scale), 0, 255))
    quantized = np.clip(np.rint(x / scale) + zero_point, 0, 255).astype(np.uint8)
    return quantized, scale, zero_point


def _conv2d(x: np.ndarray, w: np.ndarray, pads: list[int], strides: list[int]) -> np.ndarray:
    """
    Return a group-1 2D convolution of `x` [1, C, H, W] with `w` [M, C, kh, kw].

    Done as one matrix product over an im2col buffer. Integer convolutions are fed
    in as float64 with their zero points already removed: numpy has no BLAS for
    integer matmul, and float64 represents every int32 accumulator exactly.
    """
    channels = x.shape[1]
    out_channels, _, kh, kw = w.shape
    x = np.pad(x, ((0, 0), (0, 0), (pads[0], pads[2]), (pads[1], pads[3])))
    out_h = (x.shape[2] - kh) // strides[0] + 1
    out_w = (x.shape[3] - kw) // strides[1] + 1

    cols = np.empty((channels, kh, kw, out_h, out_w), dtype=x.dtype)
    for i in range(kh):
        for j in range(kw):
            cols[:, i, j] = x[
                0,
                :,
                i : i + strides[0] * out_h : strides[0],
                j : j + strides[1] * out_w : strides[1],
            ]

    product = w.reshape(out_channels, -1) @ cols.reshape(channels * kh * kw, -1)
    return product.reshape(1, out_channels, out_h, out_w)


def _lstm(  # noqa: PLR0913, PLR0917
    x: np.ndarray,
    w: np.ndarray,
    r: np.ndarray,
    b: np.ndarray,
    h0: np.ndarray,
    c0: np.ndarray,
    hidden: int,
) -> np.ndarray:
    """
    Return the outputs [seq, directions, batch, hidden] of a bidirectional LSTM.

    This is onnxruntime's DynamicQuantizeLSTM run on dequantized weights. Unlike the
    standard ONNX LSTM its weights are stored transposed - W [D, input, 4H] and
    R [D, H, 4H] - with the gates in i, o, f, c order. The onnxruntime kernel also
    re-quantizes activations each step; skipping that moves the logits by a few
    tenths at most, and has not changed a recognised character in testing.
    """
    seq_len = x.shape[0]
    directions = []
    for d in range(w.shape[0]):
        h, c = h0[d], c0[d]
        bias = b[d, : 4 * hidden] + b[d, 4 * hidden :]
        steps = range(seq_len) if d == 0 else range(seq_len - 1, -1, -1)
        outputs: list[np.ndarray] = [np.empty(0)] * seq_len
        for t in steps:
            gates = x[t] @ w[d] + h @ r[d] + bias
            i, o, f, g = (gates[:, k * hidden : (k + 1) * hidden] for k in range(4))
            c = _sigmoid(f) * c + _sigmoid(i) * np.tanh(g)
            h = _sigmoid(o) * np.tanh(c)
            outputs[t] = h
        directions.append(np.stack(outputs))
    return np.stack(directions, axis=1)


class CaptchaModel:
    """The exported recognition network, evaluated node by node."""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        """Load the node list, initializers and output charset."""
        graph = json.loads((model_dir / "graph.json").read_text(encoding="utf-8"))
        self.nodes: list[dict[str, Any]] = graph["nodes"]
        self.input_name: str = graph["input"]
        self.output_name: str = graph["output"]
        self.charset: list[str] = graph["charset"]

        # npz keys cannot hold ':', which several ONNX tensor names contain.
        with np.load(model_dir / "weights.npz") as weights:
            self.weights = {key.replace("__", ":"): weights[key] for key in weights.files}

    def logits(self, image: np.ndarray) -> np.ndarray:
        """Return the per-timestep class scores [seq, classes] for a [1, 1, 64, W] image."""
        values: dict[str, Any] = dict(self.weights)
        values[self.input_name] = image
        values[""] = None  # ONNX marks an omitted optional input with an empty name.

        for node in self.nodes:
            inputs = [values.get(name) for name in node["in"]]
            outputs = self._evaluate(node["op"], node["attr"], inputs)
            values.update(zip(node["out"], outputs, strict=False))

        return np.asarray(values[self.output_name]).reshape(-1, len(self.charset))

    def decode(self, image: np.ndarray) -> str:
        """Return the text in an image, by greedy CTC decoding of its logits."""
        text, previous = [], 0
        for index in self.logits(image).argmax(axis=1):
            if index not in (previous, 0):
                text.append(self.charset[index])
            previous = index
        return "".join(text)

    @staticmethod
    def _evaluate(op: str, attr: dict[str, Any], i: list[Any]) -> tuple[Any, ...]:  # noqa: C901, PLR0911, PLR0912
        """Evaluate one node; the operator set is exactly what the exported graph uses."""
        if op == "DynamicQuantizeLinear":
            return _dynamic_quantize_linear(i[0])
        if op == "Mul":
            return (i[0] * i[1],)
        if op == "Div":
            return (i[0] / i[1],)
        if op == "Add":
            return (i[0] + i[1],)
        if op == "Floor":
            return (np.floor(i[0]),)
        if op == "Sigmoid":
            return (_sigmoid(i[0]),)
        if op == "Cast":
            return (np.asarray(i[0]).astype(_CAST_TYPES[attr["to"]]),)
        if op == "Reshape":
            # A 0 in the target shape copies that dimension from the input.
            shape = [
                s if s != 0 else i[0].shape[k] for k, s in enumerate(np.asarray(i[1]).tolist())
            ]
            return (np.reshape(i[0], shape),)
        if op == "Transpose":
            return (np.transpose(i[0], attr["perm"]),)
        if op == "Shape":
            return (np.array(i[0].shape, dtype=np.int64),)
        if op == "Gather":
            return (np.take(i[0], i[1], axis=attr.get("axis", 0)),)
        if op == "Unsqueeze":
            return (np.expand_dims(i[0], tuple(attr["axes"])),)
        if op == "Concat":
            return (np.concatenate([np.atleast_1d(t) for t in i], axis=attr["axis"]),)
        if op == "ConstantOfShape":
            return (np.full(tuple(np.asarray(i[0]).tolist()), attr["value"][0], dtype=np.float32),)
        if op == "ConvInteger":
            x = i[0].astype(np.float64) - float(i[2])
            w = i[1].astype(np.float64) - float(i[3])
            return (np.rint(_conv2d(x, w, attr["pads"], attr["strides"])).astype(np.int32),)
        if op == "MatMulInteger":
            a = i[0].astype(np.float64) - float(i[2])
            b = i[1].astype(np.float64) - float(i[3])
            return (np.rint(a @ b).astype(np.int32),)
        if op == "DynamicQuantizeLSTM":
            x, wq, rq, bias, _, h0, c0, _, w_scale, w_zero, r_scale, r_zero = i
            w = (wq.astype(np.float32) - w_zero[:, None, None]) * w_scale[:, None, None]
            r = (rq.astype(np.float32) - r_zero[:, None, None]) * r_scale[:, None, None]
            y = _lstm(x, w, r, bias, h0, c0, attr["hidden_size"])
            return (y, y[-1], None)
        msg = f"Operator {op} is not supported by the captcha model."
        raise NotImplementedError(msg)
