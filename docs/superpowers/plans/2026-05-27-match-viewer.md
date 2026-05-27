# Match Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline diagnostic tool for AALC template matching: upload screenshot, select assets, run matching pipeline, visualize results on canvas.

**Architecture:** Python HTTP server (based on log_viewer.py pattern) with 3 API endpoints, single-page vanilla HTML/JS frontend with Canvas-based overlay rendering. Matching reuses production `ImageUtils._prepare_loaded_image`, `get_bbox`, `crop`, `match_template`.

**Tech Stack:** Python stdlib http.server, OpenCV (cv2), PIL, vanilla HTML/CSS/JS, HTML5 Canvas, no external frontend dependencies.

---

## File Structure

```
.opencode/tools/match_viewer.py            # Python server (~350 lines)
.opencode/tools/match_viewer/
  └── index.html                             # Frontend (~700 lines)
```

---

### Task 1: Python Server Scaffold

**Files:**
- Create: `.opencode/tools/match_viewer.py`

- [ ] **Step 1: Create server class with static file serving**

```python
#!/usr/bin/env python3
"""Match Viewer - Template matching diagnostic tool for AALC."""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import traceback
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from module.config import cfg
from utils.image_utils import ImageUtils

PORT = 9813


class MatchViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent / "match_viewer"), **kwargs)

    def log_message(self, format, *args):
        print(f"[match_viewer] {args[0]}")

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
        pass  # Task 2

    def _handle_asset_image(self, params):
        pass  # Task 3

    def _handle_match(self):
        pass  # Task 4


def main():
    server = HTTPServer(("127.0.0.1", PORT), MatchViewerHandler)
    url = f"http://localhost:{PORT}"
    print(f"Match Viewer running at {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify server starts and serves index.html (create stub)**

Create `.opencode/tools/match_viewer/index.html` with minimal content:
```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Match Viewer</title></head>
<body><h1>Match Viewer</h1></body>
</html>
```

Run: `uv run python .opencode/tools/match_viewer.py`
Expected: Browser opens to localhost:9813 showing "Match Viewer" heading.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer.py .opencode/tools/match_viewer/index.html
git commit -m "feat: match_viewer server scaffold"
```

---

### Task 2: `/api/categories` — Asset Catalog Endpoint

**Files:**
- Modify: `.opencode/tools/match_viewer.py` (add `_handle_categories`)

- [ ] **Step 1: Implement category scanning and bbox precomputation**

```python
def _handle_categories(self, params):
    theme = params.get("theme", ["default"])[0]
    lang = params.get("lang", ["en"])[0]
    win_size = int(params.get("win_size", ["720"])[0])

    scale = win_size / 1440.0

    # Path prefix: theme/lang
    path_prefix = f"{theme}/{lang}"
    share_path = f"{theme}/share"

    categories = {}
    base_dir = PROJECT_ROOT / "assets" / "images"

    for subdir in [path_prefix, share_path]:
        full_dir = base_dir / subdir
        if not full_dir.exists():
            continue
        for png_file in sorted(full_dir.rglob("*assets.png")):
            rel = str(png_file.relative_to(full_dir))
            # Build category from directory structure
            category = str(Path(rel).parent).replace("\\", "/") or "root"
            key = f"{category}/{png_file.name}" if category != "root" else png_file.name

            # Load image, compute bbox, scale to win_size
            img = cv2.imread(str(png_file), cv2.IMREAD_UNCHANGED)
            if img is None:
                continue
            bbox = ImageUtils.get_bbox(img)
            # Scale bbox
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

    # Sort categories
    categories = dict(sorted(categories.items()))
    for assets in categories.values():
        assets.sort(key=lambda a: a["key"])

    self._send_json({"categories": categories, "win_size": win_size, "theme": theme, "lang": lang})
```

- [ ] **Step 2: Test the endpoint**

