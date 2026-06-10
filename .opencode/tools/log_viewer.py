"""
AALC 日志可视化服务器
启动后访问 http://localhost:9812/ 查看日志可视化面板

用法:
  uv run python .opencode/tools/log_viewer.py [--port 9812] [--log <路径>]
  不指定 --log 则在页面中选择文件
"""

import http.server
import io
import json
import os
import re
import socketserver
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

# ── 配置 ──────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 9812
STATIC_DIR = Path(__file__).parent / "log_viewer"
PROJECT_ROOT = Path(__file__).parent.parent.parent
ASSET_DIRS = [
    PROJECT_ROOT / "assets" / "images" / "default" / "share",
    PROJECT_ROOT / "assets" / "images" / "default" / "en",
    PROJECT_ROOT / "assets" / "images" / "default" / "zh_cn",
    PROJECT_ROOT / "assets" / "images" / "dark",
]
ISSUES_DIR = PROJECT_ROOT / "issues"

# ── 人话映射 ──────────────────────────────────────────
SYSTEM_NAMES = {
    "burn": "🔥烧伤", "bleed": "🩸流血", "tremor": "📳震颤",
    "rupture": "💥破裂", "poise": "🌊呼吸", "sinking": "🌑沉沦",
    "charge": "⚡充能", "slash": "⚔斩击", "pierce": "🏹贯穿",
    "blunt": "🔨打击",
}

