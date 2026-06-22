# 雷蛇驱动对接设计方案 (修订)

## 目标

为 AALC 新增雷蛇 (Razer) 设备硬件级输入模拟支持，与现有罗技 (Logitech) 方案并列可选（互斥）。

## 技术原理

罗技和雷蛇方案底层原理一致：通过 Windows `DeviceIoControl` + 厂商特定 IOCTL 码直接与内核驱动通信，绕过 Windows 标准输入栈（`SendInput`/`PostMessage`），用于规避反作弊检测。

| 维度 | Logitech | Razer |
|---|---|---|
| 驱动 | `logi_joy_bus.sys` (G HUB) | `RZCONTROL` (Synapse 3) |
| 设备路径 | `\??\ROOT#SYSTEM#000X#{GUID}` 遍历 | `\GLOBAL??` NT 目录枚举 → `RZCONTROL*` 符号链接 |
| 打开方式 | `NtCreateFile` | `CreateFileW(GENERIC_WRITE, FILE_SHARE_READ\|FILE_SHARE_WRITE)` |
| IOCTL 码 | 鼠标 `0x2A2010`，键盘 `0x2A200C` | 统一 `0x88883020`（struct type 字段区分） |
| 结构体大小 | 6 字节 (MOUSE_IO) / 8 字节 (KEYBOARD_IO) | 32 字节 `RzControl` |
| 鼠标按钮模型 | 独立 down/up 函数 + click 状态枚举 | 位掩码 flag (`L_BUTTON_DOWN=0x0001`, `L_BUTTON_UP=0x0002`, ...) |
| 滚轮 | 独立 `wheelup()`/`wheeldown()` | `button_flags` 设 `WHEEL`(0x0400)，delta 写入 `movement` 字段（±120） |
| 拖拽 | `move_with_button(x, y, state)` | 同时设置 button_down flag + movement=1 + x/y |
| 键盘编码 | 字符串键名 → HID Usage ID | 字符串键名 → VK 码 → HID Usage ID → Razer MakeCode |
| 键盘扩展键 | 全部视为标准键 | 箭头/Insert/Delete/Home/End/PgUp/PgDn/Win 需附加 `KEY_E0=2` 标志 |
| 参考实现 | 本地 `Logitech_driver-main` (C) | `github.com/BlankyWacky/razerctl` v0.5.1 (Rust) |

## 架构

### 新增文件

| 文件 | 用途 |
|---|---|
| `Razer_driver/main.c` | C DLL，导出与 `Logitech_driver.dll` 相同的 12 个函数，内部对接 RZCONTROL |
| `Razer_driver/*.sln/.vcxproj` | Visual Studio 2022 构建文件（参照 Logitech_driver） |
| `module/automation/input_handlers/razer.py` | `RazerInput` 类，镜像 `LogitechInput` |
| `tasks/tools/synapse_manager.py` | (可选) Synapse 版本管理器，参照 `ghub_manager.py` |

### 修改文件

| 文件 | 变更 |
|---|---|
| `module/config/config_typing.py` | 新增 `lab_mouse_razer: bool`、`razer_dll_path: str`、`razer_bionic_trajectory: bool` 三个字段 |
| `assets/config/config.example.yaml` | 新增三个字段的注释示例 |
| `module/automation/automation.py` | 1) 新增 `elif cfg.lab_mouse_razer: RazerInput()` 分支；2) 扩展仿生轨迹判断覆盖 Razer |
| `app/setting_interface.py` | 新增 `razer_switch_card`、`razer_dll_path_card`、`razer_bionic_trajectory_card`；新增互斥逻辑 |
| `assets/i18n/` | 翻译文件同步新增雷蛇 UI 文案 |

### 不修改

- `module/automation/input_handlers/__init__.py` — 保持现有导出不变，`RazerInput` 由 `automation.py` 内部 lazy import

### 集成方式

采用**并行类，最小改动**策略：
- `RazerInput` 与 `LogitechInput` 代码镜像，各自负责自己的 DLL 交互
- 通用逻辑（仿生轨迹、状态观测器、焦点检测）在两个类中各自持有，不做抽象抽取
- 两个后端**互斥**：UI 打开 Razer 时自动关闭 Logitech，反之亦然