Run server, then: `uv run python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:9813/api/categories?theme=default&lang=en&win_size=720'); print(json.dumps(json.load(r),indent=2)[:2000])"`
Expected: JSON with categories dict containing home/, base/, battle/, mirror/, etc.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer.py
git commit -m "feat: /api/categories endpoint with bbox precomputation"
```

---

### Task 3: `/api/asset-image` — Asset Thumbnail Endpoint

**Files:**
- Modify: `.opencode/tools/match_viewer.py` (add `_handle_asset_image`)

- [ ] **Step 1: Implement thumbnail serving**

```python
def _handle_asset_image(self, params):
    key = params.get("key", [None])[0]
    path_str = params.get("path", [None])[0]
    use_bbox = params.get("bbox", ["0"])[0] == "1"
    win_size = int(params.get("win_size", ["720"])[0])

    if not key or not path_str:
        return self._send_error("Missing key or path", 400)

    img_path = PROJECT_ROOT / "assets" / "images" / path_str / key
    if not img_path.exists():
        # Try .webp
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
        img = img[y1:y2, x1:x2]

    # Resize to thumbnail-friendly size
    h, w = img.shape[:2]
    target_h = int(h * scale)
    target_w = int(w * scale)
    # Cap thumbnail at 200px max dimension for preview
    max_dim = 200
    if max(target_w, target_h) > max_dim:
        ratio = max_dim / max(target_w, target_h)
        target_w = int(target_w * ratio)
        target_h = int(target_h * ratio)

    if target_w > 0 and target_h > 0:
        img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_AREA)

    # Strip alpha for PNG output
    if len(img.shape) == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGRA)
        # Keep alpha for transparent PNG
        _, buf = cv2.imencode(".png", img)
    else:
        _, buf = cv2.imencode(".png", img)

    self.send_response(200)
    self.send_header("Content-Type", "image/png")
    self.send_header("Content-Length", len(buf))
    self.send_header("Cache-Control", "public, max-age=3600")
    self.end_headers()
    self.wfile.write(buf.tobytes())
