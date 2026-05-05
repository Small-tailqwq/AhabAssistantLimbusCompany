# AALC 更新引导器协议化设计

## 1. 概述

### 1.1 背景

`v1.5.0-canary.9` 引入了基于新包文件清单的旧残留清理逻辑。该逻辑在 `updater.py` 中通过扫描当前安装目录，删除所有“不在新包 manifest 中”的文件实现。

线上与本地模拟结果证明，这个策略存在两个根本问题：

- 当压缩包布局与 updater 预期不一致时，会把 `_internal/*` 误判为旧残留并删除，导致程序无法启动。
- 即使压缩包布局正确，也会删除 `logs/*`、锁文件等用户运行期生成内容，因为这些内容天然不会出现在发行包里。

`v1.5.0-canary.10` 已修复压缩包根目录与旧 archive 兼容问题，但在线更新时优先执行的是用户本地安装目录中的旧 `AALC Updater.exe`。因此新版本中的 updater 修复，无法反向拯救已发布的坏 updater 行为。

这说明当前问题不是单个路径判断 bug，而是更新系统缺少稳定引导协议，导致新版本无法安全约束旧 updater 的删除行为。

### 1.2 目标

- 彻底消除 `_internal/*` 被误删导致的启动失败。
- 明确区分“程序托管文件”和“用户运行时文件”，不再删除 `logs/` 等用户数据。
- 让 updater 的删除行为由显式元数据驱动，而不是靠目录扫描和隐式推断。
- 为未来打包结构调整提供向前兼容机制，避免再次出现“新版本修不了旧 updater”的问题。

### 1.3 非目标

- 不追求继续兼容所有历史 updater 的自由推断行为。
- 不在本设计中引入双阶段网络下载。
- 不试图在首次迁移到新协议时清理历史遗留文件；首次迁移优先保证安全。

## 2. 根因

### 2.1 删除策略错误地把“发行包内容”当成“安装目录所有权清单”

当前 `_remove_stale_files()` 的逻辑是：

1. 解压新包。
2. 根据新包生成 manifest。
3. 扫描安装目录。
4. 删除所有不在 manifest 且不在 preserve 白名单中的文件。

这隐含了一个错误假设：安装目录中所有合法文件都必须来自发行包。

事实上，安装目录中还会存在：

- `logs/` 下的运行日志
- 锁文件
- 未来可能新增的缓存、调试输出、用户扩展文件

这些内容是合法的，但不属于发行包。用“是否出现在新包里”来决定删除，模型本身就是错的。

### 2.2 旧 updater 没有稳定协议，只能靠本地代码猜包结构

`canary.9` 的 updater 在生成 manifest 时依赖本地解压目录结构。构建脚本当时又把 7z 压缩为带 `AALC/` 顶层前缀的路径，导致 updater 构造出的相对路径与安装目录相对路径不一致，进而误删 `_internal/*`。

这说明旧 updater 对包布局没有显式协商机制，只能根据代码分支猜测“解压后哪个目录才是真正的应用根”。

### 2.3 新版本 updater 修复无法约束已安装旧 updater

在线更新入口当前直接执行：

- `AALC Updater.exe <archive>`

因此实际运行的是用户本地旧版本安装目录中的 updater，而不是更新包内的新 updater。只要旧 updater 的删除逻辑有缺陷，后续版本就无法在本次更新前介入修正。

## 3. 设计原则

### 3.1 稳定引导器原则

安装目录中的 `AALC Updater.exe` 必须被视为稳定 bootstrap，而不是随意推断包结构和删除策略的业务实现。

稳定 bootstrap 的职责固定为：

- 终止主程序进程
- 解压更新包到隔离目录
- 读取更新元数据
- 校验包布局
- 执行覆盖安装
- 在明确安全条件满足时执行受控清理
- 持久化本次安装清单

### 3.2 所有权显式声明原则

updater 只能删除“被协议明确声明属于应用托管”的文件。

updater 也只能覆盖“被协议明确声明属于应用托管”的文件。

不允许再通过以下方式推断删除：

- 安装目录全扫描
- 新包不存在即视为应删
- 某些目录默认看起来像垃圾就删除

同样也不允许通过“解压目录里正好有同名文件”就覆盖用户路径。

