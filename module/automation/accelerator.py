import re
import xml.etree.ElementTree as ET
from time import sleep

from adbutils import adb

from module.config import cfg
from module.logger import log

ACCELERATOR_PRESETS: dict[str, dict] = {
    "custom": {
        "name": "自定义",
        "package": None,
        "acc_button_ids": [],
        "close_button_ids": [],
        "close_button_texts": [],
    },
    "leigod": {
        "name": "雷神加速器",
        "package": "com.nn.accelerator.box",
        "target_activity": ".activity.MainActivity",
        "acc_button_ids": [
            "com.nn.accelerator.box:id/acc_view2",
        ],
        "close_button_ids": [
            "com.nn.accelerator.box:id/iv_close",
        ],
        "close_button_texts": ["跳过", "我知道了"],
    },
}


def _get_preset_config() -> dict:
    preset_key = cfg.get_value("lab_simulator_accelerator_preset", "custom")
    return ACCELERATOR_PRESETS.get(preset_key, ACCELERATOR_PRESETS["custom"])


def _get_package() -> str:
    preset = _get_preset_config()
    if preset.get("package"):
        return preset["package"]
    return cfg.get_value("lab_simulator_accelerator_package", "")


def _get_adb_device():
    if cfg.simulator_type == 0:
        from module.automation.input_handlers.simulator.mumu_control import MumuControl

        conn = MumuControl.connection_device
        if conn is None:
            log.warning("加速器：MumuControl.connection_device 为空，无法获取 ADB 设备")
            return None
        port = conn.get_mumu_adb_port()
        try:
            return adb.device(port)
        except Exception as e:
            log.warning(f"加速器：无法通过端口 {port} 获取 ADB 设备: {e}")
            return None
    else:
        from module.automation.input_handlers.simulator.simulator_control import SimulatorControl

        conn = SimulatorControl.connection_device
        if conn is None:
            log.warning("加速器：SimulatorControl.connection_device 为空，无法获取 ADB 设备")
            return None
        if conn.simulator_device is None:
            log.warning("加速器：simulator_device 为空，无法获取 ADB 设备")
            return None
        return conn.simulator_device


def _check_acceleration_active(device) -> bool:
    try:
        result = device.shell("ls /sys/class/net/ 2>/dev/null")
        interfaces = (result or "").strip().split()
        tun_interfaces = [i for i in interfaces if i.startswith("tun")]
        if tun_interfaces:
            log.info(f"加速器：检测到加速已生效 (tun 接口: {', '.join(tun_interfaces)})")
            return True
    except Exception as e:
        log.warning(f"加速器：检测加速状态失败: {e}")
    return False


def _check_app_running(device, package: str) -> bool:
    try:
        result = device.shell(f"pidof {package}")
        return bool(result and result.strip())
    except Exception as e:
        log.warning(f"加速器：检查进程 {package} 失败: {e}")
        return False


def _launch_app(device, package: str, target_activity: str | None):
    """强制停止并用 am start 直接启动目标 Activity，跳过闪屏。"""
    try:
        device.shell(f"am force-stop {package} 2>/dev/null")
        sleep(0.5)
        if target_activity:
            device.shell(f"am start -n {package}/{target_activity} -W 2>/dev/null")
        else:
            device.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1 2>/dev/null")
        log.info(f"加速器：已重启 {package}" + (f" -> {target_activity}" if target_activity else ""))
    except Exception as e:
        log.error(f"加速器：启动 {package} 失败: {e}")


def _dump_ui(device) -> str | None:
    try:
        device.shell("pkill -9 uiautomator 2>/dev/null")
        device.shell("uiautomator dump 2>/dev/null")
        result = device.shell("cat /sdcard/window_dump.xml 2>/dev/null")
        if result and "<hierarchy" in result:
            log.debug(f"加速器：UI dump 成功 ({len(result)} bytes)")
            return result
        log.warning(f"加速器：UI dump 返回内容异常: {result[:200] if result else '空'}")
    except Exception as e:
        log.warning(f"加速器：UI dump 失败: {e}")
    return None