```

- [ ] **Step 2: Test thumbnail endpoint**

Run server, check: `http://localhost:9813/api/asset-image?key=home/back_assets.png&path=default/share&bbox=1&win_size=720` in browser.
Expected: Cropped back button thumbnail image.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer.py
git commit -m "feat: /api/asset-image thumbnail endpoint"
```

---

### Task 4: `/api/match` — Matching Execution Endpoint

**Files:**
- Modify: `.opencode/tools/match_viewer.py` (add `_handle_match` and helpers)

- [ ] **Step 1: Implement matching engine and endpoint**

```python
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

    # Decode screenshot
    try:
        img_data = base64.b64decode(screenshot_b64.split(",")[-1])
        screenshot_pil = Image.open(io.BytesIO(img_data))
        screenshot = np.array(screenshot_pil)
    except Exception:
        return self._send_error("Invalid screenshot data", 400)

    if len(screenshot.shape) == 3 and screenshot.shape[2] == 3:
        screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
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

    for asset in assets:
        key = asset["key"]
        path_str = asset["path"]

        # Load and prepare template
        template_raw = ImageUtils.load_from_specific_path(key, path_str, resize=not use_1440_base)
        if template_raw is None:
            continue

        bbox = None
        if key.endswith("assets.png"):
            full_img = ImageUtils.load_from_specific_path(key, path_str, resize=False)
            if full_img is not None:
                bbox_1440 = ImageUtils.get_bbox(full_img)
                if use_1440_base:
                    bbox = bbox_1440
                else:
                    bbox = tuple(int(v * scale_from_1440) for v in bbox_1440)
                template = ImageUtils.crop(full_img, bbox_1440)
                if not use_1440_base and template is not None:
                    new_w = int(template.shape[1] * scale_from_1440)
                    new_h = int(template.shape[0] * scale_from_1440)
                    if new_w > 0 and new_h > 0:
                        template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
                if template is not None and len(template.shape) == 3 and template.shape[2] >= 3:
                    template = cv2.cvtColor(template[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            template = template_raw
            if template is not None and len(template.shape) == 3 and template.shape[2] >= 3:
                template = cv2.cvtColor(template[:, :, :3], cv2.COLOR_RGB2GRAY)

        if template is None:
            continue

        h_t, w_t = template.shape[:2]
        template_size = [int(w_t / scale_to_1440), int(h_t / scale_to_1440)] if use_1440_base else [w_t, h_t]

        asset_result = {
            "key": key,
            "path": path_str,
            "template_size": template_size,
        }

        for model in models:
            try:
                center, match_val = ImageUtils.match_template(ss_for_match, template, bbox, model)
                if use_1440_base and center is not None:
                    center = ImageUtils.restore_coordinates_from_1440_matching(center, scale_to_1440)
                asset_result[model] = {
                    "center": list(center) if center else None,
                    "matchVal": round(float(match_val), 4) if match_val is not None else None,
                    "search_bbox": list(bbox) if bbox else None,
                }
            except Exception as e:
                print(f"Match error for {key} model={model}: {e}")
                asset_result[model] = {"center": None, "matchVal": None, "search_bbox": None, "error": str(e)}

        results.append(asset_result)

    self._send_json({
        "screenshot_size": [screenshot.shape[1], screenshot.shape[0]],
        "results": results,
        "low_res_mode": low_res_mode,
        "models": models,
    })
```

- [ ] **Step 2: Test matching with real data**

```bash
uv run python -c "
import base64, json, urllib.request

with open('screenshot_20260527_144208.png', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()

req = json.dumps({
    'screenshot': 'data:image/png;base64,' + b64,
    'assets': [{'key': 'home/back_assets.png', 'path': 'default/share'}],
    'low_res_mode': False,
    'models': ['clam', 'normal', 'aggressive'],
    'win_size': 720
}).encode()

r = urllib.request.urlopen(urllib.request.Request(
    'http://localhost:9813/api/match',
    data=req,
    headers={'Content-Type': 'application/json'}
))
print(json.dumps(json.load(r), indent=2))
"
```
Expected: JSON with `clam.matchVal ≈ 0.38`, `center ≈ [96, 45]`.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer.py
git commit -m "feat: /api/match endpoint with triple-model matching"
```

---

### Task 5: Frontend Skeleton — HTML Structure & CSS

**Files:**
- Modify: `.opencode/tools/match_viewer/index.html`

- [ ] **Step 1: Replace with full HTML/CSS skeleton**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Match Viewer — AALC</title>
<style>
:root {
  --bg: #1a1a2e;
  --surface: #16213e;
  --surface2: #0f3460;
  --text: #e0e0e0;
  --text2: #a0a0a0;
  --accent: #e94560;
  --green: #4caf84;
  --red: #e94560;
  --border: #2a3a5e;
  --radius: 6px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); height: 100vh; overflow: hidden;
  display: flex; flex-direction: column;
}
.topbar {
  display: flex; align-items: center; gap: 12px; padding: 8px 16px;
  background: var(--surface); border-bottom: 1px solid var(--border);
}
.topbar select, .topbar button, .topbar input[type=range] {
  background: var(--surface2); color: var(--text); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 4px 10px; font-size: 13px;
}
.topbar button { cursor: pointer; }
.topbar button:hover { background: var(--accent); }
.topbar button.primary { background: var(--accent); border-color: var(--accent); }
.main { display: flex; flex: 1; overflow: hidden; }
.panel { display: flex; flex-direction: column; }
.panel-left {
  width: 340px; min-width: 280px; background: var(--surface);
  border-right: 1px solid var(--border); overflow: hidden;
}
.panel-right { flex: 1; position: relative; overflow: hidden; }
.dropzone {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; border: 3px dashed var(--border);
  color: var(--text2); font-size: 16px; cursor: pointer; transition: border-color 0.2s;
}
.dropzone.drag-over { border-color: var(--accent); color: var(--accent); }
.canvas-wrap { position: absolute; inset: 0; overflow: hidden; }
.canvas-wrap canvas { position: absolute; }
.asset-search { padding: 8px; }
.asset-search input {
  width: 100%; background: var(--surface2); color: var(--text);
  border: 1px solid var(--border); border-radius: var(--radius); padding: 6px 10px; font-size: 13px;
}
.cat-tree { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
.cat-group { margin-bottom: 4px; }
.cat-header {
  display: flex; align-items: center; padding: 6px 4px; cursor: pointer;
  font-size: 13px; font-weight: 600; color: var(--text2);
}
.cat-header:hover { color: var(--text); }
.cat-header .arrow { margin-right: 4px; font-size: 10px; transition: transform 0.15s; }
.cat-header .arrow.open { transform: rotate(90deg); }
.cat-items { padding-left: 8px; }
.cat-items.collapsed { display: none; }
.asset-item {
  display: flex; align-items: center; gap: 8px; padding: 4px 6px;
  border-radius: var(--radius); cursor: pointer; font-size: 12px;
}
.asset-item:hover { background: var(--surface2); }
.asset-item.selected { background: var(--surface2); }
.asset-item input[type=checkbox] { accent-color: var(--accent); }
.asset-item .eye { cursor: pointer; opacity: 0.5; font-size: 14px; }
.asset-item .eye.visible { opacity: 1; color: var(--accent); }
.asset-item .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.asset-item .thumb { width: 32px; height: 32px; object-fit: contain; border-radius: 3px; }
.controls {
  padding: 8px 12px; border-top: 1px solid var(--border); background: var(--surface);
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}
.controls label { font-size: 12px; color: var(--text2); white-space: nowrap; }
.model-tabs { display: flex; gap: 2px; }
.model-tab {
  padding: 4px 12px; font-size: 12px; border: 1px solid var(--border);
  background: var(--surface2); color: var(--text); cursor: pointer; border-radius: var(--radius);
}
.model-tab.active { background: var(--accent); border-color: var(--accent); }
.status { padding: 4px 16px; font-size: 12px; color: var(--text2); background: var(--surface); border-top: 1px solid var(--border); }
</style>
</head>
<body>
<div class="topbar">
  <span style="font-weight:600;color:var(--accent)">AALC Match Viewer</span>
  <select id="themeSelect"><option value="default">亮色</option><option value="dark">暗色</option></select>
  <select id="langSelect"><option value="en">英文</option><option value="zh_cn">中文</option></select>
  <input type="range" id="thresholdSlider" min="0" max="100" value="80" style="width:120px" title="匹配阈值">
  <label id="thresholdLabel" style="min-width:40px">0.80</label>
  <div class="model-tabs" id="modelTabs">
    <span class="model-tab active" data-model="clam">clam</span>
    <span class="model-tab" data-model="normal">normal</span>
    <span class="model-tab" data-model="aggressive">aggressive</span>
  </div>
  <label><input type="checkbox" id="lowResToggle"> 低分辨率优化</label>
  <button class="primary" id="runMatchBtn">运行匹配</button>
</div>
<div class="main">
  <div class="panel panel-left">
    <div class="asset-search"><input type="text" id="assetSearch" placeholder="搜索资产..."></div>
    <div class="cat-tree" id="catTree"></div>
    <div class="controls">
      <button id="selectAllBtn">全选</button>
      <button id="deselectAllBtn">全不选</button>
      <button id="showAllBtn">全部显示</button>
      <button id="hideAllBtn">全部隐藏</button>
    </div>
  </div>
  <div class="panel panel-right" id="viewerPanel">
    <div class="dropzone" id="dropzone">
      <div style="font-size:48px;margin-bottom:16px">📷</div>
      <div>拖放截图到此处，或点击选择文件</div>
      <div style="font-size:12px;margin-top:8px">也支持 Ctrl+V 粘贴</div>
      <input type="file" id="fileInput" accept="image/*" style="display:none">
    </div>
    <div class="canvas-wrap" id="canvasWrap" style="display:none">
      <canvas id="overlayCanvas"></canvas>
    </div>
  </div>
</div>
<div class="status" id="statusBar">就绪 — 等待截图上传</div>

<script>
// Task 6-9 will fill this
</script>
</body>
</html>
```

- [ ] **Step 2: Verify layout renders**

Run: `uv run python .opencode/tools/match_viewer.py`
Expected: Dark-themed three-column layout with asset search, category tree area, and dropzone.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer/index.html
git commit -m "feat: match_viewer frontend skeleton with dark theme"
```

---

### Task 6: Frontend — Asset Browser

**Files:**
- Modify: `.opencode/tools/match_viewer/index.html` (add JS for asset loading and rendering)

- [ ] **Step 1: Implement asset catalog loading and category tree rendering**

Add to `<script>` block:
```javascript
const API = 'http://localhost:9813';
const state = {
  winSize: 720,
  assets: [],        // {key, path, bbox, size}
  selected: new Set(),
  visible: new Set(),
  matchResults: null,
  currentModel: 'clam',
  threshold: 0.8,
  screenshotImg: null,
  scale: 1, offsetX: 0, offsetY: 0,
};
let catData = {};
let collapsedCats = new Set();

async function loadCategories() {
  const theme = document.getElementById('themeSelect').value;
  const lang = document.getElementById('langSelect').value;
  const ws = state.winSize;
  try {
    const r = await fetch(`${API}/api/categories?theme=${theme}&lang=${lang}&win_size=${ws}`);
    const data = await r.json();
    catData = data.categories || {};
    state.winSize = data.win_size;
    flattenAssets();
    renderCatTree();
  } catch (e) {
    console.error('Failed to load categories:', e);
  }
}

function flattenAssets() {
  state.assets = [];
  for (const [cat, items] of Object.entries(catData)) {
    for (const item of items) {
      state.assets.push({...item, category: cat});
    }
  }
}

function renderCatTree() {
  const tree = document.getElementById('catTree');
  tree.innerHTML = '';
  const search = document.getElementById('assetSearch').value.toLowerCase();

  for (const [cat, items] of Object.entries(catData)) {
    const filtered = items.filter(a => a.key.toLowerCase().includes(search));
    if (filtered.length === 0) continue;

    const group = document.createElement('div');
    group.className = 'cat-group';
    const isCollapsed = collapsedCats.has(cat);

    const header = document.createElement('div');
    header.className = 'cat-header';
    header.innerHTML = `<span class="arrow${isCollapsed ? '' : ' open'}">▶</span> ${cat} (${filtered.length})`;
    header.onclick = () => {
      if (collapsedCats.has(cat)) collapsedCats.delete(cat);
      else collapsedCats.add(cat);
      renderCatTree();
    };
    group.appendChild(header);

    const itemsDiv = document.createElement('div');
    itemsDiv.className = 'cat-items' + (isCollapsed ? ' collapsed' : '');

    for (const item of filtered) {
      const row = document.createElement('div');
      row.className = 'asset-item';

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = state.selected.has(item.key);
      cb.onchange = () => {
        if (cb.checked) state.selected.add(item.key);
        else state.selected.delete(item.key);
      };

      const thumb = document.createElement('img');
      thumb.className = 'thumb';
      thumb.src = `${API}/api/asset-image?key=${encodeURIComponent(item.key)}&path=${encodeURIComponent(item.path)}&bbox=1&win_size=${state.winSize}`;
      thumb.onerror = () => { thumb.style.display = 'none'; };

      const name = document.createElement('span');
      name.className = 'name';
      name.textContent = item.key.split('/').pop().replace('_assets.png', '');
      name.title = item.key;

      // Eye toggle for visibility in canvas
      const eye = document.createElement('span');
      eye.className = 'eye' + (state.visible.has(item.key) ? ' visible' : '');
      eye.textContent = state.visible.has(item.key) ? '👁' : '👁';
      eye.title = '切换截图显示';
      eye.onclick = (e) => {
        e.stopPropagation();
        if (state.visible.has(item.key)) state.visible.delete(item.key);
        else state.visible.add(item.key);
        eye.className = 'eye' + (state.visible.has(item.key) ? ' visible' : '');
        eye.textContent = state.visible.has(item.key) ? '👁' : '👁';
        if (state.matchResults) drawOverlay();
      };

      row.appendChild(cb);
      row.appendChild(thumb);
      row.appendChild(name);
      row.appendChild(eye);
      itemsDiv.appendChild(row);
    }
    group.appendChild(itemsDiv);
    tree.appendChild(group);
  }
}

document.getElementById('assetSearch').addEventListener('input', renderCatTree);
document.getElementById('themeSelect').addEventListener('change', () => { state.selected.clear(); state.visible.clear(); loadCategories(); });
document.getElementById('langSelect').addEventListener('change', () => { state.selected.clear(); state.visible.clear(); loadCategories(); });

document.getElementById('selectAllBtn').onclick = () => {
  for (const a of state.assets) state.selected.add(a.key);
  renderCatTree();
};
document.getElementById('deselectAllBtn').onclick = () => {
  state.selected.clear();
  renderCatTree();
};
document.getElementById('showAllBtn').onclick = () => {
  for (const a of state.assets) state.visible.add(a.key);
  renderCatTree();
  if (state.matchResults) drawOverlay();
};
document.getElementById('hideAllBtn').onclick = () => {
  state.visible.clear();
  renderCatTree();
  if (state.matchResults) drawOverlay();
};

// Initial load
loadCategories();
```

- [ ] **Step 2: Verify asset browser works**

Run server, refresh browser. Expected: Category tree with arrows, asset items with checkboxes, eye toggles, thumbnails. Search filters work.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer/index.html
git commit -m "feat: asset browser with category tree, search, checkboxes"
```

---

### Task 7: Frontend — Screenshot Upload (Paste, Drag, File)

**Files:**
- Modify: `.opencode/tools/match_viewer/index.html` (add upload handlers)

- [ ] **Step 1: Implement upload handlers**

Add to `<script>` block:
```javascript
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const canvasWrap = document.getElementById('canvasWrap');
const overlayCanvas = document.getElementById('overlayCanvas');
const ctx = overlayCanvas.getContext('2d');

dropzone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
  if (e.target.files[0]) loadScreenshot(e.target.files[0]);
});

// Drag & drop
dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag-over'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) loadScreenshot(file);
});