ASSET_NAMES = {
    # 商店核心
    "mirror/shop/power_up_assets.png": "⭐升级",
    "mirror/shop/power_up_confirm_assets.png": "✅升级确认",
    "mirror/shop/purchase_assets.png": "🛒购买",
    "mirror/shop/shop_coins_assets.png": "🪙商店硬币图标",
    "mirror/shop/refresh_assets.png": "🔄普通刷新",
    "mirror/shop/refresh_keyword_assets.png": "🔑关键词刷新",
    "mirror/shop/refresh_keyword_confirm_assets.png": "✅关键词刷新确认",
    "mirror/shop/fuse_gift_assets.png": "🔬合成",
    "mirror/shop/fuse_ego_gift_assets.png": "🔬合成EGO",
    "mirror/shop/fuse_90%_assets.png": "90%合成概率",
    "mirror/shop/sell_gift_assets.png": "💰出售",
    "mirror/shop/sell_gift_confirm_assets.png": "✅出售确认",
    "mirror/shop/enhance_gifts_assets.png": "⬆进入升级页",
    "mirror/shop/sort_button_assets.png": "🔽排序",
    "mirror/shop/leave_assets.png": "🚪离开商店",
    "mirror/shop/leave_shop_confirm_assets.png": "✅离开确认",
    "mirror/shop/return_assets.png": "🔙返回",
    "mirror/shop/fuse_label.png": "🏷合成标签",
    "mirror/shop/gifts_list_block.png": "📋列表滑块",
    "mirror/shop/fuse_to_select_keyword_assets.png": "🔀切换关键词",
    "mirror/shop/fuse_gift_confirm_assets.png": "✅合成确认",
    "mirror/shop/enhance_and_fuse_and_sell_confirm_assets.png": "✅操作确认",
    "mirror/shop/fuse_use_starlight_assets.png": "✨使用星光",
    "mirror/shop/fuse_use_starlight_confirm_assets.png": "✅星光确认",
    "mirror/shop/fusion_level_IV_gift_assets.png": "4️⃣四级合成",
    "mirror/shop/level_IV_to_buy.png": "4️⃣四级可购买",
    "mirror/shop/level_III_to_buy.png": "3️⃣三级可购买",
    "mirror/shop/ID_skill_replace_0_purchased_assets.png": "0号技能替换已购",
    "mirror/shop/ID_skill_replace_1_purchased_assets.png": "1号技能替换已购",
    "mirror/shop/ID_skill_replace_2_purchased_assets.png": "2号技能替换已购",
    "mirror/shop/skill_replacement_assets.png": "🔄技能替换",
    "mirror/shop/skill_replacement_confirm_assets.png": "✅技能替换确认",
    "mirror/shop/skill_replacement_coins.png": "🪙技能替换硬币",
    "mirror/shop/super_shop_assets.png": "⭐超级商店",
    "mirror/shop/super_shop_skill_replacement_1_assets.png": "超级商店技能替换1",
    "mirror/shop/super_shop_skill_replacement_2_assets.png": "超级商店技能替换2",
    # 治疗
    "mirror/shop/heal_sinner/heal_all_sinner_assets.png": "💊全体治疗",
    "mirror/shop/heal_sinner/heal_sinner_assets.png": "💊治疗罪人",
    "mirror/shop/heal_sinner/heal_sinner_return_assets.png": "🔙治疗返回",
    # 镜牢通用
    "mirror/road_in_mir/ego_gift_get_confirm_assets.png": "✅EGO获取确认",
    "mirror/road_in_mir/legend_assets.png": "🗺地图图例",
    "mirror/road_in_mir/enter_assets.png": "🚪进入",
    "mirror/road_in_mir/acquire_ego_gift_card.png": "🃏EGO饰品卡",
    "mirror/road_in_mir/event_effect_button.png": "📌事件效果",
    "mirror/road_in_mir/select_encounter_reward_card_assets.png": "🃏选择奖励卡",
    "mirror/road_in_mir/select_event_effect_confirm.png": "✅事件效果确认",
    "mirror/road_in_mir/refuse_gift_assets.png": "❌拒绝饰品",
    "mirror/road_in_mir/acquire_ego_gift_select_assets.png": "选择EGO饰品",
    # 战斗
    "battle/pause_assets.png": "⏸暂停",
    "battle/view_status_assets.png": "👁查看状态",
    "battle/dead_all.png": "💀全灭",
    "battle/dead.png": "💀死亡",
    "battle/more_information_assets.png": "ℹ更多信息",
    "battle/in_mirror_assets.png": "🪞镜牢中",
    "battle/win_rate_card.png": "📊胜率卡",
    "battle/gear_left.png": "⚙齿轮左",
    "battle/select_none_assets.png": "✖取消选择",
    "battle/normal_to_battle_assets.png": "普通战斗",
    "battle/chaim_to_battle_assets.png": "锁定战斗",
    # 基础
    "base/connecting_assets.png": "🔄连接中",
    "base/retry_countdown.png": "⏳重试倒计时",
    "base/retry.png": "🔄重试",
    "base/try_again.png": "↻再试一次",
    "base/clear_all_caches_assets.png": "🧹清除缓存",
    "base/only_option_assets.png": "唯一选项",
    "base/waiting_assets.png": "⏳等待中",
    "base/battle_finish_confirm_assets.png": "✅战斗完成确认",
    # 事件
    "event/skip_assets.png": "⏭跳过",
    "event/continue_assets.png": "▶继续",
    "event/proceed_assets.png": "▶前进",
    "event/perform_the_check_feature_assets.png": "🔍执行检定",
    "event/commence_battle_assets.png": "⚔开始战斗",
    "event/commence_assets.png": "▶开始",
    "event/choices_assets.png": "📋选择",
    "event/advantage_check.png": "✅优势检定",
    # 主页/导航
    "home/drive_assets.png": "🚗出发",
    "home/window_assets.png": "🪟窗口",
    "home/mirror_dungeons_assets.png": "🪞镜牢入口",
    "home/luxcavation_assets.png": "⛏纺锤本入口",
    # 领取奖励
    "mirror/claim_reward/use_enkephalin_assets.png": "🧪使用脑啡肽",
    "mirror/claim_reward/battle_statistics_assets.png": "📊战斗统计",
    "mirror/claim_reward/claim_rewards_assets.png": "🎁领取奖励",
    "mirror/claim_reward/claim_rewards_confirm_assets.png": "✅领取确认",
    "mirror/claim_reward/claim_forfeit_assets.png": "❌放弃奖励",
    # 主题包
    "mirror/theme_pack/feature_theme_pack_assets.png": "📦主题包",
    "mirror/theme_pack/refresh_assets.png": "🔄刷新主题包",
    # 镜牢入口
    "mirror/road_to_mir/enter_assets.png": "🚪进入镜牢",
    "mirror/road_to_mir/select_team_stars_assets.png": "⭐选择星级",
    "mirror/road_to_mir/dreaming_star/coins_assets.png": "🪙星之币",
    "mirror/road_to_mir/select_team_confirm_assets.png": "✅队伍确认",
    "mirror/road_to_mir/select_init_ego_gifts_confirm_assets.png": "✅初始EGO确认",
    "mirror/road_to_mir/select_all_stars_assets.png": "⭐全星",
    "mirror/road_to_mir/resume_assets.png": "▶继续",
    # 队伍
    "teams/identify_assets.png": "🔍识别队伍",
    "teams/selected.png": "✅已选",
    # 巴士
    "mirror/mybus_default_distance.png": "🚌默认距离",
    "mirror/mybus_maximum_distance.png": "🚌最大距离",
    # 脑啡肽
    "enkephalin/use_lunacy_assets.png": "💎使用狂气换体",
    # 票证
    "pass/weekly_assets.png": "📅周常",
    "pass/pass_missions_assets.png": "📋通行证任务",
    "pass/pass_coin.png": "🪙通行证币",
    # 邮件
    "mail/close_assets.png": "❌关闭邮件",
    "mail/claim_all_assets.png": "📬全部领取",
    # 场景
    "scenes/story_skip_assets.png": "⏭跳过剧情",
    "scenes/story_skip_confirm_assets.png": "✅跳过确认",
    "scenes/story_meun_assets.png": "📖剧情菜单",
}

