"""为 myapp_en.ts 中空 translation(unfinished) 条目补齐英文翻译。

只替换空翻译的 <translation> 标签内容，保持文件其他格式不变。
"""
import re
import xml.etree.ElementTree as ET

TRANSLATIONS = {
    ("BaseCheckBox", "简单键盘寻路（始终按↑键，避免鼠标拖动）"): "Simple keyboard pathfinding (always press ↑ to avoid mouse dragging)",
    ("BaseCheckBox", "镜牢资源收集模式（收集卡包地图截图用于模型训练）"): "Mirror Dungeon resource collection mode (collect theme pack map screenshots for model training)",
    ("BaseInfoBar", "检测更新失败"): "Update check failed",
    ("BaseInfoBar", "请求超时，请检查网络连接"): "Request timed out, please check your network connection",
    ("BaseInfoBar", "图片保存为 screenshots/screenshot_{time_str}.png"): "Image saved to screenshots/screenshot_{time_str}.png",
    ("BaseInfoBar", "图片保存为 screenshots/quick_screenshot_{time_str}.png"): "Image saved to screenshots/quick_screenshot_{time_str}.png",
    ("BaseInfoBar", "截图失败"): "Screenshot failed",
    ("BaseInfoBar", "检测更新失败(╥﹏╥)"): "Update check failed (╥﹏╥)",
    ("BasePushSettingCard", "选择"): "Choose",
    ("BasePushSettingCard", "罗技 DLL 路径"): "Logitech DLL path",
    ("BasePushSettingCard", "雷蛇 DLL 路径"): "Razer DLL path",
    ("BasePushSettingCard", "OBS WebSocket 地址"): "OBS WebSocket address",
    ("BasePushSettingCard", "OBS WebSocket 密码"): "OBS WebSocket password",
    ("BasePushSettingCard", "OBS 截图源名称"): "OBS screenshot source name",
    ("BasePushSettingCard", "加速器包名"): "Accelerator package name",
    ("BasePushSettingCard", "加速按钮 X 坐标"): "Accelerator button X coordinate",
    ("BasePushSettingCard", "加速按钮 Y 坐标"): "Accelerator button Y coordinate",
    ("BasePushSettingCard", "启动后等待时间(秒)"): "Startup wait time (seconds)",
    ("BasePushSettingCard", "(已设置)"): "(Set)",
    ("BasePushSettingCard", "(未设置)"): "(Not set)",
    ("BasePushSettingCard", "日志复现工具"): "Log replay tool",
    ("BasePushSettingCard", "导入问题日志，热切换配置文件进行调试"): "Import issue logs and hot-switch config files for debugging",
    ("BasePushSettingCard", "资产管理"): "Asset manager",
    ("BasePushSettingCard", "可视化浏览、分类、替换游戏图片资产"): "Visually browse, categorize, and replace game image assets",
    ("BasePushSettingCard", "新手提示工具"): "Tutorial skip tool",
    ("BasePushSettingCard", "直接修改游戏存档，关闭或恢复所有新手引导和红点提示"): "Directly modify the game save to disable or restore all tutorial prompts and red dot notifications",
    ("BasePushSettingCard", "驱动 DLL 管理器"): "Driver DLL manager",
    ("BasePushSettingCard", "检测罗技/雷蛇驱动 DLL 状态、启动 G HUB、管理版本更新封锁"): "Check Logitech/Razer driver DLL status, launch G HUB, manage version update blocks",
    ("BasePushSettingCard", "滚轮滚动测试"): "Scroll wheel test",
    ("BasePushSettingCard", "临时工具：测试向游戏窗口或 MuMu 模拟器发送滚轮滚动输入"): "Temporary tool: test sending scroll wheel input to the game window or MuMu emulator",
    ("BasePushSettingCard", "零协汉化更新"): "Zero Association patch update",
    ("BasePushSettingCard", "检测零协汉化版本，自动下载更新汉化文件"): "Check the Zero Association patch version and auto-download updated files",
    ("BaseSettingCardGroup", "调试"): "Debug",
    ("ComboBoxSettingCard", "OBS 截图编码格式"): "OBS screenshot encoding format",
    ("ComboBoxSettingCard", "推荐使用 jpg；png 更稳但通常更慢"): "jpg is recommended; png is more stable but usually slower",
    ("ComboBoxSettingCard", "加速器类型"): "Accelerator type",
    ("ComboBoxSettingCard", "选择预设可自动配置包名和按钮检测规则"): "Selecting a preset auto-configures the package name and button detection rules",
    ("ComboBoxSettingCard", "自定义"): "Custom",
    ("ComboBoxSettingCard", "雷神加速器"): "LeiShen accelerator",
    ("ComboBoxSettingCard", "Clash Meta"): "Clash Meta",
    ("CustomizeSettingsModule", "起始之星"): "Star of the Beginning",
    ("CustomizeSettingsModule", "层积星云"): "Cumulating Starcloud",
    ("CustomizeSettingsModule", "星际旅行"): "Interstellar Travel",
    ("CustomizeSettingsModule", "倾落的流星雨"): "Star-shower",
    ("CustomizeSettingsModule", "双星商店"): "Binary Star-shop",
    ("CustomizeSettingsModule", "卫星商店"): "Moon Star-shop",
    ("CustomizeSettingsModule", "星云的宠爱"): "Favor of the Nebulae",
    ("CustomizeSettingsModule", "星芒的引导"): "Starlight Guidance",
    ("CustomizeSettingsModule", "偶然的彗星"): "Chance Comet",
    ("CustomizeSettingsModule", "全面的可能性"): "Perfected Possibility",
    ("FarmingInterfaceLeft", "停止中..."): "Stopping...",
    ("InfiniteBattles", "主线模式(测试)"): "Story mode (test)",
    ("IssueReplay", "重新导入成功"): "Re-imported successfully",
    ("LabelWithCheckBoxes", "日/周常任务"): "Daily/weekly tasks",
    ("LabelWithCheckBoxes", "通行证等级奖励"): "Pass level rewards",
    ("MainWindow", "停止超时"): "Stop timeout",
    ("MainWindow", "脚本仍在收尾，请稍后再尝试退出程序。"): "The script is still wrapping up. Please try exiting again later.",
    ("MainWindow", "退出超时"): "Exit timeout",
    ("MainWindow", "公告线程未能在 5 秒内结束，请稍后再试。"): "The announcement thread did not finish within 5 seconds. Please try again later.",
    ("Nav", "调试"): "Debug",
    ("NormalTextButton", "暂停"): "Pause",
    ("ObserveEgoGiftModule", "启用观测"): "Enable observation",
    ("ObserveEgoGiftModule", "泛用"): "General",
    ("ObserveEgoGiftModule", "体系"): "Status",
    ("ObserveEgoGiftModule", "等级"): "Tier",
    ("ObserveEgoGiftModule", "所在行"): "Row",
    ("ObserveEgoGiftModule", "所在列"): "Column",
    ("ObserveEgoGiftModule", '<div style="font-size: 15px; line-height: 1.6;">知道你们想要什么<br>2026-06 蜘蛛巢良秀专武在泛用-3级-4行-8列</div>'): '<div style="font-size: 15px; line-height: 1.6;">We know what you want<br>2026-06 Ryoshu\'s exclusive EGO in Spider Nest at General - Tier 4 - Row 8 - Column 8</div>',
    ("ObserveGiftSelectionRow", "移除或清空当前控件组"): "Remove or clear the current control group",
    ("PageMirror", "配置文件中缺少以下字段：\n- {0}\n\n将使用默认值填充这些字段。是否继续？"): "The configuration file is missing the following fields:\n- {0}\n\nThese fields will be filled with default values. Continue?",
    ("PageMirror", "已成功从文件创建队伍 {0}"): "Team {0} was successfully created from the file",
    ("PageMirror", "创建队伍时出错：{0}"): "Error creating team: {0}",
    ("PushSettingCardChance", "模拟器启动后等待主界面超时时间(秒)"): "Emulator main menu wait timeout after launch (seconds)",
    ("PushSettingCardChance", "PC启动后等待主界面超时时间(秒)"): "PC main menu wait timeout after launch (seconds)",
    ("PushSettingCardChance", "OBS WebSocket 端口"): "OBS WebSocket port",
    ("PushSettingCardChance", "OBS 截图压缩质量"): "OBS screenshot compression quality",
    ("PushSettingCardChance", "仅对有损格式生效，推荐 60~80"): "Only applies to lossy formats; 60~80 recommended",
    ("ScreenshotCard", "快速截图"): "Quick screenshot",
    ("ScreenshotCard", "截图"): "Screenshot",
    ("ScreenshotCard", "直接截图或设置窗口后截图"): "Screenshot directly or set a window first",
    ("SettingInterface", "选择游戏路径"): "Select game path",
    ("SettingInterface", "选择罗技驱动 DLL"): "Select Logitech driver DLL",
    ("SettingInterface", "选择雷蛇驱动 DLL"): "Select Razer driver DLL",
    ("SettingInterface", "(已设置)"): "(Set)",
    ("SettingInterface", "(未设置)"): "(Not set)",
    ("SwitchSettingCard", "调试模式"): "Debug mode",
    ("SwitchSettingCard", "开启后显示调试子选项；关闭后会自动重置所有子调试开关"): "Shows debug sub-options when enabled; all sub debug switches reset when disabled",
    ("SwitchSettingCard", "镜牢寻路调试"): "Mirror Dungeon pathfinding debug",
    ("SwitchSettingCard", "记录镜牢寻路额外日志，并保存调试截图和元数据到 logs/route_map_debug 目录"): "Log extra Mirror Dungeon pathfinding info and save debug screenshots and metadata to the logs/route_map_debug directory",
    ("SwitchSettingCard", "纽本调试"): "Thread Dungeon debug",
    ("SwitchSettingCard", "在纽本运行时保存匹配过程截图到 logs/thread_dungeon_debug 目录"): "Save matching-process screenshots to the logs/thread_dungeon_debug directory while Thread Dungeon is running",
    ("SwitchSettingCard", "重试调试"): "Retry debug",
    ("SwitchSettingCard", "在尝试退出、重启镜牢时输出识别情况的日志断点"): "Output recognition log breakpoints when attempting to exit or restart Mirror Dungeon",
    ("SwitchSettingCard", "商店调试"): "Shop debug",
    ("SwitchSettingCard", "记录商店各操作的详细识别和点击日志，并保存调试截图到 logs/shop_debug 目录"): "Log detailed recognition and click operations in shops and save debug screenshots to the logs/shop_debug directory",
    ("SwitchSettingCard", "镜牢事件调试"): "Mirror Dungeon event debug",
    ("SwitchSettingCard", "在镜牢事件判定各关键节点保存截图到 logs/event_debug 目录"): "Save screenshots at key event checkpoints to the logs/event_debug directory",
    ("SwitchSettingCard", "使用系统代理"): "Use system proxy",
    ("SwitchSettingCard", "启用后自动读取 Windows 系统代理设置（如 Clash），适用于有代理工具的网络环境"): "Read Windows system proxy settings (e.g., Clash) automatically when enabled; suitable for networks using a proxy tool",
    ("SwitchSettingCard", "启用罗技驱动模拟"): "Enable Logitech driver simulation",
    ("SwitchSettingCard", "使用独立 DLL 进行硬件级键鼠输入模拟，需要正确配置可用的罗技驱动 DLL 路径"): "Use a separate DLL for hardware-level keyboard/mouse input simulation; requires a valid Logitech driver DLL path",
    ("SwitchSettingCard", "启用仿生轨迹"): "Enable bionic trajectory",
    ("SwitchSettingCard", "启用后使用仿生鼠标轨迹与仿生点击偏移；关闭后回退为普通分段移动"): "Uses bionic mouse trajectories and click offsets when enabled; falls back to normal segmented movement when disabled",
    ("SwitchSettingCard", "启用雷蛇驱动模拟"): "Enable Razer driver simulation",
    ("SwitchSettingCard", "使用独立 DLL 进行硬件级键鼠输入模拟，需安装 Razer Synapse 3 并配置可用的雷蛇驱动 DLL 路径"): "Use a separate DLL for hardware-level keyboard/mouse input simulation; requires Razer Synapse 3 and a valid Razer driver DLL path",
    ("SwitchSettingCard", "启用 OBS 截图"): "Enable OBS screenshot",
    ("SwitchSettingCard", "通过 OBS WebSocket 获取截图，规避直接调用系统截图接口"): "Capture screenshots via OBS WebSocket instead of the system screenshot API",
    ("SwitchSettingCard", "模拟器启动加速器"): "Auto-launch accelerator with emulator",
    ("SwitchSettingCard", "启动游戏前检测加速是否生效（tun 接口），未生效时自动启动加速器并点击加速按钮"): "Check whether acceleration (tun interface) is active before starting the game; auto-launch the accelerator and click the boost button if not",
    ("UpdateThread", "请前往 GitHub Releases 页面查看更新说明并手动下载。"): "Please visit the GitHub Releases page for release notes and download manually.",
    ("VersionCard", "版本信息"): "Version info",
    ("VersionCard", "当前版本: {version}"): "Current version: {version}",
    ("VersionCard", "检查更新"): "Check for updates",
    ("VersionCard", "正在检查..."): "Checking...",
    ("VersionCard", "最新版本: {version}"): "Latest version: {version}",
}


def xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    path = "i18n/myapp_en.ts"
    ts = open(path, encoding="utf-8").read()

    # 用 XML 解析确认空翻译条目（与文件内转义后的 source 对应）
    tree = ET.parse(path)
    root = tree.getroot()
    empty = []
    for ctx in root.findall("context"):
        ctx_name = ctx.findtext("name", "")
        for msg in ctx.findall("message"):
            if msg.get("type") == "vanished":
                continue
            tr_el = msg.find("translation")
            if tr_el is not None and tr_el.get("type") == "unfinished" and not (tr_el.text or "").strip():
                empty.append((ctx_name, msg.findtext("source", "")))

    print(f"空翻译条目: {len(empty)}")

    missing = [e for e in empty if e not in TRANSLATIONS]
    if missing:
        print(f"!! 翻译字典缺失 {len(missing)} 条:")
        for ctx, s in missing:
            print(f"  [{ctx}] {s}")
        return

    replaced = 0
    for ctx, src in empty:
        src_esc = xml_escape(src)
        # 在对应 context 块内定位空 translation 并替换
        pattern = re.compile(
            rf"(<context>\s*<name>{re.escape(ctx)}</name>)(.*?)(</context>)",
            re.S,
        )
        def repl(m):
            block = m.group(2)
            new_block = re.sub(
                rf"(<source>{re.escape(src_esc)}</source>\s*)<translation[^>]*type=\"unfinished\"[^>]*>\s*</translation>",
                lambda mm: mm.group(1) + f"<translation>{xml_escape(TRANSLATIONS[(ctx, src)])}</translation>",
                block,
            )
            return m.group(1) + new_block + m.group(3)

        new_ts, n = pattern.subn(repl, ts)
        if n != 1:
            print(f"!! 替换失败 [{ctx}] {src} (n={n})")
            return
        ts = new_ts
        replaced += 1

    open(path, "w", encoding="utf-8", newline="\n").write(ts)
    print(f"已补齐 {replaced} 条翻译")


if __name__ == "__main__":
    main()