// Paste
document.addEventListener('paste', (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      loadScreenshot(item.getAsFile());
      break;
    }
  }
});

function loadScreenshot(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      state.screenshotImg = img;
      state.winSize = img.naturalHeight;
      dropzone.style.display = 'none';
      canvasWrap.style.display = 'block';
      state.scale = 1;
      state.offsetX = 0;
      state.offsetY = 0;
      resizeCanvas();
      drawScreenshot();
      // Update asset catalog for detected resolution
      loadCategories();
      document.getElementById('statusBar').textContent =
        `截图已加载 — ${img.naturalWidth}×${img.naturalHeight} (推断 win_size=${state.winSize})`;
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function resizeCanvas() {
  const wrap = canvasWrap;
  const img = state.screenshotImg;
  if (!img) return;
  overlayCanvas.width = wrap.clientWidth;
  overlayCanvas.height = wrap.clientHeight;
  drawScreenshot();
}

function drawScreenshot() {
  const img = state.screenshotImg;
  if (!img) return;
  ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  const drawW = img.naturalWidth * state.scale;
  const drawH = img.naturalHeight * state.scale;
  const x = (overlayCanvas.width - drawW) / 2 + state.offsetX;
  const y = (overlayCanvas.height - drawH) / 2 + state.offsetY;
  ctx.drawImage(img, x, y, drawW, drawH);
  if (state.matchResults) drawOverlay();
}

// Canvas zoom & pan
let isDragging = false, dragStartX, dragStartY;
overlayCanvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const delta = e.deltaY > 0 ? 0.9 : 1.1;
  state.scale = Math.max(0.1, Math.min(5, state.scale * delta));
  drawScreenshot();
});
overlayCanvas.addEventListener('mousedown', (e) => {
  isDragging = true; dragStartX = e.clientX - state.offsetX; dragStartY = e.clientY - state.offsetY;
});
overlayCanvas.addEventListener('mousemove', (e) => {
  if (!isDragging) return;
  state.offsetX = e.clientX - dragStartX;
  state.offsetY = e.clientY - dragStartY;
  drawScreenshot();
});
document.addEventListener('mouseup', () => { isDragging = false; });
window.addEventListener('resize', resizeCanvas);
```

- [ ] **Step 2: Test upload**

Open browser, drag `screenshot_20260527_144208.png` onto dropzone.
Expected: Screenshot displayed on canvas. Status bar shows resolution. Drag to pan, scroll to zoom work.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer/index.html
git commit -m "feat: screenshot upload via paste/drag/file + canvas viewer"
```