### 3.3 Fail-safe 原则

当 updater 无法确认安全时，必须自动降级为“只覆盖，不删除”。

允许的失败模式：

- 遗留旧文件未被清理
- 更新中止并给出明确错误

不允许的失败模式：

- 删除 `_internal/*`
- 删除 `logs/*`
- 删除未知用户数据

### 3.4 首次迁移零删除原则

首次从旧协议迁移到新协议时，本地尚不存在可信的已安装清单，因此不能做任何基于差集的删除。首次迁移必须仅覆盖安装，并在安装完成后写入第一份本地托管清单。

## 4. 协议设计

### 4.1 更新包元数据 `update_manifest.json`

每个应用更新包根目录必须携带 `update_manifest.json`，由构建脚本生成。

建议结构：

```json
{
  "format_version": 1,
  "bootstrap_version": 2,
  "current_version": "1.5.0-canary.11",
  "package_layout": "flat",
  "payload_root": ".",
  "cleanup_mode": "managed_only",
  "min_source_version_for_cleanup": "1.5.0-canary.11",
  "managed_files_manifest": "managed_files.txt",
  "managed_files_sha256": "<sha256>",
  "protected_paths": [
    "config.yaml",
    "theme_pack_list.yaml",
    "logs/",
    "update_temp/",
    "3rdparty/",
    "theme_pack_weight/",
    "__pycache__/"
  ]
}
```

字段定义：

- `format_version`：协议版本，控制解析方式。
- `bootstrap_version`：要求的最小引导器能力版本。
- `current_version`：本包版本号，用于日志与迁移判断。
- `package_layout`：包布局类型，见 4.2。
- `payload_root`：真正应用根目录相对于解压根的路径。
- `cleanup_mode`：本次更新允许的清理策略。
- `min_source_version_for_cleanup`：源安装版本达到该值后，才允许按托管清单做删除。
- `managed_files_manifest`：托管文件清单文件名。
- `managed_files_sha256`：托管清单完整性校验。
- `protected_paths`：永远禁止删除和覆盖的路径前缀。

`bootstrap_version` 的语义不是“本次运行时自动切换到包内新 updater”，而是：

- 该包要求本地已安装的稳定引导器至少具备某个能力版本
- 如果本地稳定引导器版本不足，则不能直接发布只支持新协议的新包
- 必须先通过桥接版本把本地 `AALC Updater.exe` 升级到满足要求的版本

### 4.2 包布局 `package_layout`

允许两种显式布局：

- `flat`：解压根目录直接是应用根
- `root_dir`：解压根目录下存在单个 `AALC/` 子目录作为应用根

updater 必须按元数据声明定位 `payload_root`，不能再通过“如果有 `AALC/` 就切进去”这种推断逻辑决定行为。

如果声明与实际解压结构不符：

- 记录错误日志
- 放弃清理
- 直接中止更新，不再继续覆盖安装

这里选择中止而不是尽量继续，是因为包布局异常意味着根目录识别已经不可信，继续覆盖会放大事故面。

### 4.3 托管文件清单 `managed_files.txt`

更新包根目录必须包含 `managed_files.txt`，一行一个相对路径，全部使用 `/` 分隔。

它表示：

- 这一版本交付并托管的全部程序文件集合

它同时也是允许覆盖安装的唯一文件集合。

它不应包含：

- `logs/`
- 用户配置外生成数据
- `update_temp/`
- 运行时锁文件
- 任何 `protected_paths` 覆盖到的路径

示例：

```text
AALC.exe
_internal/python313.dll
_internal/PySide6/Qt6Core.dll
assets/config/version.txt
app/my_app.py
module/update/check_update.py
```

### 4.4 本地已安装清单 `installed_manifest.txt`

updater 每次成功安装后，都要把本次已验证的 `managed_files.txt` 持久化为本地 `installed_manifest.txt`。

建议存放位置：

- `assets/config/installed_manifest.txt`

同时写入对应的本地元数据文件，例如：

- `assets/config/installed_manifest_meta.json`

用于记录：

- `format_version`
- `bootstrap_version`
- `installed_version`
- `managed_files_sha256`
- `package_layout`

本地已安装清单的语义是：