---

## C DLL 设计 (`Razer_driver.dll`)

### 导出函数签名（12 个，与 Logitech_driver.dll 完全一致）

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

Mouse 枚举（沿用 Logitech 命名）：
```c
typedef enum {
    released = 0, lmb_down = 1, rmb_down = 2, lmb_rmb_down = 3,
    mmb_down = 4, lmb_mmb_down = 5, rmb_mmb_down = 6, lmb_rmb_mmb_down = 7
} Mouse;
```

### 内部数据结构

```c
#pragma pack(push, 1)
typedef struct {
    unsigned short flags;  // MouseButtons flags 位掩码
} MouseButtons;

typedef struct {
    unsigned int   absolute_coord;  // 0=相对移动
    MouseButtons   button_flags;
    short          movement;        // 1=发生移动，或滚轮 delta
    unsigned int   unk1;            // 保留 0
    int            x;
    int            y;
    unsigned int   unk2;            // 保留 0
} MouseInputData;

typedef struct {
    unsigned short unit_id;          // 保留 0
    unsigned short make_code;        // Razer 硬件扫描码
    unsigned short flags;            // KEY_MAKE(0)/KEY_BREAK(1)/KEY_E0(2)/KEY_E1(4)
    unsigned short reserved;         // 保留 0
    unsigned int   extra_information; // 保留 0
} KeyboardInputData;

typedef enum { Type_Keyboard = 1, Type_Mouse = 2 } RzType;

typedef struct {
    unsigned int unk1;     // 保留 0
    RzType       type;
    union {
        MouseInputData    mouse;
        KeyboardInputData keyboard;
    } data;
} RzControl;

// 编译期校验
static_assert(sizeof(MouseButtons) == 2, "MouseButtons must be 2 bytes");
static_assert(sizeof(RzControl) == 32, "RzControl must be 32 bytes");
#pragma pack(pop)
```

鼠标按钮位掩码：
```c
#define L_BUTTON_DOWN   0x0001
#define L_BUTTON_UP     0x0002
#define R_BUTTON_DOWN   0x0004
#define R_BUTTON_UP     0x0008
#define M_BUTTON_DOWN   0x0010
#define M_BUTTON_UP     0x0020
#define X_BUTTON1_DOWN  0x0040
#define X_BUTTON1_UP    0x0080
#define X_BUTTON2_DOWN  0x0100
#define X_BUTTON2_UP    0x0200
#define WHEEL           0x0400
#define H_WHEEL         0x0800
```

键盘标志：
```c
#define KEY_MAKE  0
#define KEY_BREAK 1
#define KEY_E0    2
#define KEY_E1    4
```

### device_open() 详细流程

```
1. 若已打开 (g_device_handle != INVALID_HANDLE_VALUE)，返回 TRUE
2. 调用 NtOpenDirectoryObject 打开 \GLOBAL?? 目录（DIRECTORY_QUERY 权限）
3. 循环调用 NtQueryDirectoryObject 枚举符号链接条目
4. 对每条 ObjectDirectoryInformation，检查 name 是否包含 "RZCONTROL"（大小写不敏感）
5. 匹配后构造路径 "\\\\?\\" + name，以宽字符形式
6. CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ|FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL)
7. 如 CreateFileW 失败，继续枚举下一条
8. 遍历完所有条目后仍未找到 → 返回 FALSE
9. 成功打开 → 保存 g_device_handle，返回 TRUE
```

伪代码：
```c
HANDLE open_razer_device() {
    HANDLE dir;
    NtOpenDirectoryObject(&dir, DIRECTORY_QUERY, "\GLOBAL??"...);
    // 枚举条目，查找名称含 "RZCONTROL" 的符号链接
    while (NtQueryDirectoryObject(dir, ...) == STATUS_SUCCESS) {
        if (wcsstr(name, L"RZCONTROL")) {
            WCHAR full_path[512];
            swprintf(full_path, L"\\\\?\\%s", name);
            HANDLE h = CreateFileW(full_path, GENERIC_WRITE,
                FILE_SHARE_READ|FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
            if (h != INVALID_HANDLE_VALUE) return h;
        }
    }
    return INVALID_HANDLE_VALUE;
}
```

