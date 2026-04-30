# AALC 资产管理工具设计文档

## 1. 概述

AALC 当前 558 张图片资产分布在 `assets/images/{theme}/{lang}/{category}/` 下，缺乏可视化工具。开发者需手动翻文件夹查找/替换图片，相似图片难以区分用途，维护成本高。

**目标**：提供一个可视化的资产管理工具，支持自动扫描、标签分类、元数据编辑、文件替换（带版本历史回退）。

## 2. 数据层

### 2.1 目录结构

```
data/asset_library/
├── library/
│   ├── home.yaml                 主界面
│   ├── enkephalin.yaml           体力
│   ├── battle.yaml               战斗
│   ├── mail.yaml                 邮件
│   ├── scenes.yaml               场景/过场
│   ├── base.yaml                 通用基础（等待、confirm 等）
│   ├── mirror_road.yaml          镜牢-寻路
│   ├── mirror_shop.yaml          镜牢-商店
│   ├── mirror_event.yaml         镜牢-事件
│   ├── mirror_reward.yaml        镜牢-结算/奖励
│   ├── mirror_ui.yaml            镜牢-通用UI
│   ├── mirror_theme_pack.yaml    镜牢-主题包
│   ├── teams.yaml                队伍
│   ├── pass.yaml                 通行证
│   └── luxcavation.yaml          反射
├── recycle/
│   └── files/
│       └── <asset_key>/          按原始业务路径分组
│           ├── v1_<filename>     第一版
│           ├── v2_<filename>     第二版
│           └── _meta.yaml        版本链元数据
└── scan_cache.json               扫描缓存（checksum 对照用，可选）
```

YAML 规范：

```yaml
# data/asset_library/library/battle.yaml
assets:
  - file: default/share/battle/win_rate_assets.png
    business_name: 战斗-胜率按钮
    tags: [通用, 亮色]
    category: battle
    note: 战斗界面右上角的「胜率」按钮，点击后显示各技能胜率
    checksum: sha256:abc123...

  - file: default/zh_cn/battle/battle_finish_confirm_assets.png
    business_name: 战斗结算确认
    tags: [中, 亮色]
    category: battle
    note: 战斗结束后「战斗结算」弹窗的确认按钮（中文版）
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | str | 是 | 相对 `assets/images/` 的路径，由扫描自动填充 |
| `business_name` | str | 否 | 人类可读的业务名称，手动填写 |
| `tags` | list[str] | 否 | 标签：语言 `[中, 英, 通用]`，主题 `[亮色, 暗色]` |
| `category` | str | 是 | 业务分类，对应 YAML 文件名（由所在文件决定） |
| `note` | str | 否 | 用途备注，人工维护 + AI 辅助 |
| `checksum` | str | 是 | 文件 SHA256，扫描时自动计算，用于检测变更 |
| `status` | str | 否 | `active`（默认）/ `missing`（文件被删除）/ `archived` |

### 2.2 回收站版本链

```
data/asset_library/recycle/files/
└── mirror_shop_item_assets/
    ├── v1_item_assets.png
    ├── v2_item_assets.png
    └── _meta.yaml
```

`_meta.yaml` 内容：

```yaml
asset_key: mirror_shop_item_assets
original_path: default/share/mirror/shop/item_assets.png
versions:
  - version: 1
    file: v1_item_assets.png
    added_at: "2026-04-30T10:00:00"
    reason: 初始版本
  - version: 2
    file: v2_item_assets.png
    added_at: "2026-04-30T14:30:00"
    reason: 游戏更新，UI 重绘
