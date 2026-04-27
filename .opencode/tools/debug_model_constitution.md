# AALC 调试模型宪法

## 1. 总则

调试模式（debug_*）是一组用于诊断和排障的开关，所有子调试开关必须受 `debug_mode` 总开关节制。关闭总开关时，所有子开关必须自动复位。

## 2. 开关注册

### 2.1 字段定义

在 `module/config/config_typing.py` 的 `ConfigModel` 中定义：

```python
debug_xxx: bool = False
"""xxx 调试：功能描述"""
```

### 2.2 配置示例

在 `assets/config/config.example.yaml` 添加同名字段和注释。

### 2.3 UI 开关（setting_interface.py）

每个子调试开关必须有一个 `SwitchSettingCard`，注册在 `logs_group` 中：

```python
# 定义
self.debug_xxx_card = SwitchSettingCard(
    FIF.DEVELOPER_TOOLS,
    "调试标题",
    "调试描述文本",
)

# 注册
self.logs_group.addSettingCard(self.debug_xxx_card)

# 可见性
def __refreshDebugCardVisibility(self):
    debug_enabled = bool(cfg.get_value("debug_mode", False))
    ...
    self.debug_xxx_card.setVisible(debug_enabled)

# 父开关关闭时复位
def __onDebugModeChanged(self, is_checked: bool):
    if not is_checked:
        for key in ["debug_xxx", ...]:
            if cfg.get_value(key, False):
                cfg.set_value(key, False)
            self.debug_xxx_card.setValue(False)
```

## 3. 开关门控

所有子调试开关必须**双重门控**：同时检查 `debug_mode` 和自身开关。

### 3.1 辅助函数模式

在每个功能模块顶部定义私有辅助函数：

```python
def _is_xxx_debug_enabled():
    return bool(cfg.get_value("debug_mode", False) and cfg.get_value("debug_xxx", False))
```

### 3.2 调用方式

在业务代码中使用辅助函数，不直接用 `cfg.debug_xxx`：

```python
if _is_xxx_debug_enabled():
    ...
```

## 4. 日志约定

### 4.1 日志级别

- 功能断点（截图保存、决策分支）：`log.info`
- 详细信息（坐标、列表、识别值）：`log.debug`

### 4.2 日志前缀

用中式描述 + 上下文，不用统一标签：

```
✅ "镜牢路线图调试截图已保存: %s"
✅ "纽本调试截图已保存: %s"
✅ "[重试调试] 匹配→退回窗口，continue"
```

`[xxx]` 括号标签格式仅用于跨多个文件、多个函数的同主题调试。

## 5. 截图保存约定

需保存调试截图时：

### 5.1 目录

统一放在 `logs/<feature>_debug/` 下。

### 5.2 文件名

```
YYYYMMDD_HHMMSS_ms_<label>.png
```

### 5.3 清理

持续保存截图的功能必须实现文件数上限清理，参考：

```python
ROUTE_MAP_DEBUG_KEEP_COUNT = 50

def _cleanup_route_map_debug_frames():
    files = sorted(Path("logs/route_map_debug/").glob("*.png"))
    while len(files) > ROUTE_MAP_DEBUG_KEEP_COUNT * 2:
        files[0].unlink()
        files.pop(0)
```

## 6. 复位契约

`debug_mode` 关闭时必须在 `__onDebugModeChanged` 中显式复位所有子开关：

```python
def __onDebugModeChanged(self, is_checked: bool):
    if not is_checked:
        for key in ["debug_xxx", "debug_yyy", ...]:
            if cfg.get_value(key, False):
                cfg.set_value(key, False)
            self.debug_xxx_card.setValue(False)
            self.debug_yyy_card.setValue(False)
    self.__refreshDebugCardVisibility()
```

遗漏任何子开关都属于违规。