### 各导出函数实现概要

#### device_close()
```c
if (g_device_handle != INVALID_HANDLE_VALUE) {
    CloseHandle(g_device_handle);
    g_device_handle = INVALID_HANDLE_VALUE;
}
```

#### 鼠标操作（move, lmbDown, rmbDown, mmbDown, mouseUp, wheelup, wheeldown, move_with_button）

所有鼠标操作统一通过 `send_mouse_io(button_flags, movement, x, y)` 内部函数：

```c
BOOL send_mouse_io(unsigned short button_flags, short movement, int x, int y) {
    RzControl ctrl = {0};
    ctrl.type = Type_Mouse;
    ctrl.data.mouse.button_flags.flags = button_flags;
    ctrl.data.mouse.movement = movement;
    ctrl.data.mouse.x = x;
    ctrl.data.mouse.y = y;
    return device_ioctl(&ctrl);
}

BOOL device_ioctl(RzControl* ctrl) {
    DWORD returned;
    BOOL ok = DeviceIoControl(g_device_handle, 0x88883020,
        ctrl, sizeof(RzControl), NULL, 0, &returned, NULL);
    if (!ok) {
        device_close();
        device_open();
        ok = DeviceIoControl(g_device_handle, 0x88883020,
            ctrl, sizeof(RzControl), NULL, 0, &returned, NULL);
    }
    return ok;
}
```

各函数映射：
- **move(x, y)**: `send_mouse_io(0, 1, x, y)`
- **lmbDown()**: `send_mouse_io(L_BUTTON_DOWN, 0, 0, 0)`
- **rmbDown()**: `send_mouse_io(R_BUTTON_DOWN, 0, 0, 0)`
- **mmbDown()**: `send_mouse_io(M_BUTTON_DOWN, 0, 0, 0)`
- **mouseUp()**: `send_mouse_io(0, 0, 0, 0)` — 清除所有按钮状态
- **wheelup()**: `send_mouse_io(WHEEL, 120, 0, 0)` — WHEEL 标志 + movement=+120 (WHEEL_DELTA)
- **wheeldown()**: `send_mouse_io(WHEEL, -120, 0, 0)` — WHEEL 标志 + movement=-120
- **move_with_button(x, y, state)**: 根据 state 枚举构造对应 button_flags，同时设 movement=1

move_with_button 的 Mouse 枚举 → button_flags 映射：
```c
unsigned short mouse_state_to_flags(Mouse state) {
    unsigned short flags = 0;
    if (state == lmb_down || state == lmb_rmb_down || state == lmb_mmb_down || state == lmb_rmb_mmb_down)
        flags |= L_BUTTON_DOWN;
    if (state == rmb_down || state == lmb_rmb_down || state == rmb_mmb_down || state == lmb_rmb_mmb_down)
        flags |= R_BUTTON_DOWN;
    if (state == mmb_down || state == lmb_mmb_down || state == rmb_mmb_down || state == lmb_rmb_mmb_down)
        flags |= M_BUTTON_DOWN;
    return flags;
}
```

### 键盘操作

#### 键名 → VK 码映射表

AALC 使用的规范键名来自 `module/automation/input_handlers/keys.py:CANONICAL_KEYS`（31 个键）：

| 键名 | VK 码 | HID Usage ID | MakeCode | 扩展键 |
|---|---|---|---|---|
| a-z | 0x41-0x5A | 0x04-0x1D | 查表 | 否 |
| 0-9 | 0x30-0x39 | 0x1E-0x27 | 查表 | 否 |
| enter | 0x0D | 0x28 | 查表 | 否 |
| esc | 0x1B | 0x29 | 查表 | 否 |
| space | 0x20 | 0x2C | 查表 | 否 |
| tab | 0x09 | 0x2B | 查表 | 否 |
| shift | 0x10 | 0xE1 (左) | 查表 | 否 |
| ctrl | 0x11 | 0xE0 (左) | 查表 | 否 |
| alt | 0x12 | 0xE2 (左) | 查表 | 否 |
| up | 0x26 | 0x52 | 查表 | **是** (KEY_E0) |
| down | 0x28 | 0x51 | 查表 | **是** |
| left | 0x25 | 0x50 | 查表 | **是** |
| right | 0x27 | 0x4F | 查表 | **是** |
| backspace | 0x08 | 0x2A | 查表 | 否 |
| delete | 0x2E | 0x4C | 查表 | **是** |
| pageup | 0x21 | 0x4B | 查表 | **是** |
| pagedown | 0x22 | 0x4E | 查表 | **是** |
| home | 0x24 | 0x4A | 查表 | **是** |
| end | 0x23 | 0x4D | 查表 | **是** |
| insert | 0x2D | 0x49 | 查表 | **是** |
| lwindows | 0x5B | 0xE3 (左) | 查表 | **是** |
| rwindows | 0x5C | 0xE7 (右) | 查表 | **是** |