def resolve_asset(asset_key: str) -> str | None:
    """在 asset 目录中查找图片，返回相对于 project root 的路径"""
    for base in ASSET_DIRS:
        fp = base / asset_key
        if fp.exists():
            return str(fp.relative_to(PROJECT_ROOT))
    # fallback: scan broadly (handle dark/ variants etc.)
    for base in [PROJECT_ROOT / "assets" / "images"]:
        if base.is_dir():
            for root, _dirs, files in os.walk(str(base)):
                for f in files:
                    if f == os.path.basename(asset_key):
                        full = Path(root) / f
                        return str(full.relative_to(PROJECT_ROOT))
    return None


def human_name(asset_key: str) -> str:
    """图片路径 → 人话"""
    # 先查静态映射
    if asset_key in ASSET_NAMES:
        return ASSET_NAMES[asset_key]
    # 动态映射：shop_{system}.png / big_{system}.png / {system}_level_IV.png
    fn = os.path.basename(asset_key)
    for sys_en, sys_cn in SYSTEM_NAMES.items():
        if fn.startswith(f"shop_{sys_en}"):
            return f"{sys_cn}体系饰品"
        if fn.startswith(f"big_{sys_en}"):
            return f"{sys_cn}大饰品"
        if fn.startswith(f"keyword_{sys_en}"):
            return f"{sys_cn}关键词"
        if fn == f"{sys_en}_level_IV.png":
            return f"{sys_cn}四级饰品"
    # 兜底：文件名去后缀、去下划线
    name = fn.replace(".png", "").replace("_assets", "").replace("_", " ")
    return name


# ── 日志解析 ──────────────────────────────────────────
LOG_PATTERN = re.compile(
    r"\[(DEBUG|INFO|WARNING|ERROR)\]\s+"
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})"
    r"\s+\[AALC\]\s+"
    r"\.\.\\\.\.\\(.+?):(\d+):\s*(.*)"
)

IMG_PATTERN = re.compile(
    r"目标图片：([\w/\\-]+\.png)"
)

CLICK_PATTERN = re.compile(
    r"点击位置:\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)"
)

SIM_PATTERN = re.compile(
    r"相似度：([\d.]+)"
)

def parse_log(filepath: str) -> list[dict]:
    entries = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n\r")
            m = LOG_PATTERN.search(line)
            if not m:
                continue
            level, ts, module, lineno, msg = m.groups()
            # find images
            images = []
            for im in IMG_PATTERN.findall(msg):
                sim_m = SIM_PATTERN.search(msg, msg.find(im))
                sim = float(sim_m.group(1)) if sim_m else None
                resolved = resolve_asset(im)
                images.append({
                    "key": im,
                    "name": human_name(im),
                    "similarity": sim,
                    "path": resolved,
                })
            # find clicks
            clicks = [{"x": float(x), "y": float(y)} for x, y in CLICK_PATTERN.findall(msg)]
            # module short name
            mod_short = module.split("\\")[-1] if "\\" in module else module
            entries.append({
                "ts": ts,
                "level": level,
                "module": module,
                "module_short": mod_short,
                "line": int(lineno),
                "msg": msg.strip(),
                "images": images,
                "clicks": clicks,
            })
    return entries


def list_log_files():
    """扫描 issues/ 和 logs/ 下的日志"""
    files = []
    for base in [ISSUES_DIR, PROJECT_ROOT / "logs"]:
        if not base.exists():
            continue
        for child in sorted(base.iterdir(), reverse=True):
            if child.is_dir():
                for f in child.iterdir():
                    if f.suffix in (".log", ".txt") and "report" not in f.name:
                        files.append({
                            "name": f.name,
                            "path": str(f),
                            "rel": f.relative_to(PROJECT_ROOT).as_posix(),
                            "size": f.stat().st_size,
                            "dir": child.name,
                        })
            elif child.suffix == ".log":
                files.append({
                    "name": child.name,
                    "path": str(child),
                    "rel": child.relative_to(PROJECT_ROOT).as_posix(),
                    "size": child.stat().st_size,
                    "dir": "",
                })
    return files