- 上一次成功安装后，哪些文件被系统认定为“程序托管文件”

这是后续删除的唯一可信旧基线。

### 4.5 本地引导器版本标记

为了让应用层和 updater 层都能明确知道当前安装目录中的引导器能力版本，安装完成后还需要持久化一份本地引导器版本标记。

建议位置：

- `assets/config/bootstrap_version.txt`

语义：

- 当前安装目录中 `AALC Updater.exe` 所实现的稳定协议版本

用途：

- 应用层在发起更新前判断本地是否具备处理目标包的能力
- updater 层记录当前安装是否已完成桥接迁移

### 4.6 路径安全校验

所有由 `update_manifest.json`、`managed_files.txt` 驱动的路径，在参与复制、删除、写入前都必须通过同一套路径安全校验。

必须拒绝以下路径：

- 绝对路径，如 `/foo/bar`、`C:/foo/bar`、`C:\\foo\\bar`
- 包含 `..` 路径段的相对路径
- 归一化后为空、`.` 或指向目录根的路径
- 指向 `protected_paths` 的路径
- 解析后落在安装根目录之外的路径

校验规则：

1. 先把协议路径统一归一化为 `/` 分隔
2. 使用纯路径语义做分段校验，拒绝 `..`、绝对盘符、UNC 路径
3. 计算目标绝对路径后，必须验证其 `resolve()` 结果仍位于安装根目录内
4. 复制来源路径的 `resolve()` 结果也必须位于 `payload_root` 内

任何一条校验失败，都必须中止更新，不能忽略或跳过。

## 5. 更新流程

### 5.1 新流程概览

```text
下载更新包
  -> 旧/当前 AALC Updater.exe 启动
  -> 解压到隔离目录
  -> 读取 update_manifest.json
  -> 校验协议版本与包布局
  -> 读取并校验 managed_files.txt
  -> 校验 managed path 与 target path 安全
  -> 按 managed_files.txt 覆盖安装文件
  -> 决定是否允许清理
  -> 若允许，仅按 installed_manifest vs managed_files 差集删除
  -> 写入新的 installed_manifest
  -> 清理 update_temp
  -> 启动 AALC.exe
```

### 5.2 删除判定逻辑

删除依据从当前的：

- `扫描安装目录 - 新包 manifest`

改为：

- `旧 installed_manifest - 新 managed_files.txt`

只有同时满足以下条件，才允许删除某个路径：

1. 本地存在可信的 `installed_manifest.txt`
2. `update_manifest.json` 存在且校验通过
3. `managed_files.txt` 存在且哈希匹配
4. 当前源版本满足 `min_source_version_for_cleanup`
5. 路径出现在旧 `installed_manifest.txt` 中
6. 路径不再出现在新 `managed_files.txt` 中
7. 路径不匹配任何 `protected_paths`

任何一个条件不满足，都必须跳过删除。

### 5.3 首次迁移逻辑

当本地不存在 `installed_manifest.txt` 时，视为首次迁移到新协议。

行为必须是：

- 覆盖安装
- 不做任何删除
- 安装成功后写入第一份 `installed_manifest.txt`

这样可以避免旧版本目录中的用户数据、旧日志、历史遗留目录被误删。

### 5.4 已知危险源版本兜底

对于 `<= 1.5.0-canary.9` 的源安装版本，即使当前 updater 已支持新协议，也必须强制禁用清理。

原因：

- 这部分用户本地目录很可能已经受旧清理逻辑污染
- 本地也一定不存在可信的 `installed_manifest.txt`
- 继续试图清理会扩大事故面

因此对危险源版本的策略固定为：

- 仅覆盖
- 写入新协议元数据
- 从下一次升级开始才允许进入精准清理

### 5.5 `protected_paths` 规则

以下路径必须始终视为用户或运行期所有，不参与删除差集，也不允许被更新包覆盖：

- `logs/`
- `update_temp/`
- `3rdparty/`
- `theme_pack_weight/`
- `__pycache__/`
- `config.yaml`
- `theme_pack_list.yaml`

规则补充：