#### press_key(key_name)

```c
void press_key(char* key_name) {
    // 1. 字符串 → VK 码
    uint8_t vk = key_name_to_vk(key_name);
    if (vk == 0) return;

    // 2. VK → HID Usage ID
    uint16_t usage_id = vk_to_usage_id(vk);
    if (usage_id == 0) return;

    // 3. HID Usage ID → Razer MakeCode
    int16_t make_code = usage_id_to_make_code(usage_id);
    if (make_code < 0) return;

    // 4. 构造键盘 IOCTL
    RzControl ctrl = {0};
    ctrl.type = Type_Keyboard;
    ctrl.data.keyboard.make_code = (uint16_t)make_code;
    ctrl.data.keyboard.flags = KEY_MAKE;
    if (is_extended_key(vk))
        ctrl.data.keyboard.flags |= KEY_E0;

    // 5. 追踪已按下键（最多 6 键同时）
    if (g_pressed_count < 6) {
        g_pressed_keys[g_pressed_count++] = make_code;
    }

    // 6. 发送 IOCTL
    device_ioctl(&ctrl);
}
```

#### release_key(key_name) / release_key_all()

- `release_key()`: 与 press_key 相同但 flags=KEY_BREAK，从 g_pressed_keys 中移除
- `release_key_all()`: 遍历 g_pressed_keys[0..g_pressed_count-1]，逐个发送 KEY_BREAK，清空计数

### 从 razerctl 移植的码表

完整 `usage_id_to_make_code()` 表（149 项主表 + 6 个特殊范围）必须原样移植到 C 中，参考 `key_translation.rs:1-58`。

---

## Python `RazerInput` 设计

### 类结构 (`module/automation/input_handlers/razer.py`)

```
SingletonMeta
  └── RazerInput (继承自 WinAbstractInput 的完整拷贝，等同于 LogitechInput)
        KEY_BACKEND = "razer"
```

### 与 LogitechInput 的镜像关系

| 属性/方法 | 差异 |
|---|---|
| `__init__` | `self.dll_path = cfg.razer_dll_path` |
| `_ensure_driver_ready()` | 加载 `Razer_driver.dll`，错误信息显示 "Razer_driver.dll" |
| `_cleanup_driver_state()` | 完全相同 |
| 所有 `_mouse_*`、`_key_*` 方法 | 完全相同（调用的 DLL 函数签名一致） |
| `_mouse_move_to()` | 完全相同（仿生轨迹逻辑） |
| `_move_relative_chunked()` | 完全相同（状态观测器） |
| `mouse_click()`, `mouse_scroll()`, `mouse_drag()` | 完全相同 |
| `input_text()`, `key_down()`, `key_up()`, `key_press()` | 完全相同 |

### 错误信息定制

- 错误 `"需要 Logitech_driver.dll"` → `"需要 Razer_driver.dll"`
- 日志 `"罗技"` → `"雷蛇"`
- 日志 `"G HUB"` → `"Synapse"`

---

## 配置设计

### ConfigModel 新增字段 (`module/config/config_typing.py`)

在 `ConfigModel` 类中，紧接现有 Logitech 相关配置位置，新增：

```python
lab_mouse_razer: bool = False
"""启用雷蛇驱动硬件级键鼠输入模拟"""

razer_dll_path: str = ""
"""雷蛇驱动 DLL 的绝对路径"""

razer_bionic_trajectory: bool = True
"""雷蛇驱动专用：是否启用仿生轨迹与仿生点击偏移"""
```