---

### Task 8: Frontend — Matching Execution & Result Rendering

**Files:**
- Modify: `.opencode/tools/match_viewer/index.html` (add match execution and Canvas overlay drawing)

- [ ] **Step 1: Implement match execution and rectangle rendering**

Add to `<script>` block:
```javascript
// Model tabs
document.querySelectorAll('.model-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.model-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    state.currentModel = tab.dataset.model;
    drawScreenshot();
  });
});

// Threshold slider
const thresholdSlider = document.getElementById('thresholdSlider');
const thresholdLabel = document.getElementById('thresholdLabel');
thresholdSlider.addEventListener('input', () => {
  state.threshold = thresholdSlider.value / 100;
  thresholdLabel.textContent = state.threshold.toFixed(2);
  drawScreenshot();
});

// Run match
document.getElementById('runMatchBtn').addEventListener('click', runMatch);

async function runMatch() {
  if (!state.screenshotImg) {
    alert('请先加载截图');
    return;
  }
  const selectedAssets = state.assets.filter(a => state.selected.has(a.key));
  if (selectedAssets.length === 0) {
    alert('请至少选择一个资产');
    return;
  }

  document.getElementById('statusBar').textContent = '正在匹配...';

  // Get base64 of screenshot
  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = state.screenshotImg.naturalWidth;
  tempCanvas.height = state.screenshotImg.naturalHeight;
  tempCanvas.getContext('2d').drawImage(state.screenshotImg, 0, 0);
  const b64 = tempCanvas.toDataURL('image/png');

  const lowRes = document.getElementById('lowResToggle').checked;
  const reqBody = {
    screenshot: b64,
    assets: selectedAssets.map(a => ({key: a.key, path: a.path})),
    low_res_mode: lowRes,
    models: ['clam', 'normal', 'aggressive'],
    win_size: state.winSize,
  };

  try {
    const r = await fetch(`${API}/api/match`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(reqBody),
    });
    state.matchResults = await r.json();
    // Auto-show all matched assets
    for (const r of state.matchResults.results) {
      state.visible.add(r.key);
    }
    document.getElementById('statusBar').textContent =
      `匹配完成 — ${state.matchResults.results.length} 资产, ${state.matchResults.models.length} 模型`;
    drawScreenshot();
  } catch (e) {
    document.getElementById('statusBar').textContent = '匹配失败: ' + e.message;
  }
}

function drawOverlay() {
  if (!state.matchResults || !state.screenshotImg) return;
  const img = state.screenshotImg;
  const drawW = img.naturalWidth * state.scale;
  const drawH = img.naturalHeight * state.scale;
  const baseX = (overlayCanvas.width - drawW) / 2 + state.offsetX;
  const baseY = (overlayCanvas.height - drawH) / 2 + state.offsetY;
  const scaleX = drawW / img.naturalWidth;
  const scaleY = drawH / img.naturalHeight;

  for (const result of state.matchResults.results) {
    if (!state.visible.has(result.key)) continue;

    const modelData = result[state.currentModel];
    if (!modelData || !modelData.center || modelData.matchVal === null) continue;

    const [cx, cy] = modelData.center;
    const [tw, th] = result.template_size;

    const x = baseX + cx * scaleX - (tw * scaleX) / 2;
    const y = baseY + cy * scaleY - (th * scaleY) / 2;
    const w = tw * scaleX;
    const h = th * scaleY;
    const passed = modelData.matchVal >= state.threshold;

    ctx.strokeStyle = passed ? '#4caf84' : '#e94560';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);

    // Label
    const shortName = result.key.split('/').pop().replace('_assets.png', '');
    const label = `${shortName} ${modelData.matchVal.toFixed(2)}`;
    ctx.font = '11px monospace';
    const textW = ctx.measureText(label).width + 6;
    ctx.fillStyle = passed ? 'rgba(76,175,132,0.85)' : 'rgba(233,69,96,0.85)';
    ctx.fillRect(x, y - 18, textW, 18);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, x + 3, y - 5);
  }
}
```

