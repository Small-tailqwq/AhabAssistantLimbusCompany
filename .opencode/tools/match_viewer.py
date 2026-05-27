#!/usr/bin/env python3
"""Match Viewer - Template matching diagnostic tool for AALC."""

import base64
import io
import json
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from module.config import cfg  # noqa: E402
from utils.image_utils import ImageUtils  # noqa: E402

PORT = 9813


class MatchViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent / "match_viewer"), **kwargs)

    def log_message(self, format, *args):
        print(f"[match_viewer] {args[0]}")  # noqa: T201

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg, status=400):
        self._send_json({"error": msg}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self.path = "/index.html"
            return super().do_GET()

        if path == "/api/categories":
            return self._handle_categories(params)
        if path == "/api/asset-image":
            return self._handle_asset_image(params)

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/match":
            return self._handle_match()
        self._send_error("Not found", 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_categories(self, params):
        theme = params.get("theme", ["default"])[0]
        lang = params.get("lang", ["en"])[0]
        win_size = int(params.get("win_size", ["720"])[0])

        scale = win_size / 1440.0

        categories = {}
        base_dir = PROJECT_ROOT / "assets" / "images"

        path_prefix = f"{theme}/{lang}"
        share_path = f"{theme}/share"

        for subdir in [share_path, path_prefix]:
            full_dir = base_dir / subdir
            if not full_dir.exists():
                continue
            for png_file in sorted(full_dir.rglob("*assets.png")):
                rel = str(png_file.relative_to(full_dir))
                category = str(Path(rel).parent).replace("\\", "/") or "root"
                key = f"{category}/{png_file.name}" if category != "root" else png_file.name

                img = cv2.imread(str(png_file), cv2.IMREAD_UNCHANGED)
                if img is None:
                    continue
                bbox = ImageUtils.get_bbox(img)
                scaled_bbox = [int(v * scale) for v in bbox]
                template_size = [
                    int((bbox[2] - bbox[0]) * scale),
                    int((bbox[3] - bbox[1]) * scale),
                ]
                entry = {
                    "key": key,
                    "path": subdir,
                    "bbox": scaled_bbox,
                    "size": template_size,
                }
                categories.setdefault(category, []).append(entry)

        categories = dict(sorted(categories.items()))
        for assets in categories.values():
            assets.sort(key=lambda a: a["key"])

        self._send_json({
            "categories": categories,
            "win_size": win_size,
            "theme": theme,
            "lang": lang,
        })

    def _handle_asset_image(self, params):
        key = params.get("key", [None])[0]
        path_str = params.get("path", [None])[0]
        use_bbox = params.get("bbox", ["0"])[0] == "1"
        win_size = int(params.get("win_size", ["720"])[0])

        if not key or not path_str:
            return self._send_error("Missing key or path", 400)

        img_path = PROJECT_ROOT / "assets" / "images" / path_str / key
        if not img_path.exists():
            webp_path = img_path.with_suffix(".webp")
            if webp_path.exists():
                img_path = webp_path
            else:
                return self._send_error("Asset not found", 404)

        img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            return self._send_error("Failed to load image", 500)

        scale = win_size / 1440.0

        if use_bbox:
            bbox = ImageUtils.get_bbox(img)
            x1, y1, x2, y2 = map(int, bbox)
            if x2 > x1 and y2 > y1:
                img = img[y1:y2, x1:x2]

        h, w = img.shape[:2]
        target_h = int(h * scale)
        target_w = int(w * scale)
        max_dim = 200
        if max(target_w, target_h) > max_dim:
            ratio = max_dim / max(target_w, target_h)
            target_w = int(target_w * ratio)
            target_h = int(target_h * ratio)

        if target_w > 0 and target_h > 0:
            img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_AREA)

        _, buf = cv2.imencode(".png", img)

        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", len(buf))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(buf.tobytes())

    def _handle_match(self):
        try:
            body = json.loads(self._read_body())
        except json.JSONDecodeError:
            return self._send_error("Invalid JSON", 400)

        screenshot_b64 = body.get("screenshot", "")
        assets = body.get("assets", [])
        low_res_mode = body.get("low_res_mode", False)
        models = body.get("models", ["clam", "normal", "aggressive"])
        win_size = int(body.get("win_size", "720"))

        if not screenshot_b64:
            return self._send_error("Missing screenshot", 400)
        if not assets:
            return self._send_error("Missing assets", 400)

        try:
            img_data = base64.b64decode(screenshot_b64.split(",")[-1])
            screenshot_pil = Image.open(io.BytesIO(img_data))
            screenshot = np.array(screenshot_pil)
        except Exception:
            return self._send_error("Invalid screenshot data", 400)

        if len(screenshot.shape) == 3 and screenshot.shape[2] >= 3:
            screenshot_gray = cv2.cvtColor(screenshot[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            screenshot_gray = screenshot

        results = []

        use_1440_base = low_res_mode and win_size < 1080
        if use_1440_base:
            ss_for_match, scale_to_1440 = ImageUtils.normalize_screenshot_for_1440_matching(screenshot_gray)
        else:
            ss_for_match = screenshot_gray
            scale_to_1440 = 1.0

        scale_from_1440 = win_size / 1440.0

        temp_win_size = getattr(cfg, "set_win_size", None)
        try:
            if temp_win_size is not None:
                cfg.unsaved_set_value("set_win_size", win_size)
        except Exception:
            pass

        try:
            for asset in assets:
                key = asset["key"]
                path_str = asset["path"]

                full_img = ImageUtils.load_from_specific_path(key, path_str, resize=False)
                if full_img is None:
                    continue

                bbox = None
                template = None
                if key.endswith("assets.png"):
                    bbox_1440 = ImageUtils.get_bbox(full_img)
                    if use_1440_base:
                        bbox = bbox_1440
                    else:
                        bbox = tuple(int(v * scale_from_1440) for v in bbox_1440)
                    template = ImageUtils.crop(full_img, bbox_1440)
                    if template is not None and not use_1440_base:
                        new_w = int(template.shape[1] * scale_from_1440)
                        new_h = int(template.shape[0] * scale_from_1440)
                        if new_w > 0 and new_h > 0:
                            template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    if template is not None and len(template.shape) == 3 and template.shape[2] >= 3:
                        template = cv2.cvtColor(template[:, :, :3], cv2.COLOR_RGB2GRAY)
                else:
                    template = ImageUtils.load_from_specific_path(key, path_str, resize=not use_1440_base)
                    if template is not None and len(template.shape) == 3 and template.shape[2] >= 3:
                        template = cv2.cvtColor(template[:, :, :3], cv2.COLOR_RGB2GRAY)

                if template is None:
                    continue

                h_t, w_t = template.shape[:2]
                template_size = (
                    [int(w_t / scale_to_1440), int(h_t / scale_to_1440)]
                    if use_1440_base
                    else [w_t, h_t]
                )

                asset_result = {
                    "key": key,
                    "path": path_str,
                    "template_size": template_size,
                }

                for model_name in models:
                    try:
                        center, match_val = ImageUtils.match_template(
                            ss_for_match, template, bbox, model_name
                        )
                        if use_1440_base and center is not None:
                            center = ImageUtils.restore_coordinates_from_1440_matching(
                                center, scale_to_1440
                            )
                        asset_result[model_name] = {
                            "center": list(center) if center else None,
                            "matchVal": round(float(match_val), 4) if match_val is not None else None,
                            "search_bbox": list(bbox) if bbox else None,
                        }
                    except Exception as e:
                        print(f"Match error for {key} model={model_name}: {e}")  # noqa: T201
                        asset_result[model_name] = {
                            "center": None,
                            "matchVal": None,
                            "search_bbox": None,
                            "error": str(e),
                        }

                results.append(asset_result)
        finally:
            if temp_win_size is not None:
                try:
                    cfg.unsaved_set_value("set_win_size", temp_win_size)
                except Exception:
                    pass

        self._send_json({
            "screenshot_size": [screenshot.shape[1], screenshot.shape[0]],
            "results": results,
            "low_res_mode": low_res_mode,
            "models": models,
        })


def main():
    server = HTTPServer(("127.0.0.1", PORT), MatchViewerHandler)
    url = f"http://localhost:{PORT}"
    print(f"Match Viewer running at {url}")  # noqa: T201
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")  # noqa: T201
        server.shutdown()


if __name__ == "__main__":
    main()