### config.example.yaml 新增 (`assets/config/config.example.yaml`)

在 `# 实验性功能` 区块，Logitech 配置之后新增：

```yaml
lab_mouse_razer: False # 实验室功能：通过独立雷蛇驱动 DLL 进行硬件级键鼠输入模拟，需填入正确 DLL 路径才能生效
razer_dll_path: "" # 雷蛇驱动 DLL 的绝对路径，启用硬件键鼠模拟必填
razer_bionic_trajectory: True # 雷蛇驱动专用：是否启用仿生轨迹与仿生点击偏移
```

---

## automation.py 变更

### 输入处理器选择 (第84-103行区间)

在现有 `if getattr(cfg, "lab_mouse_logitech", False):` 分支**之后**、`elif input_type == "background":` 分支**之前**，插入：

```python
elif getattr(cfg, "lab_mouse_razer", False):
    from .input_handlers.razer import RazerInput

    log.debug("使用雷蛇硬件鼠标模拟模块（延迟加载 DLL）")
    self.input_handler = RazerInput()
```

由于 Logitech 和 Razer 在 UI 互斥，理论上不会同时启用。但为确保防御性，Logitech 分支在先（优先级高于 Razer）。

### 仿生轨迹判断扩展

**第210-212行** `calculate_click_position` 中将：
```python
use_logitech_humanization = bool(
    getattr(cfg, "lab_mouse_logitech", False) and getattr(cfg, "logitech_bionic_trajectory", True)
)
```
改为：
```python
use_logitech_humanization = bool(
    getattr(cfg, "lab_mouse_logitech", False) and getattr(cfg, "logitech_bionic_trajectory", True)
)
use_razer_humanization = bool(
    getattr(cfg, "lab_mouse_razer", False) and getattr(cfg, "razer_bionic_trajectory", True)
)
use_hardware_humanization = use_logitech_humanization or use_razer_humanization
```
然后将第223行 `if offset and use_logitech_humanization:` 改为 `if offset and use_hardware_humanization:`。

**第286-288行** 同理，将 `use_logitech_humanization` 替换为 `use_hardware_humanization`。

---

## UI 设计 (`app/setting_interface.py`)

### 新增卡片（"实验性内容"分组内）

```python
self.razer_switch_card = SwitchSettingCard(
    FIF.MOVE,
    QT_TRANSLATE_NOOP("SwitchSettingCard", "启用雷蛇驱动模拟"),
    QT_TRANSLATE_NOOP("SwitchSettingCard",
        "使用独立 DLL 进行硬件级键鼠输入模拟，需安装 Razer Synapse 3 并配置可用的雷蛇驱动 DLL 路径"),
    config_name="lab_mouse_razer",
    parent=self.experimental_group,
)
self.razer_dll_path_card = BasePushSettingCard(
    QT_TRANSLATE_NOOP("BasePushSettingCard", "选择"),
    FIF.FOLDER,
    QT_TRANSLATE_NOOP("BasePushSettingCard", "雷蛇 DLL 路径"),
    cfg.get_value("razer_dll_path", ""),
    parent=self.experimental_group,
)
self.razer_bionic_trajectory_card = SwitchSettingCard(
    FIF.MOVE,
    QT_TRANSLATE_NOOP("SwitchSettingCard", "启用仿生轨迹"),
    QT_TRANSLATE_NOOP("SwitchSettingCard",
        "启用后使用仿生鼠标轨迹与仿生点击偏移；关闭后回退为普通分段移动"),
    config_name="razer_bionic_trajectory",
    parent=self.experimental_group,
)
```

### 互斥逻辑

`__onExperimentalDependencyChanged` 中新增：

```python
# Razer 和 Logitech 互斥
def __onExperimentalDependencyChanged(self, _: bool):
    razer_enabled = bool(cfg.get_value("lab_mouse_razer", False))
    logitech_enabled = bool(cfg.get_value("lab_mouse_logitech", False))
    if razer_enabled and logitech_enabled:
        # 最后被切换的那个保留，另一个关闭
        # 通过 sender 判断：如果是 razer switch 触发，关闭 logitech
        pass  # 具体实现见下
    self.__refreshExperimentalCardVisibility()
```

