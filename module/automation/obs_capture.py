"""OBS WebSocket 截图后端

通过 OBS Studio 的 WebSocket 接口获取游戏画面截图，
避免直接调用 GDI BitBlt / PrintWindow 等可被 ScreenCaptureAnalytics 检测的 API。

使用前提：
1. 安装 OBS Studio 28+ (内置 obs-websocket v5)
2. OBS 中添加「游戏捕获」或「窗口捕获」源，捕获游戏窗口
3. OBS → 工具 → WebSocket 服务器设置 → 启用
4. 安装 Python 依赖: pip install obsws-python
"""

import base64
import inspect
import io
from time import time

from PIL import Image

from module.config import cfg
from module.game_and_screen import screen
from module.logger import log


class OBSCapture:
    """通过 OBS WebSocket 获取游戏画面截图"""

    def __init__(self):
        self._client = None
        self._connected = False
        self._last_connect_attempt = 0
        self._connect_cooldown = 5.0  # 连接失败后冷却时间

        self._host = "localhost"
        self._port = 4455
        self._password = ""
        self._source_name = ""
        self._image_format = "jpg"
        self._image_quality = 80
        self._refresh_settings()

        if not self._source_name:
            log.error("OBS 截图源名称未配置 (obs_source_name)，请在配置文件中填写 OBS 中捕获的源名称")

    def _refresh_settings(self) -> None:
        """从配置中刷新 OBS 连接与截图参数。"""
        self._host = getattr(cfg, "obs_host", "localhost")
        self._port = getattr(cfg, "obs_port", 4455)
        self._password = getattr(cfg, "obs_password", "") or ""
        self._source_name = getattr(cfg, "obs_source_name", "")
        self._image_format = self._normalize_image_format(getattr(cfg, "obs_image_format", "jpg"))
        self._image_quality = self._normalize_image_quality(getattr(cfg, "obs_image_quality", 80))

    @staticmethod
    def _normalize_image_format(image_format: str) -> str:
        image_format = str(image_format).strip().lower().lstrip(".")
        if image_format == "jpeg":
            return "jpg"
        if image_format not in {"jpg", "png", "webp"}:
            return "jpg"
        return image_format

    @staticmethod
    def _normalize_image_quality(quality) -> int:
        try:
            quality = int(quality)
        except (TypeError, ValueError):
            return 80
        return max(0, min(100, quality))

    @staticmethod
    def _default_capture_size() -> tuple[int, int]:
        height = int(getattr(cfg, "set_win_size", 1080) or 1080)
        width = int(height * 16 / 9)
        return width, height

    def _resolve_capture_size(self) -> tuple[int, int]:
        """推断 OBS 应返回的目标尺寸，避免无意义的全尺寸编码与传输。"""
        try:
            if getattr(screen.handle, "_hwnd", 0) != 0:
                rect = screen.handle.rect(client=True)
                width = max(0, rect[2] - rect[0])
                height = max(0, rect[3] - rect[1])
                if width >= 8 and height >= 8:
                    return width, height
        except Exception:
            pass

        return self._default_capture_size()

    def connect(self) -> bool:
        """连接到 OBS WebSocket 服务器"""
        self._refresh_settings()

        if self._connected and self._client:
            return True

        # 冷却期内不重试
        if time() - self._last_connect_attempt < self._connect_cooldown:
            return False

        self._last_connect_attempt = time()

        try:
            import obsws_python as obs
        except ImportError:
            log.error(
                "缺少 obsws-python 依赖，请执行: pip install obsws-python\n"
                "或者: uv add obsws-python"
            )
            return False

        try:
            self._client = obs.ReqClient(
                host=self._host,
                port=self._port,
                password=self._password if self._password else None,
                timeout=3,
            )
            self._connected = True
            log.info(f"已连接到 OBS WebSocket ({self._host}:{self._port})")
            return True
        except Exception as e:
            self._connected = False
            self._client = None
            log.error(f"连接 OBS WebSocket 失败: {e}")
            return False

    def build_capture_error_message(self, error: str) -> str:
        """将内部错误转换为面向用户的提示。"""
        self._refresh_settings()

        if error == "source_name_missing":
            return "OBS 截图源名称未配置，请在设置中填写 OBS 中捕获的源名称。"

        if error == "connect_failed":
            return (
                f"无法连接到 OBS WebSocket ({self._host}:{self._port})，"
                "请检查 OBS 是否已启动，以及地址、端口、密码是否填写正确。"
            )

        return f"OBS 截图不可用: {error}"

    def take_screenshot(self, gray: bool = True, return_stats: bool = False) -> Image.Image | tuple[Image.Image | None, dict]:
        """请求 OBS 截取一帧画面并返回 PIL Image

        Args:
            gray: 是否转为灰度图

        Returns:
            PIL.Image.Image: 截图图像，失败则返回 None
        """
        self._refresh_settings()

        if not self.connect():
            if return_stats:
                return None, {"error": "connect_failed"}
            return None

        if not self._source_name:
            log.error("OBS 截图源名称未配置 (obs_source_name)")
            if return_stats:
                return None, {"error": "source_name_missing"}
            return None

        try:
            capture_width, capture_height = self._resolve_capture_size()
            response, request_stats = self._get_source_screenshot(capture_width, capture_height)

            # 解码 Base64 图像数据
            # OBS 返回格式: "data:image/png;base64,iVBORw0KG..."
            decode_start = time()
            data_uri = response.image_data
            if "," in data_uri:
                _, base64_str = data_uri.split(",", 1)
            else:
                base64_str = data_uri

            image_bytes = base64.b64decode(base64_str)
            image = Image.open(io.BytesIO(image_bytes))
            image.load()

            # 转换颜色模式
            if image.mode == "RGBA":
                image = image.convert("RGB")

            if gray:
                image = image.convert("L")

            stats = {
                **request_stats,
                "decode_ms": (time() - decode_start) * 1000,
                "returned_size": image.size,
                "returned_mode": image.mode,
                "payload_chars": len(data_uri),
            }

            if return_stats:
                return image, stats
            return image

        except Exception as e:
            log.error(f"OBS 截图失败: {e}")
            # 连接可能断开，重置状态
            self._connected = False
            self._client = None
            if return_stats:
                return None, {"error": str(e)}
            return None

    def validate_capture_ready(self) -> tuple[bool, str]:
        """启动任务前预检 OBS 截图链路是否可用。"""
        self._refresh_settings()

        if not self._source_name:
            return False, self.build_capture_error_message("source_name_missing")

        # 预检前强制清理失败冷却，避免用户修好 OBS 后立即重试仍被旧状态拦截。
        self.disconnect()
        self._last_connect_attempt = 0
        image, stats = self.take_screenshot(gray=False, return_stats=True)
        if image is None:
            return False, self.build_capture_error_message(stats.get("error", "unknown"))

        return True, ""

    def _get_source_screenshot(self, width: int, height: int):
        method = self._client.get_source_screenshot
        parameters = inspect.signature(method).parameters
        request_start = time()

        if {"width", "height", "quality"}.issubset(parameters):
            try:
                response = method(
                    name=self._source_name,
                    img_format=self._image_format,
                    width=width,
                    height=height,
                    quality=self._image_quality,
                )
                return response, {
                    "request_ms": (time() - request_start) * 1000,
                    "request_width": width,
                    "request_height": height,
                    "image_format": self._image_format,
                    "image_quality": self._image_quality,
                }
            except Exception:
                if self._image_format != "png":
                    fallback_start = time()
                    response = method(
                        name=self._source_name,
                        img_format="png",
                        width=width,
                        height=height,
                        quality=-1,
                    )
                    return response, {
                        "request_ms": (time() - fallback_start) * 1000,
                        "request_width": width,
                        "request_height": height,
                        "image_format": "png",
                        "image_quality": -1,
                    }
                raise

        response = method(
            name=self._source_name,
            img_format=self._image_format,
        )
        return response, {
            "request_ms": (time() - request_start) * 1000,
            "request_width": width,
            "request_height": height,
            "image_format": self._image_format,
            "image_quality": self._image_quality,
        }

    def benchmark_screenshot(self, gray: bool = False, count: int = 10) -> dict:
        """对 OBS 截图进行粗略阶段性性能统计。"""
        total_request_ms = 0.0
        total_decode_ms = 0.0
        success = 0
        last_stats = {}

        for _ in range(count):
            image, stats = self.take_screenshot(gray=gray, return_stats=True)
            if image is not None:
                success += 1
                total_request_ms += stats.get("request_ms", 0.0)
                total_decode_ms += stats.get("decode_ms", 0.0)
                last_stats = stats

        avg_request_ms = total_request_ms / success if success else 0.0
        avg_decode_ms = total_decode_ms / success if success else 0.0

        return {
            "success": success,
            "count": count,
            "avg_request_ms": avg_request_ms,
            "avg_decode_ms": avg_decode_ms,
            "avg_total_ms": avg_request_ms + avg_decode_ms,
            "last_stats": last_stats,
        }

    def disconnect(self):
        """断开 OBS WebSocket 连接"""
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._connected = False
            log.info("已断开 OBS WebSocket")


# 全局单例（懒加载）
_obs_capture_instance: OBSCapture | None = None


def get_obs_capture() -> OBSCapture:
    """获取 OBSCapture 全局单例"""
    global _obs_capture_instance
    if _obs_capture_instance is None:
        _obs_capture_instance = OBSCapture()
    return _obs_capture_instance


def disconnect_obs_capture() -> None:
    """断开已创建的 OBS 截图单例连接。"""
    if _obs_capture_instance is not None:
        _obs_capture_instance.disconnect()
