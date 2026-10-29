"""Compare .NET matching and crop recognition against the production Python stages.

Writes private screenshots and reports only below logs/dotnet_milestone_debug/vision.
No screen capture, game input, or user configuration writes are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, default=ROOT / "dotnet/src/AALC.Cli/bin/Debug/net10.0-windows/AAALC.Cli.dll")
    parser.add_argument("--skip-ocr", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    output = ROOT / "logs/dotnet_milestone_debug/vision" / uuid.uuid4().hex[:12]
    profile = output / "profile"
    profile.mkdir(parents=True)

    import module

    for name, relative in {
        "CONFIG_PATH": "config.yaml", "CONFIG_BACKUP_PATH": "config_backup",
        "THEME_PACK_LIST_PATH": "theme_pack_list.yaml", "THEME_PACK_WEIGHT_PATH": "theme_pack_weight", "LOG_DIR": "logs",
    }.items():
        setattr(module, name, str(profile / relative))
    source = ROOT / "config.yaml"
    shutil.copy2(source if source.exists() else ROOT / module.EXAMPLE_PATH, profile / "config.yaml")

    import cv2
    import numpy as np
    from PIL import Image

    from module.config import cfg
    from utils.image_utils import ImageUtils
    from utils.path_manager import path_manager

    cfg.set_save_suspended(True, source="dotnet-vision-reference")
    path_manager.initialize_paths()

    def command(*arguments):
        result = subprocess.run(["dotnet", str(args.cli.resolve()), *map(str, arguments)],
                                capture_output=True, text=True, encoding="utf-8", timeout=90)
        if result.returncode:
            message = f"CLI failed ({result.returncode}): {result.stderr}"
            raise RuntimeError(message)
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def load(key, selected, height):
        cfg.unsaved_set_value("set_win_size", height)
        template = ImageUtils.load_from_specific_path(key, selected)
        bbox = None
        if key.endswith("assets.png"):
            bbox = ImageUtils.get_bbox(template)
            template = ImageUtils.crop(template, bbox)
        return template, bbox

    matches = []

    def compare(path, key, language="zh_cn", theme="default", kind="real"):
        with Image.open(path) as image:
            screen = np.array(image.convert("L"))
        path_manager.set_theme(theme)
        path_manager.set_language(language)
        candidates = ImageUtils.existing_image_paths(key)
        actual = command("match", path, key, ROOT, language, theme)
        for row in actual:
            mode = row["mode"].lower()
            references = []
            for selected in candidates:
                template, bbox = load(key, selected, screen.shape[0])
                center, score = ImageUtils.match_template(screen, template, bbox, mode)
                png = ROOT / "assets/images" / selected / key
                resolved = Path(ImageUtils.resolve_asset_path(str(png)))
                references.append({"path": resolved.relative_to(ROOT / "assets/images").as_posix(),
                                   "score": score, "center": list(map(int, center)) if center is not None else None,
                                   "bounds": list(map(int, bbox)) if bbox is not None else None})
            reference = max(references, key=lambda r: r["score"])
            value = row["match"]
            center = value["center"]
            center = [center["x"], center["y"]] if center is not None else None
            error = abs(reference["score"] - value["score"])
            passed = error <= 1e-5 and center == reference["center"] and value["path"] == reference["path"] and value["bounds"] == reference["bounds"]
            matches.append({"sample": str(path.relative_to(ROOT)), "kind": kind, "key": key,
                            "language": language, "theme": theme, "scale": screen.shape[0] / 1440,
                            "mode": mode, "python": reference, "dotnet": value,
                            "scoreAbsoluteError": error, "passed": passed})

    home = ROOT / "logs/daily_validation_debug/2026-09-27-final-home.png"
    daily = ROOT / "logs/daily_validation_debug/2026-09-27-daily-unclaimed.png"
    mirror = ROOT / "logs/daily_validation_debug/2026-09-27-mirror-clear.png"
    keys = ["home/mail_assets.png", "mail/claim_all_assets.png", "mail/get_mail_prize_confirm.png", "mail/close_assets.png"]
    for screenshot in (home, daily, mirror):
        for key in keys:
            compare(screenshot, key)
    for language, theme in (("en", "default"), ("zh_cn", "dark"), ("en", "dark")):
        for key in keys:
            compare(home, key, language, theme, "path-selection")
    original = cv2.imread(str(home))
    for height in (360, 1440, 1800):
        path = output / f"home-{height}.png"
        cv2.imwrite(str(path), cv2.resize(original, None, fx=height / 720, fy=height / 720,
                                        interpolation=cv2.INTER_AREA if height < 720 else cv2.INTER_LINEAR))
        for key in (keys[0], keys[1]):
            compare(path, key, kind="resized-real")

    path_manager.set_theme("default")
    path_manager.set_language("zh_cn")
    for height in (360, 720, 1440, 1800):
        template, bbox = load(keys[0], "default/share", height)
        margin = max(30, int(30 * height / 1440))
        normal_margin = max(100, int(100 * height / 1440))
        for offset in (0, -margin, -margin - 1, -normal_margin, -normal_margin - 1):
            canvas = np.random.default_rng(17).integers(0, 32, (height, round(height * 16 / 9)), dtype=np.uint8)
            x, y = int(bbox[0]) + offset, int(bbox[1])
            canvas[y:y + template.shape[0], x:x + template.shape[1]] = template
            path = output / f"boundary-{height}-{offset}.png"
            cv2.imwrite(str(path), canvas)
            compare(path, keys[0], kind="synthetic-search-boundary")

    recognition = []
    models = ROOT / ".venv/Lib/site-packages/rapidocr/models"
    model = models / "ch_PP-OCRv4_rec_infer.onnx"
    dictionary = models / "ppocr_keys_v1.txt"
    if not args.skip_ocr:
        from rapidocr.ch_ppocr_rec.typings import TextRecInput

        from module.ocr import ocr

        recognizer = ocr.engine.text_rec
        crops = [(home, (952, 641, 1009, 668), "驾驶席"),
                 (home, (1028, 639, 1085, 668), "放映室"),
                 (daily, (179, 40, 293, 77), "战斗通行证"),
                 (daily, (411, 285, 557, 316), "清剿经验采光1次"),
                 (daily, (411, 548, 535, 578), "击败10个敌人")]
        for index, (source_path, bounds, expected) in enumerate(crops):
            with Image.open(source_path) as image:
                crop = image.convert("RGB").crop(bounds)
            path = output / f"text-{index}.png"
            crop.save(path)
            gray = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2GRAY)
            if len(np.unique(gray)) > 2:
                gray = cv2.createCLAHE(clipLimit=2, tileGridSize=(8, 8)).apply(gray)
            bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            python = recognizer(TextRecInput(img=bgr))
            norm = recognizer.resize_norm_img(bgr, max(320 / 48, bgr.shape[1] / bgr.shape[0]))[None]
            logits = recognizer.session(norm)
            tokens = logits.argmax(axis=2)[0]
            probs = logits.max(axis=2)[0]
            dotnet = command("recognize", path, model, dictionary)[0]
            error = float(np.max(np.abs(probs - np.array(dotnet["probabilities"]))))
            passed = (dotnet["text"] == python.txts[0] and dotnet["inputShape"] == list(norm.shape)
                      and dotnet["tokens"] == tokens.tolist() and abs(dotnet["score"] - python.scores[0]) <= 1e-5 and error <= 1e-4)
            recognition.append({"sample": str(path.relative_to(ROOT)), "source": str(source_path.relative_to(ROOT)),
                                "crop": bounds, "expected": expected, "python": {"text": python.txts[0], "score": python.scores[0]},
                                "dotnet": dotnet, "maxProbabilityAbsoluteError": error, "passed": passed,
                                "correctText": dotnet["text"] == expected})

    report = {"templateScope": "Production ImageUtils resource selection, resize, bbox/crop and match_template; Pillow grayscale screenshot path. Highest-score candidate for diagnostics.",
              "ocrScope": "One horizontal crop per inference; OCR.run grayscale/CLAHE, RapidOCR text_rec resize, local PP-OCRv4 rec ONNX and CTC. Detection, angle classification and word boxes are not ported or compared.",
              "versions": {"opencvPython": cv2.__version__},
              "modelSha256": hashlib.sha256(model.read_bytes()).hexdigest() if not args.skip_ocr else None,
              "matches": matches, "recognition": recognition,
              "summary": {"matchCases": len(matches), "matchPassed": sum(r["passed"] for r in matches),
                          "maxScoreAbsoluteError": max(r["scoreAbsoluteError"] for r in matches),
                          "recognitionCases": len(recognition), "recognitionPassed": sum(r["passed"] for r in recognition),
                          "recognitionCorrectText": sum(r["correctText"] for r in recognition)}}
    report_path = output / "comparison.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(json.dumps({"report": str(report_path), **report["summary"]}, ensure_ascii=False) + "\n")
    return 0 if all(r["passed"] for r in matches + recognition) else 1


if __name__ == "__main__":
    raise SystemExit(main())
