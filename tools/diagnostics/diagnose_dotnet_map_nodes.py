"""Inspect raw mirror-map ONNX predictions without capturing or controlling the game."""

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--model", type=Path, default=Path("assets/model/best.onnx"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.drive.casefold() == "c:":
        message = "Diagnostic output must be outside the C drive"
        raise ValueError(message)
    output.mkdir(parents=True, exist_ok=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(args.model), options, providers=["CPUExecutionProvider"])
    metadata = session.get_modelmeta().custom_metadata_map
    names = ast.literal_eval(metadata["names"])
    report = {
        "model": str(args.model.resolve()),
        "sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "metadata": metadata,
        "names": names,
        "images": [],
    }
    for path in args.images:
        source = cv2.imread(str(path))
        if source is None:
            message = f"Cannot read {path}"
            raise ValueError(message)
        variants = [("original", source, 0, 0)]
        for gamma in [0.6, 0.4]:
            table = np.uint8(np.power(np.arange(256) / 255.0, gamma) * 255)
            variants.append((f"gamma-{gamma}", cv2.LUT(source, table), 0, 0))
        variants.append(("linear-2", cv2.convertScaleAbs(source, alpha=2), 0, 0))
        lab = cv2.cvtColor(source, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = cv2.createCLAHE(2, (8, 8)).apply(lab[:, :, 0])
        variants.append(("clahe", cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), 0, 0))
        for width in [960, 640]:
            for x in [0, source.shape[1] - width]:
                crop = source[80 : min(source.shape[0], 80 + width), x : x + width]
                variants.append((f"tile-{width}-{x}", crop, x, 80))
                table = np.uint8(np.power(np.arange(256) / 255.0, 0.5) * 255)
                variants.append((f"tile-{width}-{x}-gamma", cv2.LUT(crop, table), x, 80))
        result = {"path": str(path), "shape": list(source.shape), "variants": []}
        raw_arrays = {}
        for name, image, offset_x, offset_y in variants:
            length = max(image.shape[:2])
            square = np.zeros((length, length, 3), dtype=np.uint8)
            square[: image.shape[0], : image.shape[1]] = image
            resized = cv2.resize(square, (640, 640))
            tensor = np.ascontiguousarray(resized.transpose(2, 0, 1)[None], dtype=np.float32) / 255
            raw = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
            raw_arrays[name] = raw
            scores = raw[4:].max(axis=0)
            classes = raw[4:].argmax(axis=0)
            ratio = length / 640
            ranked = []
            for index in scores.argsort()[::-1][:100]:
                ranked.append(
                    {
                        "score": float(scores[index]),
                        "kind": names[int(classes[index])],
                        "center": [float(raw[0, index] * ratio + offset_x), float(raw[1, index] * ratio + offset_y)],
                        "size": [float(raw[2, index] * ratio), float(raw[3, index] * ratio)],
                    }
                )
            summary = {"name": name, "raw_above_025": int(np.count_nonzero(scores >= 0.25)), "top": ranked}
            result["variants"].append(summary)
            sys.stdout.write(
                json.dumps(
                    {"image": path.name, "variant": name, "raw_above_025": summary["raw_above_025"], "best": ranked[0]},
                    ensure_ascii=False,
                )
                + "\n"
            )
            sys.stdout.flush()
        report["images"].append(result)
        np.savez_compressed(output / f"{path.stem}-raw.npz", **raw_arrays)
    (output / "raw-predictions.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