更简洁的实现：在 `__connect_signal` 中分别为两个开关连接独立的处理函数：

```python
self.logitech_switch_card.switchButton.checkedChanged.connect(self.__onLogitechSwitchChanged)
self.razer_switch_card.switchButton.checkedChanged.connect(self.__onRazerSwitchChanged)

def __onLogitechSwitchChanged(self, checked: bool):
    if checked and cfg.get_value("lab_mouse_razer", False):
        cfg.set_value("lab_mouse_razer", False)
    self.__refreshExperimentalCardVisibility()

def __onRazerSwitchChanged(self, checked: bool):
    if checked and cfg.get_value("lab_mouse_logitech", False):
        cfg.set_value("lab_mouse_logitech", False)
    self.__refreshExperimentalCardVisibility()
```

### 可见性刷新

`__refreshExperimentalCardVisibility` 中新增：
```python
razer_enabled = bool(cfg.get_value("lab_mouse_razer", False))
self.razer_dll_path_card.setVisible(razer_enabled)
self.razer_bionic_trajectory_card.setVisible(razer_enabled)
```

### DLL 路径选择

新增信号连接和回调（参照 `__onLogitechDllPathCardClicked`）：
```python
self.razer_dll_path_card.clicked.connect(self.__onRazerDllPathCardClicked)

def __onRazerDllPathCardClicked(self):
    dll_path, _ = QFileDialog.getOpenFileName(self, "选择雷蛇驱动 DLL", "", "DLL Files (*.dll)")
    if not dll_path or cfg.get_value("razer_dll_path") == dll_path:
        return
    cfg.set_value("razer_dll_path", dll_path)
    self.razer_dll_path_card.setContent(dll_path)
```

---

## 验证计划

### 无硬件验证（CI / 本地可跑）

| 测试项 | 说明 |
|---|---|
| `py_compile razer.py` | Python 语法正确性 |
| `ruff check .` | 代码风格 |
| 配置默认值测试 | `lab_mouse_razer=False`, `razer_dll_path=""`, `razer_bionic_trajectory=True` |
| 后端优先级测试 | 同时启用时 Logitech 优先 |
| UI 互斥测试 | 打开 Razer → Logitech 关闭，反之亦然 |
| `RazerInput.__init__` 懒加载 | 不传 DLL 路径时不抛异常 |
| 所有 `CANONICAL_KEYS` 映射测试 | 键名 → VK → Usage ID → MakeCode 全覆盖，无返回 0/-1 |
| DLL 缺导出错误 | 加载不存在的 DLL 时异常信息正确 |
| C 结构体编译期校验 | `static_assert(sizeof(RzControl)==32)`、`sizeof(MouseButtons)==2` |
| `RzControl.type` 枚举值 | Type_Mouse=2, Type_Keyboard=1 与 razerctl 一致 |
| `Mouse` 枚举 → button_flags 映射 | 7 种状态全覆盖 |

### 真实硬件验证（手动）

| 验证项 | 设备要求 |
|---|---|
| `device_open()` 成功 | Razer 键鼠 + Synapse 3 |
| 鼠标移动、点击、滚轮 | Razer 鼠标 |
| 键盘全键、组合键 | Razer 键盘 |
| 仿生轨迹效果 | 任意 Razer 设备 |
| `release_key_all()` 清理 | 任意 Razer 设备 |

---

## 风险

1. **IOCTL 版本兼容**: `0x88883020` 可能随 Synapse 版本变化，需长期追踪
2. **滚轮编码**: `movement` 字段作为滚轮 delta 的编码方式基于 Windows raw input 惯例推断，需硬件验证
3. **Synapse 依赖**: 必须安装 Razer Synapse 3 且 `RZCONTROL` 符号链接存在（等价于 G HUB 依赖）
4. **MakeCode 码表**: 从 razerctl v0.5.1 移植，远期 Synapse 更新可能导致码表变化
5. **无硬件验证**: 开发阶段大部分逻辑无法在真实雷蛇设备上验证
6. **move_with_button 行为**: 雷蛇驱动对"按住按钮同时移动"的实现可能与罗技有细微差异
