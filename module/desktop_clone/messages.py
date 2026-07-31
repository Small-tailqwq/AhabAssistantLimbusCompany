"""Translation helpers for desktop-clone runtime and IPC messages."""

from __future__ import annotations

import re

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

CONTEXT = "DesktopCloneMessages"

# Keep runtime-only strings visible to pyside6-lupdate.
_TRANSLATABLE_MESSAGES = (
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "桌面分身尚未启动"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "正在创建 Windows Child Session"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "正在同步配置并启动分身任务"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "正在取消分身启动"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "正在请求分身任务安全停止"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "桌面分身已停止"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "桌面分身尚未确认注销"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "桌面分身 IPC 写入不完整：{0}/{1}",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身 AALC 已就绪"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身任务运行中"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身任务已停止"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身任务已完成"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身任务已结束：{0}"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Child Session {0} 已连接，正在启动 AALC",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "启动桌面分身失败：{0}"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "同步桌面分身配置失败：{0}"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "在 Child Session 启动 AALC 失败：{0}",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "同步分身任务状态失败：{0}"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "请求分身任务停止失败：{0}"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "切换分身任务暂停状态失败：{0}",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 桌面分身宿主意外退出（exit={0}）",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 桌面分身意外断开（reason={0}）",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 宿主上报了错误 Child Session：reported={0}, actual={1}",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "桌面分身在 {0} 秒内未完成登录，已终止 RDP 宿主并清理 Child Session。"
        "若出现凭据窗口，请注销 Windows 后重新登录再试",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 已连接，正在等待 Windows 完成 Child Session 登录",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "桌面分身首次初始化尚未完成，{0} 秒后自动重试（{1}/3）",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP Child Session 连接失败"
        "（stage={0}, code={1}, extended={2}）：{3}",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "桌面分身仍有残留会话，请先执行“停止任务并注销分身”",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "桌面分身正在停止，请等待注销完成后重试",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "检测到已有 Child Session；AALC 不会接管或注销其他程序创建的会话",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "模拟器模式不需要且不支持桌面分身",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "《边狱公司》已在主桌面运行，请先退出游戏后再启动桌面分身。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Steam 将《边狱公司》启动到了桌面分身之外，已拒绝继续自动化。"
        "请退出 Steam 和游戏后重试（{0}）。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Child AALC 尚未连接，无法停止任务",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "取消分身启动时未能确认 Child Session 已注销",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "Child AALC 意外断开"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 桌面分身宿主连接已断开",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "检测到非 AALC 管理的 Child Session {0}，为避免注销其中的程序，AALC 不会接管。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 宿主可用：{0}。",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "RDP 宿主不可用：{0}"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "Steam 可用：{0}。"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "Steam 不可用：{0}"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "桌面分身仅支持 Windows。"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Windows Home 未列入首发支持范围。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "当前进程没有管理员权限，无法启用 Child Session。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Child Session API 可用，当前状态：{0}。",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "已启用"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "未启用"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Child Session API 不可用：{0}",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "RDP 端口：{0}。"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Windows 远程桌面连接未启用，无法创建本机 Child Session。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 本机端口 {0} 未监听，请检查 Remote Desktop Services。",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "UU远程"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "MuMu远程"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "、"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "检测到正在运行的远程控制软件：{0}。"
        "Child Session 会成为新的活动桌面，远程控制画面可能被切换到分身；"
        "确认风险后可以继续启动。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "检测到远程控制后台服务：{0}。"
        "这类服务通常常驻且难以彻底退出，不会阻止桌面分身启动。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "未找到 Steam.exe；桌面分身必须通过 Steam 完成账户验证",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Steam 已在其他 Windows Session 运行，无法保证登录态和游戏进程进入桌面分身。"
        "请完全退出 Steam 后重试（{0}）。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "启动 RDP Child Session 失败：{0}",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "读取 RDP Child Session 状态失败：{0}",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "断开 RDP 失败：{0}"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "停止 RDP ActiveX 失败：{0}"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "注销 Child Session 失败（Win32 错误 {0}）",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "读取 Child Session 失败（Win32 错误 {0}）",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "当前 Child Session 已不属于 AALC，拒绝注销。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 宿主尚未确认 Child Session 所有权，拒绝注销。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 登录完成后的 Child Session 与连接期间观察值不一致。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP ActiveX 未确认已停止，拒绝报告 Child Session 注销完成。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "检测到已有 Child Session，AALC 拒绝接管。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "启动前无法确认 Child Session 为空。",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身任务已经在运行"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "重新加载分身配置失败：{0}",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "分身任务未能通过启动前检查",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "分身任务仍在运行，暂不退出 Child AALC",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Windows 尚未确认 Child Session 已注销",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "{0}（Win32 错误 {1}）",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法启用 Windows Child Session",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法禁用 Windows Child Session",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法读取 Windows Child Session 状态",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法取得 Windows Child Session ID",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法注销 Child Session {0}",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "AALC 桌面分身"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "关闭声音"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "关闭输入"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "[分身] {0}"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "[日志同步] 队列已丢弃较早的 {0} 条日志",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "[日志同步] 管道断开期间丢失 {0} 条日志",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "Child AALC 意外断开（peer_pid={0}）"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Child AALC 意外断开（peer_pid={0}）；分身启动崩溃记录：\n{1}",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "桌面分身在 {0} 秒内未完成登录，已终止 RDP 宿主并清理 Child Session。"
        "若出现凭据窗口，请注销 Windows 后重新登录再试；分身启动崩溃记录：\n{1}",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "正在创建 AALC 桌面分身...",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "AALC 桌面分身已断开",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 已连接，但 Windows 未返回 Child Session ID。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP ActiveX 未接受 ConnectToChildSession=true。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法读取 Windows Child Session 启用状态。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Windows Child Session 尚未启用。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Windows Child Session 已在本次登录后启用。"
        "请注销 Windows 并重新登录后再启动桌面分身；"
        "不要在凭据窗口中输入密码。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Windows Child Session 已成功启用。"
        "请注销 Windows 并重新登录一次，使免凭据登录生效；"
        "重新登录后无需再次设置。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法读取当前 Windows 登录标识",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "无法取得 LOCALAPPDATA，不能记录 Child Session 初始化状态",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Winlogon 正在显示拒绝断开现有会话对话框。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Winlogon 正在显示无权限对话框。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "Winlogon 已静默终止登录。",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "RDP 登录被拒绝。"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 登录凭据无效；Child Session 未完成免凭据登录。",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "Windows 密码已过期。"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "RDP 登录处理失败。"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 登录阶段发生错误。",
    ),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 客户端发生致命错误。",
    ),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "RDP 连接失败。"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "Windows 未返回 Child Session ID"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "Child AALC 尚未连接"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身任务结果缺少状态增量"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身状态增量字段不合法"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身队伍队列不合法"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "分身状态字段 {0} 类型不合法"),
    QT_TRANSLATE_NOOP("DesktopCloneMessages", "无法解码远端错误信息"),
    QT_TRANSLATE_NOOP(
        "DesktopCloneMessages",
        "RDP 宿主上报了无效的 Child Session ID：{0}",
    ),
)


