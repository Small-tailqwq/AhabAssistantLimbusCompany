# 雷蛇驱动对接设计方案

## 目标

为 AALC 新增雷蛇 (Razer) 设备硬件级输入模拟支持，与现有罗技 (Logitech) 方案并列可选。

## 技术原理

罗技和雷蛇方案底层原理一致：通过 Windows `DeviceIoControl` + 厂商特定 IOCTL 码直接与内核驱动通信，绕过 Windows 标准输入栈（`SendInput`/`PostMessage`），用于规避反作弊检测。

| 维度 | Logitech | Razer |
|---|---|---|
| 驱动 | `logi_joy_bus.sys` (G HUB) | `RZCONTROL` (Synapse 3) |
| 设备路径 | `\??\ROOT#SYSTEM#000X#{GUID}` 遍历 | `\GLOBAL??\RZCONTROL` 符号链接查找 |
| IOCTL 码 | 鼠标 `0x2A2010`，键盘 `0x2A200C` | 统一 `0x88883020`（type 字段区分） |
| 鼠标结构体 | 6 字节 | 32 字节 `RzControl` |
| 键盘编码 | 字符串键名 → HID Usage ID | VK → HID Usage ID → MakeCode |
| 参考实现 | 本地 `Logitech_driver-main` (C) | `github.com/BlankyWacky/razerctl` (Rust) |

## 架构

### 新增文件

| 文件 | 用途 |
|---|---|
| `Razer_driver/main.c` | C DLL，导出与 `Logitech_driver.dll` 相同的 12 个函数 |
| `module/automation/input_handlers/razer.py` | `RazerInput` 类，镜像 `LogitechInput` |
| `tasks/tools/synapse_manager.py` | (可选) Synapse 版本管理器 |

### 修改文件

| 文件 | 变更 |
|---|---|
| `module/automation/automation.py` | 新增 `elif cfg.lab_mouse_razer: RazerInput()` 分支 |
| `module/automation/input_handlers/__init__.py` | 导出 `RazerInput` |
| `app/setting_interface.py` | 新增 `razer_switch_card`、`razer_dll_path_card`、`razer_bionic_trajectory_card` |
| `assets/config/config.example.yaml` | 新增 `lab_mouse_razer`、`razer_dll_path`、`razer_bionic_trajectory` 示例 |

### 集成方式

采用**并行类，最小改动**策略：
- `RazerInput` 与 `LogitechInput` 代码镜像，各自负责自己的 DLL 交互
- 通用逻辑（仿生轨迹、状态观测器、焦点检测）在两个类中各自持有，不做抽象抽取
- 配置通过 Pydantic `extra: allow` 动态字段，无需修改 `ConfigModel`

## C DLL 设计

### 导出函数签名（与 Logitech_driver.dll 完全一致）

```c
__declspec(dllexport) BOOL   device_open(void);
__declspec(dllexport) void   device_close(void);
__declspec(dllexport) BOOL   move(char x, char y);
__declspec(dllexport) BOOL   move_with_button(char x, char y, Mouse button_state);
__declspec(dllexport) BOOL   lmbDown(void);
__declspec(dllexport) BOOL   rmbDown(void);
__declspec(dllexport) BOOL   mmbDown(void);
__declspec(dllexport) BOOL   mouseUp(void);
__declspec(dllexport) BOOL   wheelup(void);
__declspec(dllexport) BOOL   wheeldown(void);
__declspec(dllexport) void   press_key(char* key_name);
__declspec(dllexport) void   release_key(char* key_name);
__declspec(dllexport) void   release_key_all(void);
```

### 内部实现

- **device_open**: 遍历 `\GLOBAL??` 查找包含 `RZCONTROL` 的符号链接，`CreateFileW` 打开
- **鼠标操作**: 构造 32 字节 `RzControl` (type=Mouse)，通过位掩码设置 button_flags
- **键盘操作**: 字符串键名 → VK 码 → HID Usage ID → Razer MakeCode，构造 `RzControl` (type=Keyboard)
- **IOCTL**: `DeviceIoControl(handle, 0x88883020, &control, 32, NULL, 0, &returned, NULL)`
- **错误恢复**: IOCTL 失败时自动 `device_close` + `device_open` 重连

### 关键码表（从 razerctl 移植）

- `vk_to_usage_id()`: Windows VK 码 → USB HID Usage ID（标准映射表）
- `usage_id_to_make_code()`: HID Usage ID → Razer MakeCode（149 项主表 + 特殊键映射）
- `is_extended_key()`: 判断是否需要 KEY_E0 扩展标志

## Python RazerInput 设计

### 类结构

```
WinAbstractInput
  └── RazerInput (SingletonMeta)
        KEY_BACKEND = "razer"
```

### 与 LogitechInput 的差异点

| 方法 | 差异 |
|---|---|
| `_ensure_driver_ready()` | 加载 `Razer_driver.dll` 而非 `Logitech_driver.dll` |
| `_cleanup_driver_state()` | 相同清理逻辑 |
| 所有鼠标/键盘方法 | 完全相同，仅调用的 DLL 不同 |

### 通用逻辑（从 LogitechInput 复制）

- `_mouse_move_to()`: 仿生轨迹/线性模式选择
- `_move_relative_chunked()`: 分块移动 + 状态观测器
- `get_gaussian_click_point()`: 高斯分布点击偏移
- 状态观测器变量: `os_x`, `os_y`, `unack_dx`, `unack_dy`
- `stop_checker` 停止传播回调

## 配置

| 配置键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `lab_mouse_razer` | bool | false | 启用雷蛇硬件输入 |
| `razer_dll_path` | string | "" | Razer_driver.dll 路径 |
| `razer_bionic_trajectory` | bool | false | 启用仿生轨迹 |

## UI

- 设置界面 "实验性内容" 分组新增三张卡片（与 Logitech 并列）
- `razer_switch_card` 控制 `razer_dll_path_card` 和 `razer_bionic_trajectory_card` 可见性
- `automation.py` 在初始化时根据配置选择输入处理器

## 风险

1. **IOCTL 版本兼容**: `0x88883020` 可能随 Synapse 版本变化，需测试验证
2. **Synapse 依赖**: 必须安装 Razer Synapse 3 且 `RZCONTROL` 符号链接存在
3. **键码表准确性**: MakeCode 码表需在真实雷蛇设备上验证
4. **无硬件测试**: 开发阶段可能无法实际验证雷蛇设备行为

## 验证计划

1. 编译 `Razer_driver.dll` 并通过 `py_compile` 验证 Python 端语法
2. `uv run ruff check .` 确保代码风格
3. 在 `test/` 下编写手动验证脚本（依赖真实设备）
4. 确保 Logitech 现有功能不受影响（回归测试）