# ── HTTP Handler ──────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/files":
            self._json_response(list_log_files())
            return

        if parsed.path == "/api/log":
            filepath = qs.get("file", [None])[0]
            if not filepath or not os.path.exists(filepath):
                self._json_response({"error": "文件不存在"}, status=404)
                return
            try:
                entries = parse_log(filepath)
                # 统计
                levels = {}
                modules = {}
                for e in entries:
                    levels[e["level"]] = levels.get(e["level"], 0) + 1
                    modules[e["module_short"]] = modules.get(e["module_short"], 0) + 1
                self._json_response({
                    "total": len(entries),
                    "entries": entries,
                    "stats": {"levels": levels, "modules": modules},
                    "file": os.path.basename(filepath),
                })
            except Exception as e:
                self._json_response({"error": str(e)}, status=500)
            return

        if parsed.path.startswith("/api/asset/"):
            # e.g. /api/asset/mirror/shop/power_up_assets.png
            asset_key = parsed.path[len("/api/asset/"):]
            for base in ASSET_DIRS:
                fp = base / asset_key
                if fp.exists():
                    self._serve_image(str(fp))
                    return
            # broad scan
            for base in [PROJECT_ROOT / "assets" / "images"]:
                if base.is_dir():
                    for root, _dirs, files in os.walk(str(base)):
                        for f in files:
                            if f == os.path.basename(asset_key):
                                self._serve_image(str(Path(root) / f))
                                return
            self._json_response({"error": "asset not found"}, status=404)
            return

        # static files
        if parsed.path == "/" or parsed.path == "":
            self.path = "/index.html"
        return super().do_GET()

    @staticmethod
    def _trim_black_border(img: Image.Image, threshold: int = 30, min_size: int = 120, padding: int = 12) -> Image.Image:
        """裁掉图片四周的黑边，并放大过小的内容到 min_size 以便查看。"""
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode != "RGBA":
            img = img.convert("RGBA")
        arr = bytearray(img.tobytes())
        w, h = img.size
        top, bottom, left, right = h, 0, w, 0
        stride = w * 4
        for y in range(h):
            row_start = y * stride
            for x in range(w):
                px = row_start + x * 4
                if arr[px + 3] == 0:
                    continue
                if arr[px] > threshold or arr[px + 1] > threshold or arr[px + 2] > threshold:
                    if y < top: top = y
                    if y > bottom: bottom = y
                    if x < left: left = x
                    if x > right: right = x
        if top <= bottom and left <= right:
            img = img.crop((left, top, right + 1, bottom + 1))
        cw, ch = img.size
        scale = min_size / max(cw, ch) if max(cw, ch) < min_size else 1.0
        if scale > 1:
            nw, nh = int(cw * scale), int(ch * scale)
            img = img.resize((nw, nh), Handler._LANCZOS)
        if padding:
            bg = Image.new("RGBA", (img.width + padding * 2, img.height + padding * 2), (0, 0, 0, 0))
            bg.paste(img, (padding, padding), img)
            img = bg
        return img

    _LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)

    def _serve_image(self, path):
        """服务裁剪+放大后的 PNG"""
        try:
            with Image.open(path) as img:
                cropped = self._trim_black_border(img)
                buf = io.BytesIO()
                cropped.save(buf, format="PNG")
                data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _serve_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        ct = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp",
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript",
            ".css": "text/css",
        }.get(ext, "application/octet-stream")
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stderr.write(f"[log_viewer] {args[0] if args else ''}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AALC 日志可视化")
    parser.add_argument("--port", "-p", type=int, default=PORT, help=f"端口 (默认 {PORT})")
    parser.add_argument("--host", type=str, default=HOST, help=f"主机 (默认 {HOST})")
    parser.add_argument("--log", "-l", type=str, default=None, help="预加载日志文件路径")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    # 写入预加载配置
    if args.log:
        cfg_path = STATIC_DIR / "preload.json"
        cfg_path.write_text(json.dumps({"log": os.path.abspath(args.log)}), encoding="utf-8")

    server = socketserver.TCPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print("\n  🪟 AALC 日志可视化面板")
    print("  ─────────────────────────────────────")
    print(f"  📡 {url}")
    print("  📁 日志目录: issues/ 和 logs/")
    print("  ❌ Ctrl+C 停止")
    print()
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        server.server_close()
        # 清理预加载配置
        cfg_path = STATIC_DIR / "preload.json"
        if cfg_path.exists():
            cfg_path.unlink()


if __name__ == "__main__":
    main()
