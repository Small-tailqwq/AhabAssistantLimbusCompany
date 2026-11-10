"""Compare map ONNX models against reviewed annotations using production pixels."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


def overlap(a, b):
    intersection = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(
        0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return intersection / (a[2] * a[3] + b[2] * b[3] - intersection)


def detect(session, image):
    height, width = image.shape[:2]
    length = max(height, width)
    square = np.zeros((length, length, 3), dtype=np.uint8)
    square[:height, :width] = image
    resized = cv2.resize(square, (640, 640), interpolation=cv2.INTER_LINEAR)
    tensor = np.ascontiguousarray(resized.transpose(2, 0, 1)[None], dtype=np.float32)
    tensor *= np.float32(1 / 255)
    started = time.perf_counter()
    raw = session.run(None, {session.get_inputs()[0].name: tensor})[0]
    elapsed = (time.perf_counter() - started) * 1000
    if raw.ndim != 3 or raw.shape[:2] != (1, 11):
        message = f"Expected [1,11,N], received {raw.shape}"
        raise ValueError(message)
    raw = raw[0]
    classes = raw[4:].argmax(axis=0)
    scores = raw[4:].max(axis=0)
    candidates = []
    for index in np.flatnonzero(np.isfinite(scores) & (scores >= .25)):
        x, y, w, h = raw[:4, index].astype(np.float64) * (length / 640)
        if not np.isfinite([x, y, w, h]).all() or w <= 0 or h <= 0:
            continue
        if not (0 <= int(x) < width and 0 <= int(y) < height):
            continue
        candidates.append(dict(classId=int(classes[index]), score=float(scores[index]),
                               center=[int(x), int(y)], bounds=[int(x - w / 2), int(y - h / 2), int(w), int(h)]))
    kept = []
    for candidate in sorted(candidates, key=lambda item: -item["score"]):
        if not any(overlap(candidate["bounds"], previous["bounds"]) > .4 for previous in kept):
            kept.append(candidate)
    return kept, elapsed


def evaluate(predictions, objects):
    available = set(range(len(objects)))
    matches = []
    false_positives = []
    for prediction in predictions:
        candidates = [(overlap(prediction["bounds"], objects[index]["bounds"]), index)
                      for index in available if prediction["classId"] == objects[index]["classId"]]
        score, index = max(candidates, default=(0, -1))
        if score >= .5:
            available.remove(index)
            matches.append(dict(prediction=prediction, annotation=objects[index], iou=score))
        else:
            false_positives.append(prediction)
    return dict(tp=len(matches), fp=len(false_positives), fn=len(available), matches=matches,
                falsePositives=false_positives, misses=[objects[index] for index in sorted(available)])


def summarize(rows):
    totals = {key: sum(row["evaluation"][key] for row in rows) for key in ["tp", "fp", "fn"]}
    totals["precision"] = totals["tp"] / (totals["tp"] + totals["fp"]) if totals["tp"] + totals["fp"] else 0
    totals["recall"] = totals["tp"] / (totals["tp"] + totals["fn"]) if totals["tp"] + totals["fn"] else 0
    per_class = []
    for kind in range(7):
        tp = sum(sum(match["annotation"]["classId"] == kind for match in row["evaluation"]["matches"]) for row in rows)
        fp = sum(sum(item["classId"] == kind for item in row["evaluation"]["falsePositives"]) for row in rows)
        fn = sum(sum(item["classId"] == kind for item in row["evaluation"]["misses"]) for row in rows)
        per_class.append(dict(classId=kind, tp=tp, fp=fp, fn=fn))
    return dict(images=len(rows), **totals, perClass=per_class)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--old", type=Path, default=Path("assets/model/best.onnx"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.drive.casefold() == "c:":
        message = "Evaluation output must be outside the C drive"
        raise ValueError(message)
    output.mkdir(parents=True, exist_ok=True)
    report = dict(confidence=.25, nms=dict(classAgnostic=True, iou=.4), matching=dict(sameClass=True, iou=.5),
                  preprocessing="Original BGR; top-left zero square; OpenCV LINEAR 640; float32 multiply 1/255",
                  scope="Original full images; declared trainingRegion restricts scoring only; no bus-side filtering", models={})
    for model_name, model_path in [("old", args.old), ("candidate", args.candidate)]:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        model = dict(path=str(model_path.resolve()), sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(), splits={})
        for split in ["train", "validation", "acceptance"]:
            rows = []
            for annotation in sorted((args.annotations / ("annotations-" + split)).glob("*.json")):
                data = json.loads(annotation.read_text(encoding="utf-8-sig"))
                if data["annotationStatus"] != "reviewed":
                    continue
                image_path = annotation.parent / data["image"]
                if hashlib.sha256(image_path.read_bytes()).hexdigest() != data["sha256"]:
                    message = f"Image SHA256 mismatch: {image_path}"
                    raise ValueError(message)
                image = cv2.imread(str(image_path))
                if image is None or image.shape[:2] != (data["height"], data["width"]):
                    message = f"Image dimensions mismatch: {image_path}"
                    raise ValueError(message)
                predictions, elapsed = detect(session, image)
                scoring = predictions
                if region := data.get("trainingRegion"):
                    scoring = [p for p in predictions if region["x"] <= p["center"][0] < region["x"] + region["width"]
                               and region["y"] <= p["center"][1] < region["y"] + region["height"]]
                objects = [dict(classId=obj["classId"], bounds=[obj["bounds"][key] for key in ["x", "y", "width", "height"]])
                           for obj in data["objects"]]
                rows.append(dict(annotation=str(annotation), image=str(image_path), sceneGroup=data["sceneGroup"],
                                 evaluationRegion=data.get("trainingRegion"), predictions=predictions,
                                 inferenceMilliseconds=elapsed, evaluation=evaluate(scoring, objects)))
            model["splits"][split] = dict(summary=summarize(rows), images=rows)
            sys.stdout.write(json.dumps(dict(model=model_name, split=split, **summarize(rows))) + "\n")
        report["models"][model_name] = model
    (output / "detection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