- `managed_files.txt` 不得声明任何位于 `protected_paths` 下的路径
- `copy_payload()` 不得复制任何位于 `protected_paths` 下的文件
- `remove_retired_managed_files()` 不得删除任何位于 `protected_paths` 下的文件
- 如果更新包声明或实际落盘了 `protected_paths` 下的托管文件，updater 必须直接中止更新

后续如果新增运行期目录，也必须通过 `protected_paths` 显式声明。

### 5.6 引导器接管与桥接迁移

对于已经发布出去的旧版本，尤其是 `canary.9`，必须明确区分两类更新：

1. 桥接更新
2. 协议更新

桥接更新的目的不是立刻启用新协议删除，而是先把本地安装目录中的 `AALC Updater.exe` 升级为稳定引导器。

这里必须强调：

- 只要本次更新仍由旧 updater 启动并执行，当前这一次运行的删除与覆盖行为就仍然由旧逻辑主导
- 新协议文件在这次运行里不具备接管能力，只能为“桥接完成后的下一次更新”建立基础
- 因此桥接包必须完全兼容旧 updater 的现有逻辑，而不能依赖新协议在本次运行中提供保护

桥接更新规则：

- 更新包必须继续使用旧 updater 可正确处理的 `root_dir` 布局
- 更新包必须是完整应用包，不能是只包含 updater 的增量包或补丁包
- 更新包内同时携带新的 `AALC Updater.exe`
- 更新包内同时携带 `update_manifest.json`、`managed_files.txt` 与 `bootstrap_version.txt`
- 旧 updater 即使不理解这些协议文件，也能先把它们拷贝到安装目录
- 本次桥接完成后，本地 `AALC Updater.exe` 与 `bootstrap_version.txt` 才真正升级到新协议版本

桥接包必须满足的兼容约束：

- 必须包含旧 updater 可能据此判断为“需要保留”的全部运行关键文件
- 不允许使用任何需要旧 updater 理解 `protected_paths`、`installed_manifest.txt`、`managed_files.txt` 语义才安全的发布策略
- 必须假设旧 updater 在本次桥接运行中仍可能删除所有其白名单之外的旧文件
- 如果某类用户数据不能承受这次桥接中的旧逻辑影响，则该用户必须走手动升级或救援路径

协议更新规则：

- 只有当本地 `bootstrap_version.txt >= 目标包要求` 时，才允许发布和安装仅支持新协议的更新包
- 协议更新可以使用默认 `flat` 布局和精准清理逻辑

这意味着 `canary.9 -> 桥接版本` 与 `桥接版本 -> 后续协议版本` 是两个不同阶段，不能在文档中假设旧 updater 能在同一次运行里读懂并执行新协议。

### 5.7 已损坏安装的救援路径

如果用户已经因为旧 updater 误删 `_internal/*` 导致 AALC 无法启动，则应用内在线更新入口已经不可用。

对此必须单独提供救援路径：

- 发布独立恢复包或完整安装包
- 允许用户在无法启动 AALC 时手动恢复 `AALC.exe` 与 `_internal/*`

救援路径不属于在线更新协议本身，但必须作为事故发布策略的一部分明确存在。

### 5.8 桥接版本发布约束

桥接版本的发布必须遵守以下约束：

- 发布物中的应用更新资产必须是单一、完整、旧 updater 可处理的 `.7z` 包
- 不允许在同一 release 中同时摆放多个让旧客户端可能选错的应用更新 `.7z` 资产
- 发布说明必须明确告知：本次桥接运行仍受旧 updater 逻辑约束，历史日志等运行期文件可能无法保留
- 若用户需要保留历史运行日志，必须先手动备份或直接使用手动升级/救援路径

## 6. 构建侧改动

### 6.1 `scripts/build.py`

构建流程新增以下输出：

1. 生成 `managed_files.txt`
2. 计算其 SHA256
3. 生成 `update_manifest.json`
4. 将这两个文件打入更新包根目录

要求：

- `managed_files.txt` 必须以最终分发目录 `dist/AALC` 为基准生成
- 生成时排除 `logs/`、`update_temp/` 等运行期路径
- 生成时排除全部 `protected_paths`
- `package_layout` 必须与实际 7z 打包结构一致

### 6.2 包布局约束

后续更新包统一使用一种布局，推荐：

- `flat`

即压缩包根目录直接包含 `AALC.exe`、`_internal/`、`assets/` 等文件。