- [ ] **Step 2: End-to-end test**

1. Start server
2. Open browser, select theme=亮色, lang=英文
3. Upload `screenshot_20260527_144208.png`
4. Checkbox `back_assets` under `home/`
5. Click "运行匹配"
6. Expected: Green rectangle at top-left with "back_assets 0.38". Adjust threshold slider to verify color change at 0.38 boundary.
7. Switch to `aggressive` model, verify rectangle repositioned.

- [ ] **Step 3: Commit**

```bash
git add .opencode/tools/match_viewer/index.html
git commit -m "feat: match execution and canvas overlay rendering"
```

---

### Task 9: Frontend — Polish & Edge Cases

**Files:**
- Modify: `.opencode/tools/match_viewer/index.html`

- [ ] **Step 1: Handle edge cases**

Add to `<script>`:
```javascript
// Show/hide canvas when removing screenshot (via new "清除截图" button)
function clearScreenshot() {
  state.screenshotImg = null;
  state.matchResults = null;
  dropzone.style.display = 'flex';
  canvasWrap.style.display = 'none';
  state.visible.clear();
  renderCatTree();
  document.getElementById('statusBar').textContent = '就绪 — 等待截图上传';
}

// Disable run match button when no screenshot
document.getElementById('lowResToggle').addEventListener('change', () => {
  if (state.matchResults) {
    document.getElementById('statusBar').textContent = '低分辨率模式已更改 — 请重新运行匹配';
  }
});
```