def _parse_bounds(bounds_str: str) -> tuple[int, int] | None:
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
    if m:
        x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return ((x1 + x2) // 2, (y1 + y2) // 2)
    return None


def _find_element_center(ui_xml: str, *, resource_id: str | None = None, text: str | None = None, clickable_only: bool = True) -> tuple[int, int] | None:
    try:
        root = ET.fromstring(ui_xml)
    except ET.ParseError:
        return None

    candidates = []

    def _walk(node):
        for child in node:
            _walk(child)

        bounds_str = node.get("bounds", "")
        if not bounds_str:
            return
        rid = node.get("resource-id", "")
        txt = node.get("text", "")
        clickable = node.get("clickable", "false") == "true"
        if resource_id and resource_id in rid:
            center = _parse_bounds(bounds_str)
            if center:
                candidates.append((center, clickable))
        if text and txt == text:
            center = _parse_bounds(bounds_str)
            if center:
                candidates.append((center, clickable))

    _walk(root)

    if clickable_only:
        candidates = [c for c in candidates if c[1]]
    if candidates:
        return candidates[0][0]
    return None


def _dismiss_popups_with_xml(device, ui_xml: str | None, preset: dict) -> bool:
    if not ui_xml:
        return False

    close_ids = preset.get("close_button_ids", [])
    close_texts = preset.get("close_button_texts", [])

    log.debug(f"加速器：弹窗检测 (close_ids={close_ids}, close_texts={close_texts})")

    for rid in close_ids:
        center = _find_element_center(ui_xml, resource_id=rid, clickable_only=False)
        if center:
            log.info(f"加速器：检测到弹窗关闭按钮 (resource-id: {rid})，坐标 {center}")
            try:
                device.shell(f"input tap {center[0]} {center[1]}")
                sleep(1)
                return True
            except Exception as e:
                log.warning(f"加速器：关闭弹窗失败: {e}")
                return False

    for text in close_texts:
        center = _find_element_center(ui_xml, text=text, clickable_only=False)
        if center:
            log.info(f"加速器：检测到弹窗关闭文字 '{text}'，坐标 {center}")
            try:
                device.shell(f"input tap {center[0]} {center[1]}")
                sleep(1)
                return True
            except Exception as e:
                log.warning(f"加速器：关闭弹窗失败: {e}")
                return False

    return False


def _find_acc_button_in_xml(ui_xml: str, preset: dict) -> tuple[int, int] | None:
    for rid in preset.get("acc_button_ids", []):
        center = _find_element_center(ui_xml, resource_id=rid)
        if center:
            log.info(f"加速器：自动检测到加速按钮 (resource-id: {rid})，坐标 {center}")
            return center
    return None


def _click_acc_button(device, tap_x: int, tap_y: int):
    try:
        device.shell(f"input tap {tap_x} {tap_y}")
        log.info(f"加速器：已点击加速按钮 ({tap_x}, {tap_y})")
    except Exception as e:
        log.error(f"加速器：点击加速按钮失败: {e}")


def ensure_accelerator():
    if not cfg.get_value("lab_simulator_launch_accelerator", False):
        return

    preset = _get_preset_config()
    package = _get_package()

    if not package:
        log.warning("加速器：未配置加速器包名，跳过")
        return

    preset_name = cfg.get_value("lab_simulator_accelerator_preset", "custom")
    log.info(f"加速器：开始检查 (预设: {preset.get('name', '自定义')}, 包名: {package})")

    device = _get_adb_device()
    if device is None:
        log.warning("加速器：无法获取 ADB 设备，跳过检查")
        return

    if _check_acceleration_active(device):
        log.info("加速器：加速已生效，无需操作")
        return

    log.info(f"加速器：加速未生效，正在重启 {package} 确保干净状态")
    _launch_app(device, package, preset.get("target_activity"))

    delay = float(cfg.get_value("lab_simulator_accelerator_delay", 3.0))
    log.info(f"加速器：等待 {delay:.1f} 秒加载 UI")
    sleep(delay)

    try:
        focus = device.shell("dumpsys window 2>/dev/null | grep mCurrentFocus")
        log.info(f"加速器：当前界面 {focus.strip()}")
    except Exception:
        pass

    ui_xml = _dump_ui(device)
    if ui_xml:
        if _dismiss_popups_with_xml(device, ui_xml, preset):
            sleep(2)
            ui_xml = _dump_ui(device)
    else:
        log.info("加速器：UI dump 不可用，跳过弹窗检测")

    tap_x = 0
    tap_y = 0

    if ui_xml and preset_name != "custom":
        auto_center = _find_acc_button_in_xml(ui_xml, preset)
        if auto_center:
            tap_x, tap_y = auto_center
        else:
            log.warning("加速器：UI 中未找到加速按钮")
            log.info(f"加速器：UI XML 预览: {ui_xml[:500]}")

    if tap_x == 0 and tap_y == 0:
        tap_x = int(cfg.get_value("lab_simulator_accelerator_tap_x", 0))
        tap_y = int(cfg.get_value("lab_simulator_accelerator_tap_y", 0))
        if tap_x > 0 and tap_y > 0:
            log.info(f"加速器：使用配置坐标 ({tap_x}, {tap_y})")

    if tap_x > 0 and tap_y > 0:
        _click_acc_button(device, tap_x, tap_y)
        log.info("加速器：等待加速生效")
        for i in range(5):
            sleep(3)
            if _check_acceleration_active(device):
                log.info("加速器：加速已成功开启，游戏将自动启动")
                return
        log.warning("加速器：点击加速按钮后 15 秒内未检测到加速，请检查配置")
    else:
        log.warning("加速器：未检测到加速按钮位置且未配置坐标，请在设置中配置")
