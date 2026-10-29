"""Collect pending map annotation samples from native recordings; never train on predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def read_events(path: Path, warnings: list[str]) -> list[dict]:
    lines = path.read_bytes().splitlines(keepends=True)
    events = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if index == len(lines) and not line.endswith((b"\n", b"\r")):
                warnings.append(f"{path}:{index}: ignored incomplete final line")
                break
            raise
    return events


def candidates(recording: Path, warnings: list[str]) -> list[dict]:
    """Keep the first/last suspect map in each consecutive suspect-map segment."""
    selected = []
    segment = []
    maps = []

    def finish() -> None:
        if segment:
            selected.append(segment[0])
            if len(segment) > 1:
                selected.append(segment[-1])
            segment.clear()

    for index, event in enumerate(read_events(recording / "events.jsonl", warnings), 1):
        if event.get("rule") != "mirror.route.map":
            continue
        prediction = json.loads(event["detail"])
        reasons = []
        if not any(edge["From"] == -1 for edge in prediction["Connections"]):
            reasons.append("no-bus-connection")
        if any(node["Kind"] in (7, "Unknown") for node in prediction["Nodes"]):
            reasons.append("unknown-node")
        observation = {
            "runId": event["runId"], "frameId": event["frameId"], "eventIndex": index,
            "source": str(recording / "events.jsonl"),
            "elapsedMilliseconds": event.get("elapsedMilliseconds"),
            "prediction": prediction, "predictionStatus": "pending", "triggerReasons": reasons,
        }
        maps.append(observation)
        if reasons:
            segment.append(observation)
        else:
            finish()
    finish()
    result_path = recording / "result.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if result.get("outcome") == "Failed" and "no-confirmed-connection" in result.get("reason", "") and maps:
            last = maps[-1]
            last["triggerReasons"].append("final-no-confirmed-connection")
            if last not in selected:
                selected.append(last)
    return selected


def collect(source: Path, output: Path, model: Path | None = None) -> dict:
    source, output = source.resolve(), output.resolve()
    if output.drive.lower() != "d:":
        raise ValueError("Sample output must be on D:")  # noqa: TRY003
    warnings: list[str] = []
    samples = {}
    model_hashes = set()
    recordings = sorted({path.parent for path in source.rglob("events.jsonl")})
    for recording in recordings:
        selected = candidates(recording, warnings)
        if not selected:
            continue
        identity_path = recording / "map-model.json"
        if identity_path.is_file():
            recorded = json.loads(identity_path.read_text(encoding="utf-8-sig"))
            identity = {key: recorded[key] for key in ("modelSha256", "modelSource", "modelIdentitySource")}
        elif model is not None:
            identity = {"modelSha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                        "modelSource": str(model.resolve()),
                        "modelIdentitySource": "provided-file-not-recorded-in-events"}
        else:
            raise ValueError(f"{recording}: map-model.json missing; provide --model")  # noqa: TRY003
        model_hashes.add(identity["modelSha256"])
        for observation in selected:
            image = recording / f"frame-{observation['frameId']:06d}.png"
            if not image.is_file():
                warnings.append(f"Missing source image: {image}")
                continue
            data = image.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            observation.update({"sourceImage": str(image), **identity})
            if sha not in samples:
                samples[sha] = {"data": data, "observations": []}
            samples[sha]["observations"].append(observation)
    output.mkdir(parents=True, exist_ok=True)
    for sha, sample in samples.items():
        image_path = output / f"{sha}.png"
        metadata_path = output / f"{sha}.json"
        if image_path.exists():
            if hashlib.sha256(image_path.read_bytes()).hexdigest() != sha:
                raise ValueError("Existing sample image does not match its SHA256 filename")  # noqa: TRY003
        else:
            with image_path.open("xb") as image_file:
                image_file.write(sample["data"])
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            metadata = {"imageSha256": sha, "image": image_path.name,
                        "annotationStatus": "pending", "observations": []}
        changed = not metadata_path.exists()
        for observation in sample["observations"]:
            if observation not in metadata["observations"]:
                metadata["observations"].append(observation)
                changed = True
        # Only observations are extended; human annotation fields remain untouched.
        if changed:
            temporary = metadata_path.with_suffix(".json.tmp")
            with temporary.open("x", encoding="utf-8") as metadata_file:
                json.dump(metadata, metadata_file, ensure_ascii=False, indent=2)
                metadata_file.write("\n")
            temporary.replace(metadata_path)
    return {"recordings": len(recordings), "uniqueSamples": len(samples),
            "selectedObservations": sum(len(item["observations"]) for item in samples.values()),
            "output": str(output), "modelSha256s": sorted(model_hashes), "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Recording directory or root containing recordings")
    parser.add_argument("--output", type=Path, required=True, help="Explicit D: sample output directory")
    parser.add_argument("--model", type=Path, help="Caller-associated model for recordings without map-model.json")
    args = parser.parse_args()
    summary = collect(args.source, args.output, args.model)
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