设计上仍保留 `root_dir` 解析能力，仅用于兼容历史包或救援包，但新构建默认不再输出多余顶层目录。

### 6.3 桥接版本构建模式

为了完成从旧 updater 到稳定引导器的迁移，构建脚本需要提供显式桥接模式，例如：

- `--bridge-updater`

桥接模式要求：

- 7z 包输出 `root_dir` 布局
- 桥接包输出完整应用内容，而不是增量修补内容
- 包内包含新的 `AALC Updater.exe`
- 包内包含 `update_manifest.json`
- 包内包含 `managed_files.txt`
- 包内包含 `bootstrap_version.txt`
- 桥接包内容必须经过旧 updater 本地模拟验证

桥接模式的目标只有一个：

- 让旧 updater 能安全完成一次“替换本地 updater”的更新

这里的“安全”仅指：

- 不再误删 `_internal/*` 并导致程序无法启动
- 桥接完成后本地 updater 成功升级

它不代表旧 updater 在这次运行里已经具备新协议的数据保护能力。

桥接模式不是长期默认模式。完成桥接发布后，后续正常构建回到默认协议模式。

## 7. Updater 侧改动

### 7.1 角色重构

`updater.py` 的职责从“解压 + 覆盖 + 扫描删除”改为：

- `extract_payload()`：解压到隔离目录
- `load_update_manifest()`：读取并校验协议元数据
- `resolve_payload_root()`：根据 `package_layout` 与 `payload_root` 定位应用根
- `load_managed_files()`：读取并校验托管清单
- `validate_managed_path()`：校验单个托管路径合法、非 protected、无路径穿越
- `copy_payload()`：仅按托管清单覆盖安装
- `load_installed_manifest()`：读取本地已安装清单
- `remove_retired_managed_files()`：按差集精准删除
- `write_installed_manifest()`：持久化当前托管清单

旧的 `_remove_stale_files()` 必须删除，不能继续保留作兜底路径。

### 7.2 升级兼容行为

为了处理旧 updater 启动新包的场景，新 updater 必须尽量做到：

- 即使本地旧目录没有安装清单，也能安全完成首次迁移
- 即使包布局异常，也不会误删用户文件
- 即使未来字段扩展，旧 `format_version` 仍可被明确拒绝，而不是默默走默认逻辑
- 即使压缩包中存在恶意或错误路径，也不会把文件写到安装目录之外或写进受保护路径

### 7.3 本地版本识别

updater 在决定是否允许清理时，需要读取当前安装目录版本号。

建议来源：

- `assets/config/version.txt`

当版本号缺失或无法解析时，必须视为不可信来源版本，禁用清理。

### 7.4 应用层的引导器能力检查

桥接完成后，应用层发起在线更新前，还需要读取：

- `assets/config/bootstrap_version.txt`

并与目标包 `update_manifest.json` 中的 `bootstrap_version` 做比较。

行为规则：

- 若本地版本满足要求，允许正常下载并启动 updater
- 若本地版本不满足要求，但存在可用桥接版本，则优先引导用户安装桥接版本
- 若本地版本不满足要求且无桥接版本可用，则拒绝安装并提示手动恢复/手动下载

这样可以避免未来再次出现“新包能力高于本地 updater，但仍被错误下发”的情况。

## 8. 错误处理与日志

### 8.1 必须中止更新的错误

- `update_manifest.json` 缺失
- `format_version` 不支持
- `package_layout` 与实际解压结构不匹配
- `managed_files.txt` 缺失
- `managed_files_sha256` 校验失败
- `managed_files.txt` 中存在绝对路径、`..`、UNC、盘符路径或其他非法路径
- 任一路径解析后落在安装根目录之外或 `payload_root` 之外
- 任一路径命中 `protected_paths`
- 覆盖安装失败

### 8.2 可以降级继续的情况

- 本地不存在 `installed_manifest.txt`
- 源安装版本无法解析
- 源安装版本低于 `min_source_version_for_cleanup`
- 本地旧元数据文件缺失

这些情况统一降级为：

- 只覆盖，不删除
- 写日志说明为何跳过清理

### 8.3 关键日志要求

updater 日志必须明确打印：