Add "清除截图" button to topbar:
```html
<button id="clearBtn" onclick="clearScreenshot()">清除截图</button>
```

- [ ] **Step 2: Add search_bbox visualization (dashed line for search region)**

In `drawOverlay()`, after the match rectangle, add:
```javascript
    // Draw search bbox as dashed rectangle (only if bbox exists)
    if (modelData.search_bbox) {
      const [sx1, sy1, sx2, sy2] = modelData.search_bbox;
      const sbx = baseX + sx1 * scaleX;
      const sby = baseY + sy1 * scaleY;
      const sbw = (sx2 - sx1) * scaleX;
      const sbh = (sy2 - sy1) * scaleY;
      ctx.strokeStyle = 'rgba(100,149,237,0.4)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.strokeRect(sbx, sby, sbw, sbh);
      ctx.setLineDash([]);
    }
```

- [ ] **Step 3: Final verification**

Full workflow test:
1. Load screenshot → category tree populated with correct resolution bbox
2. Select multiple assets → run match → all rectangles visible
3. Toggle eye icons → rectangles appear/disappear
4. Threshold slider → green/red transitions at correct values
5. Model tabs → rectangles shift between clam/normal/aggressive positions
6. Low res mode toggle → re-run match → verify upscaled matching works (should give ~0.39 for back_assets)
7. Search filter → narrows asset list
8. Zoom/pan → rectangles scale correctly