def translate_message(source: str, *args: object) -> str:
    translated = QCoreApplication.translate(CONTEXT, source)
    return translated.format(*args) if args else translated


def translate_remote_message(message: str) -> str:
    """Translate the fixed portion of a C# host or child IPC error."""
    exact_sources = (
        "当前 Child Session 已不属于 AALC，拒绝注销。",
        "RDP 宿主尚未确认 Child Session 所有权，拒绝注销。",
        "RDP 登录完成后的 Child Session 与连接期间观察值不一致。",
        "RDP ActiveX 未确认已停止，拒绝报告 Child Session 注销完成。",
        "检测到已有 Child Session，AALC 拒绝接管。",
        "启动前无法确认 Child Session 为空。",
        "RDP 已连接，但 Windows 未返回 Child Session ID。",
        "RDP ActiveX 未接受 ConnectToChildSession=true。",
        "无法读取 Windows Child Session 启用状态。",
        "Windows Child Session 尚未启用。",
        "Winlogon 正在显示拒绝断开现有会话对话框。",
        "Winlogon 正在显示无权限对话框。",
        "Winlogon 已静默终止登录。",
        "RDP 登录被拒绝。",
        "RDP 登录凭据无效；Child Session 未完成免凭据登录。",
        "Windows 密码已过期。",
        "RDP 登录处理失败。",
        "RDP 登录阶段发生错误。",
        "RDP 客户端发生致命错误。",
        "RDP 连接失败。",
        "分身任务已经在运行",
        "分身任务未能通过启动前检查",
        "分身任务仍在运行，暂不退出 Child AALC",
    )
    if message in exact_sources:
        return translate_message(message)

    for prefix in (
        "启动 RDP Child Session 失败",
        "读取 RDP Child Session 状态失败",
        "断开 RDP 失败",
        "停止 RDP ActiveX 失败",
        "重新加载分身配置失败",
    ):
        separator = prefix + "："
        if message.startswith(separator):
            return translate_message(
                prefix + "：{0}",
                translate_remote_message(message[len(separator) :]),
            )

    win32_match = re.fullmatch(
        r"(注销|读取) Child Session 失败（Win32 错误 (\d+)）",
        message,
    )
    if win32_match:
        source = (
            "注销 Child Session 失败（Win32 错误 {0}）"
            if win32_match.group(1) == "注销"
            else "读取 Child Session 失败（Win32 错误 {0}）"
        )
        return translate_message(source, win32_match.group(2))
    return message