- 当前安装版本
- 更新包版本
- 识别到的 `package_layout`
- 是否进入首次迁移模式
- 是否允许清理
- 跳过清理的具体原因
- 实际删除的托管文件数量

日志中禁止再出现“扫描安装目录并删除未知文件”的模糊表述。

## 9. 验证策略

### 9.1 本地回归场景

至少覆盖以下场景：

1. `canary.9 -> 新协议版本`
   - `_internal/*` 不被删除
   - `logs/*` 不被删除
   - 安装完成后能正常启动

2. 首次从旧协议版本升级
   - 本地无 `installed_manifest.txt`
   - 不发生任何删除
   - 安装后写入新的本地清单

3. 新协议版本之间升级
   - 旧托管文件被精准删除
   - 用户数据目录保持不变

4. 包布局异常
   - 更新中止
   - 安装目录不被破坏

5. `managed_files.txt` 哈希异常
   - 更新中止
   - 不发生清理

6. 路径穿越或非法路径
   - 更新中止
   - 安装根目录外没有新文件产生
   - `protected_paths` 下没有文件被覆盖

7. `canary.9 -> 桥接版本`
   - 旧 updater 能完成安装
   - 新的 `AALC Updater.exe` 被成功写入安装目录
   - `bootstrap_version.txt` 被正确写入
   - 不再发生 `_internal/*` 误删

8. `桥接版本 -> 协议版本`
   - 由新稳定引导器执行更新
   - 精准清理生效
   - `logs/*` 不被删除

### 9.2 建议测试资产

更新流程测试目录中应显式构造：

- `logs/debugLog.log`
- `logs/.__debugLog.lock`
- 模拟旧版 `_internal/` 文件
- 一个已废弃但曾经托管的假文件
- 包含 `../evil.txt`、`C:/evil.txt`、`logs/config.yaml` 等非法或受保护路径的恶意测试清单

借此验证：

- 用户文件不会被删
- 仅旧托管假文件会在新协议版本间被删除
- 路径穿越会被立即拦截

## 10. 风险与取舍

### 10.1 首次迁移不清理会保留历史遗留文件

这是有意取舍。相比误删运行时关键文件，保留一些历史垃圾文件是可以接受的。

### 10.2 需要维护本地已安装清单

这会引入一份新的持久化元数据，但它是实现“安全删除”的必要前提。没有可信旧基线，就不能做可靠差集。

### 10.3 旧 updater 仍无法被新包前置修正

本设计解决的是“以后不再依赖扫描删除”，不能改变已发布旧 updater 已经执行的事实。对已经损坏的 `canary.9` 用户，仍需要通过修复包、重新安装包或手动恢复方式处理。

### 10.4 `canary.9 -> 桥接版本` 期间的历史日志保留限制

只要某次更新仍然由 `canary.9` 的旧 updater 执行，它就仍会沿用旧的扫描删除逻辑。因此桥接更新阶段无法通过协议彻底阻止它删除旧 `logs/*`。

这是一项已知限制。

更严格地说：

- 旧 updater 在桥接这次运行中的行为不可控
- 桥接包只能通过“完全兼容旧逻辑”降低损坏范围，不能把旧逻辑变成新逻辑
- 因此桥接阶段的发布要求必须以旧 updater 的最坏行为为基线设计，而不是以新协议的理想行为为基线设计

本设计对它的处理方式是：

- 不再让这种行为继续出现在桥接之后的版本中
- 对需要保留历史日志的用户，提供手动恢复/手动升级路径

也就是说，本设计可以从体系上终结该问题，但不能让已经发布的 `canary.9` updater 在首次桥接时突然学会保留日志。

## 11. 结论

本设计把更新系统从“目录扫描 + 猜测删除”重构为“稳定引导器 + 显式协议 + 托管清单差集删除”。

核心变化只有两条：

- 删除依据从“新包缺席”改为“旧托管清单与新托管清单的差集”
- 任何不确定条件都降级为“只覆盖，不删除”

这样可以同时解决：

- `canary.9` 误删 `_internal/*`
- 正常更新误删 `logs/*`
- 未来包布局变化再次触发旧 updater 猜错根目录

并为之后的版本演进建立稳定、可验证、可扩展的更新协议基础。
