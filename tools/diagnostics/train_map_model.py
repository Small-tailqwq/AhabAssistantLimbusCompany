"""Prepare reviewed map labels, or explicitly train/export an isolated candidate on D:."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np

NAMES = ["battle", "boss_battle", "event", "hard_battle", "hard_battle_2", "shop", "small_boss_battle"]
TRAINING = {
    "epochs": 120, "batch": 4, "workers": 0, "device": 0, "freeze": 10,
    "imgsz": 640, "seed": 20261026, "deterministic": True,
    "mosaic": 0.0, "fliplr": 0.0, "flipud": 0.0, "degrees": 0.0,
    "scale": 0.15, "translate": 0.1, "hsv_h": 0.0, "bgr": 0.0,
    "amp": False, "rect": False, "multi_scale": False,
}
CONTRACT = (
    "Crop trainingRegion when present, place BGR pixels at the top left of a zero-filled square, "
    "then resize to 640x640 with OpenCV INTER_LINEAR. Save the training PNG with red/blue "
    "channels exchanged: Ultralytics' BGR-to-RGB loader then yields the production BGR CHW tensor. "
    "Labels use the same crop offset and square normalization. Color/geometric training augmentations "
    "operate after this base preprocessing; bgr=0 preserves the loader conversion."
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def d_path(path: Path) -> Path:
    path = path.resolve()
    require(path.drive.lower() == "d:", f"Output must be on D: {path}")
    return path


def load_annotations(directory: Path) -> tuple[list[dict], list[str]]:
    records, ignored = [], []
    for annotation in sorted(directory.resolve().glob("*.json")):
        data = json.loads(annotation.read_text(encoding="utf-8-sig"))
        if data.get("annotationStatus") != "reviewed":
            ignored.append(str(annotation))
            continue
        image = (annotation.parent / data["image"]).resolve()
        image_sha = sha(image)
        require(image_sha == data["sha256"], f"Image SHA mismatch: {annotation}")
        require(bool(data.get("sceneGroup")), f"Missing sceneGroup: {annotation}")
        require(isinstance(data.get("objects"), list), f"Missing reviewed objects: {annotation}")
        records.append({"annotation": str(annotation), "annotationSha256": sha(annotation),
                        "image": str(image), "imageSha256": image_sha,
                        "source": data["source"], "sceneGroup": data["sceneGroup"], "data": data})
    require(bool(records), f"No reviewed annotations: {directory}")
    return records, ignored


def production_pixels(record: dict) -> tuple[np.ndarray, list[str], dict]:
    data = record["data"]
    image = cv2.imread(record["image"])
    require(image is not None, f"Cannot read image: {record['image']}")
    height, width = image.shape[:2]
    require((width, height) == (data["width"], data["height"]), f"Image dimensions mismatch: {record['image']}")
    region = data.get("trainingRegion", {"x": 0, "y": 0, "width": width, "height": height})
    x, y, w, h = (region[key] for key in ("x", "y", "width", "height"))
    require(all(isinstance(value, int) for value in (x, y, w, h)) and
            x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height,
            f"Invalid trainingRegion: {record['annotation']}")
    length = max(w, h)
    square = np.zeros((length, length, 3), dtype=np.uint8)
    square[:h, :w] = image[y:y + h, x:x + w]
    pixels = cv2.resize(square, (640, 640), interpolation=cv2.INTER_LINEAR)
    labels = []
    for obj in data["objects"]:
        class_id = obj["classId"]
        require(isinstance(class_id, int) and 0 <= class_id < len(NAMES) and
                obj["className"] == NAMES[class_id], f"Class order mismatch: {record['annotation']}")
        bounds = obj["bounds"]
        bx, by, bw, bh = (bounds[key] for key in ("x", "y", "width", "height"))
        bx, by = bx - x, by - y
        require(bw > 0 and bh > 0 and bx >= 0 and by >= 0 and bx + bw <= w and by + bh <= h,
                f"Object is outside trainingRegion: {record['annotation']}")
        labels.append(f"{class_id} {(bx + bw / 2) / length:.10f} {(by + bh / 2) / length:.10f} {bw / length:.10f} {bh / length:.10f}")
    return pixels, labels, region


def check_loader(records: list[dict], output: Path) -> dict:
    from ultralytics.cfg import get_cfg
    from ultralytics.data.dataset import YOLODataset

    differences = []
    for split in ("train", "val"):
        dataset = YOLODataset(img_path=str(output / "images" / split), imgsz=640, augment=False,
                              data={"names": dict(enumerate(NAMES)), "nc": len(NAMES)}, hyp=get_cfg(), rect=False)
        by_image = {record["preparedImage"]: record for record in records if record["split"] == split}
        require(len(dataset) == len(by_image), f"Ultralytics rejected images in {split}")
        for index in range(len(dataset)):
            sample = dataset[index]
            record = by_image[str(Path(sample["im_file"]).resolve())]
            expected, _, _ = production_pixels(record)
            expected_chw = expected.transpose(2, 0, 1)
            actual = sample["img"].numpy()
            byte_difference = int(np.abs(actual.astype(np.int16) - expected_chw.astype(np.int16)).max())
            float_difference = float(np.abs(actual.astype(np.float32) / 255 -
                                             expected_chw.astype(np.float32) * np.float32(1 / 255)).max())
            require(byte_difference == 0 and float_difference <= 1e-7,
                    f"Production/Ultralytics pixel mismatch: {record['image']}")
            require(len(sample["cls"]) == len(record["data"]["objects"]),
                    f"Ultralytics rejected labels: {record['annotation']}")
            differences.append({"image": record["preparedImage"], "maxByteDifference": byte_difference,
                                "maxFloatDifference": float_difference})
    return {"contract": CONTRACT, "images": differences}


def prepare(train: Path, val: Path, output: Path, checkpoint: Path, fused_checkpoint: bool = False) -> dict:
    output = d_path(output)
    require(not output.exists(), f"Output already exists: {output}")
    checkpoint = checkpoint.resolve()
    d_path(checkpoint)
    checkpoint_sha = sha(checkpoint)
    train_records, train_ignored = load_annotations(train)
    val_records, val_ignored = load_annotations(val)
    for key in ("sceneGroup", "imageSha256"):
        overlap = {row[key] for row in train_records} & {row[key] for row in val_records}
        require(not overlap, f"Train/val overlap in {key}: {sorted(overlap)}")
    records = []
    for split, source_records in (("train", train_records), ("val", val_records)):
        for record in source_records:
            pixels, labels, region = production_pixels(record)
            image = output / "images" / split / f"{Path(record['annotation']).stem}.png"
            label = output / "labels" / split / image.with_suffix(".txt").name
            image.parent.mkdir(parents=True, exist_ok=True)
            label.parent.mkdir(parents=True, exist_ok=True)
            # Production consumes BGR; undo the RGB conversion in Ultralytics Format.
            require(cv2.imwrite(str(image), pixels[:, :, ::-1]), f"Could not write PNG: {image}")
            label.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")
            records.append({**record, "split": split, "trainingRegion": region,
                            "preparedImage": str(image), "preparedImageSha256": sha(image),
                            "preparedLabel": str(label), "preparedLabelSha256": sha(label)})
    prepared_overlap = {r["preparedImageSha256"] for r in records if r["split"] == "train"} & {
        r["preparedImageSha256"] for r in records if r["split"] == "val"}
    require(not prepared_overlap, "Train/val prepared image overlap")
    dataset = {"path": str(output), "train": "images/train", "val": "images/val", "names": dict(enumerate(NAMES))}
    import yaml

    (output / "data.yaml").write_text(yaml.safe_dump(dataset, allow_unicode=True, sort_keys=False), encoding="utf-8")
    pixel_check = check_loader(records, output)
    config = {**TRAINING, "data": str(output / "data.yaml"), "project": str(output / "runs"), "name": "candidate"}
    write_json(output / "training-config.json", config)
    manifest = {"preprocessingContract": CONTRACT, "classes": NAMES, "checkpoint": str(checkpoint),
                "initializationMode": "quantized-weight-restored-fused" if fused_checkpoint else "official-checkpoint",
                "checkpointSha256": checkpoint_sha, "scriptSha256": sha(Path(__file__)),
                "versions": {name: version(name) for name in ("torch", "torchvision", "ultralytics", "opencv-python")},
                "records": records, "ignoredAnnotations": train_ignored + val_ignored,
                "trainingConfigSha256": sha(output / "training-config.json"), "datasetYamlSha256": sha(output / "data.yaml"),
                "pixelCheck": pixel_check,
                "counts": {split: dict(Counter(NAMES[obj["classId"]] for r in records if r["split"] == split
                                                 for obj in r["data"]["objects"])) for split in ("train", "val")}}
    write_json(output / "manifest.json", manifest)
    return manifest


def train_candidate(output: Path) -> dict:
    import onnx
    from ultralytics import YOLO

    output = d_path(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in (("training-config.json", manifest["trainingConfigSha256"]),
                           ("data.yaml", manifest["datasetYamlSha256"])):
        require(sha(output / name) == expected, f"Prepared configuration changed: {name}")
    require(sha(Path(manifest["checkpoint"])) == manifest["checkpointSha256"], "Checkpoint changed")
    for record in manifest["records"]:
        for path_key, sha_key in (("annotation", "annotationSha256"), ("image", "imageSha256"),
                                  ("preparedImage", "preparedImageSha256"), ("preparedLabel", "preparedLabelSha256")):
            require(sha(Path(record[path_key])) == record[sha_key], f"Prepared input changed: {record[path_key]}")
    config = json.loads((output / "training-config.json").read_text(encoding="utf-8"))
    require(not (output / "runs" / "candidate").exists(), "Candidate run already exists")
    model = YOLO(manifest["checkpoint"])
    if manifest.get("initializationMode") == "quantized-weight-restored-fused":
        import torch
        from ultralytics.models.yolo.detect import DetectionTrainer

        original = {key: value.detach().cpu().clone() for key, value in model.model.state_dict().items()}
        original_biases = {name for name, module in model.model.named_modules()
                           if isinstance(module, torch.nn.Conv2d) and module.bias is not None}

        def verify_fused(network: torch.nn.Module) -> dict:
            state = network.state_dict()
            require(not any(isinstance(module, torch.nn.modules.batchnorm._BatchNorm)
                            for module in network.modules()), "Fused initialization contains BatchNorm")
            require(set(state) == set(original), "Fused initialization state keys changed")
            require(all(torch.equal(value.detach().cpu(), original[key]) for key, value in state.items()),
                    "Fused initialization parameter values changed")
            biases = {name for name, module in network.named_modules()
                      if isinstance(module, torch.nn.Conv2d) and module.bias is not None}
            require(biases == original_biases, "Fused convolution biases changed")
            return {"stateEntries": len(state), "biasedConvolutions": len(biases), "batchNormModules": 0,
                    "exactStateMatch": True}

        verify_fused(model.model)

        class FusedDetectionTrainer(DetectionTrainer):
            def get_model(self, cfg=None, weights=None, verbose=True):
                require(weights is not None, "Fused trainer requires the restored model")
                # Default get_model creates an unfused network and drops fused convolution biases.
                network = deepcopy(weights).float()
                verify_fused(network)
                return network

        def check_training_initialization(trainer: DetectionTrainer) -> None:
            result = verify_fused(trainer.model)
            result["trainableParameters"] = sum(value.numel() for value in trainer.model.parameters() if value.requires_grad)
            write_json(output / "fused-initialization.json", result)

        model.add_callback("on_pretrain_routine_end", check_training_initialization)
    started = time.perf_counter()
    if manifest.get("initializationMode") == "quantized-weight-restored-fused":
        metrics = model.train(trainer=FusedDetectionTrainer, **config)
    else:
        metrics = model.train(**config)
    training = {"elapsedSeconds": time.perf_counter() - started, "parameters": config,
                "initializationMode": manifest.get("initializationMode", "official-checkpoint"),
                "validationMetrics": {key: float(value) for key, value in metrics.results_dict.items()},
                "epochsCompleted": model.trainer.epoch + 1}
    write_json(output / "training-result.json", training)
    best = output / "runs" / "candidate" / "weights" / "best.pt"
    started = time.perf_counter()
    exported = Path(YOLO(str(best)).export(format="onnx", imgsz=640, batch=1, dynamic=False,
                                          opset=12, nms=False, simplify=False, device="cpu"))
    graph = onnx.load(exported)
    onnx.checker.check_model(graph)
    input_shape = [d.dim_value for d in graph.graph.input[0].type.tensor_type.shape.dim]
    output_shape = [d.dim_value for d in graph.graph.output[0].type.tensor_type.shape.dim]
    require(input_shape == [1, 3, 640, 640] and output_shape == [1, 11, 8400],
            f"Unexpected ONNX shapes: {input_shape} -> {output_shape}")
    require(next(item.version for item in graph.opset_import if item.domain in ("", "ai.onnx")) == 12,
            "Unexpected ONNX opset")
    report = {"bestCheckpoint": str(best), "bestCheckpointSha256": sha(best), "onnx": str(exported),
              "onnxSha256": sha(exported), "inputShape": input_shape, "outputShape": output_shape,
              "manifestSha256": sha(output / "manifest.json"), "training": training,
              "exportElapsedSeconds": time.perf_counter() - started, "opset": 12, "nms": False}
    write_json(output / "candidate.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Validate reviewed labels and create a new D: dataset; does not train")
    prep.add_argument("--train-annotations", type=Path, required=True)
    prep.add_argument("--val-annotations", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    initial = prep.add_mutually_exclusive_group(required=True)
    initial.add_argument("--checkpoint", type=Path, help="Official pretrained checkpoint")
    initial.add_argument("--fused-checkpoint", type=Path, help="Explicit quantized-weight-restored fused checkpoint")
    training = commands.add_parser("train", help="Explicitly train and export a previously prepared candidate")
    training.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        manifest = prepare(args.train_annotations, args.val_annotations, args.output,
                           args.fused_checkpoint or args.checkpoint, fused_checkpoint=args.fused_checkpoint is not None)
        summary = {"output": str(args.output.resolve()), "images": len(manifest["records"]), "counts": manifest["counts"]}
    else:
        summary = train_candidate(args.output)
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