- [ ] **Step 4: Commit**

```bash
git add .opencode/tools/match_viewer/index.html
git commit -m "feat: polish edge cases, search bbox viz, clear button"
```

---

### Task 10: Self-Review & Cleanup

**Files:**
- Modify: `.opencode/tools/match_viewer.py`
- Modify: `.opencode/tools/match_viewer/index.html`

- [ ] **Step 1: Run ruff linter on server code**

```bash
uv run ruff check .opencode/tools/match_viewer.py
```
Expected: No new errors.

- [ ] **Step 2: Syntax check**

```bash
uv run python -m py_compile .opencode/tools/match_viewer.py
```
Expected: No output (success).

- [ ] **Step 3: Verify import chain works**

```bash
uv run python -c "import sys; sys.path.insert(0, '.'); from module.config import cfg; from utils.image_utils import ImageUtils; print('Imports OK')"
```
Expected: "Imports OK" (no crash).

- [ ] **Step 4: Final manual test with back_init_menu assets**

1. Start server
2. Load `screenshot_20260527_144208.png`
3. Select all assets in: home/, base/, mirror/road_in_mir/
4. Run match
5. Verify: `back_assets` shows 0.38 (red at default 0.80 threshold), `window_assets` shows 0.49
6. Drop threshold to 0.35 → `back_assets` goes green, `window_assets` goes green at 0.49
7. Confirm the diagnosis: only `clear_all_caches` at 0.64 and `window_assets` at 0.49 have any matches, all below 0.80

- [ ] **Step 5: Final commit**

```bash
git add .opencode/tools/match_viewer.py .opencode/tools/match_viewer/index.html
git commit -m "chore: final verification and cleanup for match_viewer"
```