current_version: 2
```

**版本切换流程**（例如当前 v3，切回 v2）：

1. 用户选择版本历史 → 选中 v2 → 点击"切换到此版本"
2. `restore()` 执行前必须 `os.path.exists()` 校验回收站目标文件是否存在，不存在则报错
3. 弹确认框："当前文件将存档为 v4，并恢复为 v2 版本。是否继续？"
4. 用户确认后：
   - 回收站 `_meta.yaml` 追加 `v4` 记录（从当前路径复制过来）
   - 回收站 `v2_item_assets.png` 复制到原路径覆盖
   - `_meta.yaml` 的 `current_version` 更新为 `v2`
5. 结果：原路径放 v2，回收站保有 v1、v2、v3、v4。无文件丢失，无重复。

**边缘情况：当前文件已被用户在外部删除**
- 此时 `status` 应为 `missing`，详情面板缩略图显示红色占位符
- `restore()` 分叉逻辑：如果原路径文件不存在，则直接从回收站复制历史版本过去（不执行"当前版本存档"步骤），在 `_meta.yaml` 中记录"从丢失状态恢复"

### 2.3 文件替换流程

1. 用户拖入/选择新图片
2. 当前图片 → 移入回收站作为新版本（自动递增版本号）
3. 新图片 → 写入原路径，保持原文件名
4. 更新 YAML 的 `checksum`
5. 更新回收站 `_meta.yaml`

### 2.4 扫描机制

**性能要求：必须在后台线程执行，不得阻塞 UI 线程。**

两级缓存校验（避免每次全量 SHA256）：

1. `scan_cache.json` 记录每个文件的 `mtime`（最后修改时间）和 `size`（文件大小）
2. 启动扫描时先比对 `mtime + size`，未变则跳过 SHA256
3. 仅当 `mtime` 或 `size` 变化时，才计算 SHA256 并更新缓存

扫描逻辑：

- **启动时**（后台 QThread）：遍历 `assets/images/` 下所有图片，与 YAML 记录对照
- **新增**：自动追加到对应分类 YAML，`file` + `checksum` 填充，其余字段留空
- **变更**：`checksum` 不匹配 → YAML 旧记录的 `status` 标记为 `archived`，追加新记录
- **删除**：YAML 中有但文件不存在 → 标记 `status: missing`（保持记录不丢，UI 显示红叉占位）
- 扫描完成后发射信号通知 UI 刷新

### 2.6 防抖写入（Debounce）

**问题**：详情面板编辑时如果每次修改都写 YAML，会触发高频磁盘 I/O。

**方案**：
- `AssetLibraryModel` 维护 `dirty_categories: set[str]`
- 每次修改只标记分类为 dirty，不立即落盘
- 启动一个 1.5 秒的单发 QTimer（每次修改重置计时器）
- 以下时机触发统一落盘：防抖定时器到期 / 用户切换选中资产 / 窗口关闭

### 2.5 分类映射规则

硬编码映射表（`model.py` 中定义），路径前缀匹配：

```
home/*                    → home
enkephalin/*              → enkephalin
battle/*                  → battle
mail/*                    → mail
scenes/*                  → scenes
base/*                    → base
mirror/road_in_mir/*      → mirror_road
mirror/road_to_mir/*      → mirror_road
mirror/shop/*             → mirror_shop
mirror/event/*            → mirror_event          # 注意：assets/images/event/ 属于日常事件，镜牢事件单独处理
mirror/claim_reward/*     → mirror_reward
mirror/get_reward_card/*  → mirror_reward
mirror/theme_pack/*       → mirror_theme_pack
mirror/*.png              → mirror_ui             # 镜牢根目录的零散 UI 图
teams/*                   → teams
pass/*                    → pass
luxcavation/*             → luxcavation
```

不匹配任何规则的资产 → 归入 `uncategorized.yaml`，等待手动归类。

## 3. UI 设计

### 3.1 窗口形式

独立悬浮窗口，通过 `tasks/tools/asset_manager.py` 注册到 `ToolManager`，在「小工具」页点击按钮启动。与现有截图工具同模式。

### 3.2 布局

```
┌──────────────────────────────────────────────────────┐
│ [🔍 搜索...]              [标签过滤 ▼]  [刷新 ↻]     │
├────────┬─────────────────────────┬───────────────────┤
│        │                         │                   │
│  分类树 │   缩略图网格            │   详情面板        │
│        │   (自适应列数)          │                   │
│  📁 全部 │   ┌────┐ ┌────┐ ┌────┐│  ┌───────────┐  │
│  📁 主界面│   │图1 │ │图2 │ │图3 ││  │ 缩略图预览  │  │
│  📁 体力 │   └────┘ └────┘ └────┘│  └───────────┘  │
│  📁 战斗 │   ┌────┐ ┌────┐ ┌────┐│                  │
│  📁 镜牢 │   │图4 │ │图5 │ │图6 ││  业务名: [____] │
│    📁 寻路│   └────┘ └────┘ └────┘│                  │
│    📁 商店│                        │  文件名: xxx     │
│    📁 事件│                        │                  │
│    📁 UI │                        │  标签: [通用][亮]│
│  📁 队伍 │                        │                  │
│  ...     │                        │  备注:           │
│          │                        │  [编辑框]        │
│          │                        │                  │
│          │                        │  [替换图片] [历史]│
├────────┴─────────────────────────┴───────────────────┤
│  状态栏: 共 558 个资产  |  已选 1 个                   │
└──────────────────────────────────────────────────────┘
```

### 3.3 窗口规格

| 属性 | 值 |
|---|---|
| 初始尺寸 | 1200 × 750 |
| 最小尺寸 | 900 × 550 |
| 左侧分类树 | 180px |
| 右侧详情面板 | 320px |

### 3.4 详情面板字段交互

| 字段 | 控件 | 交互 |
|---|---|---|---|
| 缩略图 | QLabel + QPixmap | 使用 `QImageReader.setScaledSize(150,150)` 加载缩略图，绝不加载原图；点击可放大预览 |
| 业务名 | QLineEdit | 可编辑，防抖落盘 |
| 文件名 | QLabel (只读) | - |
| 标签 | FlowLayout + TagChip | 可增删，点击标签可反过滤 |
| 备注 | QTextEdit | 可编辑，防抖落盘 |
| 替换图片 | QPushButton + Drag & Drop | 点击弹出文件选择；详情面板缩略图区域支持 `dragEnterEvent`/`dropEvent` 直接拖入替换 |
| 历史版本 | QPushButton | 弹出版本列表对话框，支持切换 |

**缩略图网格内存管理**：
- 使用 `QListWidget` 的 IconMode 配合 `setIconSize(QSize(120, 120))`
- 网格项只持有 `QIcon`（内部已做共享引用计数），不单独持有 `QPixmap`
- 不实现完整虚拟滚动（558 张图在 IconMode 下表现可接受），但懒加载分批插入：首次只加载前 100 张，滚动到底部时追加后续批次

### 3.5 搜索与过滤

- **搜索栏**：实时过滤，匹配 `business_name` + `note` + `file`
- **标签过滤**：下拉多选，支持组合过滤（如 `[通用] + [暗色]`）
- **分类树**：点击节点过滤到该分类，折叠子分类
- **右键菜单**（网格项）：
  - 「在文件管理器中打开」— `os.startfile(os.path.dirname(abspath))`
  - 「复制路径」— 将相对路径复制到剪贴板
  - 「标记为已删除」— 软删除（仅改 YAML `status`，不动文件）
  - 「从回收站恢复」— 仅在 `status: missing` 时可用

## 4. 代码模块划分

```
tasks/tools/
├── __init__.py                  ← ToolManager 注册 asset_manager
├── asset_manager.py             ← AssetManager (QWidget 窗口)
└── asset_library/
    ├── __init__.py
    ├── model.py                 ← AssetLibraryModel: YAML 读写、扫描、过滤
    ├── widgets.py               ← 分类树、缩略图网格、详情面板等 UI 组件
    └── recycle.py               ← RecycleManager: 回收站版本链管理
```

### 4.1 类职责

**`AssetLibraryModel`**（非线程安全，需在后台线程构造或使用信号桥接）
- `scan()` — 返回 diff 结果（新增/变更/删除列表），不直接写 YAML；异步调用方负责将结果应用到 UI
- `apply_scan_result(diff)` — 将扫描 diff 写入 YAML + 更新 `scan_cache.json`
- `load_cache()` / `save_cache()` — `scan_cache.json` 的 mtime/size 缓存读写
- `get_assets(category=None, tags=None, search=None)` — 过滤查询
- `get_asset(file_path)` — 单条查询
- `update_asset(file_path, **fields)` — 标记字段变更，分类加入 `dirty_categories`
- `flush_dirty()` — 将所有 `dirty_categories` 写盘，清空集合
- `replace_asset(file_path, new_image_path)` — 替换图片（触发回收站流程）
- `_load_yaml(category)` / `_save_yaml(category)` — YAML I/O

**`RecycleManager`**
- `archive(file_path, reason)` — 当前文件移入回收站，追加版本
- `restore(asset_key, version)` — 恢复指定版本到原路径（必须先 `os.path.exists()` 校验）
- `list_versions(asset_key)` — 列出资产的所有历史版本
- `permanently_delete(asset_key, version)` — 彻底删除某版本
- `_get_recycle_path(asset_key)` — 回收站分组路径

**`AssetManager` (QWidget)**
- 主窗口：组装 `AssetTree` + `AssetGrid` + `AssetDetailPanel`
- 信号路由：树节点选中 → 过滤网格 → 网格项选中 → 填充详情
- 扫描进度反馈

### 4.2 信号流

```
启动 → QThread: model.scan() → scan_finished(diff) → UI 刷新生效
分类树选中 → model.get_assets(category=...) → 网格刷新
网格项选中 → model.get_asset(file_path) → 详情填充
详情编辑 → model.update_asset(...) → 标记 dirty_categories → 防抖 QTimer 重置
防抖到期 / 切换资产 / 关闭窗口 → model.flush_dirty() → YAML 落盘
替换点击 → model.replace_asset(...) → 回收站归档 + 网格刷新
拖入文件 → detail_panel.dropEvent → model.replace_asset(...) → 同上
历史点击 → recycle.list_versions(...) → 版本对话框
版本切换 → recycle.restore(...) → 网格刷新
```

## 5. 整合到现有项目

### 5.1 注册工具

在 `tasks/tools/__init__.py` 的 `ToolManager.run_tools()` 中添加：

```python
elif self.tool == "asset_manager":
    self.w = AssetManager()
```

在 `app/tools_interface.py` 的 `__init_card()` 中添加启动卡片：

```python
self.asset_manager_card = BasePushSettingCard(
    QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
    FIF.ALBUM,
    QT_TRANSLATE_NOOP("BasePushSettingCard", "资产管理"),
    QT_TRANSLATE_NOOP("BasePushSettingCard", "可视化浏览、分类、替换游戏图片资产"),
    parent=self.tools_group,
)
```

### 5.2 gitignore

**版本控制策略**（源自代码审阅建议）：

```
# 纳入版本控制 — 这是共享的元数据知识库
data/asset_library/library/*.yaml

# 加入 .gitignore — 大二进制历史文件 + 本地扫描缓存
data/asset_library/recycle/
data/asset_library/scan_cache.json
```

### 5.3 构建排除

`scripts/build.py` 的构建复制规则中排除 `data/asset_library/`：

```python
exclude_patterns = [
    "data/asset_library/**",
    ...
]
```

## 6. 实现顺序

1. `model.py` — YAML 读写、全量扫描、diff
2. `recycle.py` — 回收站版本链归档/恢复
3. `widgets.py` — 分类树、缩略图网格、详情面板
4. `asset_manager.py` — 组合窗口、信号路由
5. 整合到 `tools_interface` + 构建排除

## 7. 验证要点

- 扫描 558 张图片不卡 UI（后台线程 + 两级缓存），首次扫描 SHA256 有进度反馈
- 二次启动扫描速度明显提升（mtime/size 缓存命中跳过 SHA256）
- 分类树折叠展开、过滤后网格刷新
- 缩略图加载无 OOM（全量加载后内存 < 200MB）
- 替换图片 → 回收站出现版本记录
- 版本切换 → 原路径文件正确替换，回收站追加新版本
- 用户从外部删除原图 → UI 显示 [Missing] 红叉占位，从回收站恢复正常
- 标签组合过滤（如 `[通用]+[暗色]`）结果准确
- 拖拽图片到详情面板触发替换
- 右键菜单：在文件管理器中打开 / 复制路径
- 窗口关闭后重新打开，YAML 数据一致
- `data/asset_library/library/*.yaml` 纳入 git 追踪，`recycle/` 被 gitignore
