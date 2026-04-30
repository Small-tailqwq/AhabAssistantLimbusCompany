# Changelog

## [Unreleased] — Canary

## [1.5.0-canary.7] — 2026-05-01

### 构建修复
- fix: 修复 `Qt6Xml.dll` 被误删导致 dist 构建产物启动报错 (ImportError)
- fix: 从冗余文件列表移除 `PySide6/Qt6Xml.dll`，`qfluentwidgets.common.icon` 运行时依赖它

## [1.5.0-canary.6] — 2026-04-30

### CI 修复
- fix: 修复 build.py 中非 ASCII 字符 (`→`) 导致 Windows CI 构建失败 (UnicodeEncodeError)
- docs: 更新 AGENTS.md 编码陷阱警告，补充具体案例

## [1.5.0-canary.5] — 2026-04-30

### 资产管理器 (Asset Manager)
- feat: 新增资产管理器完整功能 — 扫描、搜索、过滤、缓存、回收站版本链归档恢复
- feat: 集成到工具启动器，支持独立窗口与信号路由
- feat: 添加设计文档与实现计划

### 镜牢稳定性
- fix: DARK 主题下多个模拟器兼容性问题
- fix: 退出商店循环 loop_count 递减移至 while 顶部，防止无限卡死
- fix: 空星光列表时 all_click_level 误算为 1

### 自动化优化
- feat: 镜牢事件唤醒次数随机化、楼层识别优化、ONNX 模型会话缓存
- opt: 通行证奖励领取改为批量点击 + 2 轮校验
- feat: 截图去重、帧内匹配结果缓存和批量并行匹配
- opt: OCR 跳过二值图的 CLAHE 处理，简化颜色空间转换
- fix: retry 添加节流保护和 skip_screenshot 参数，避免高频重复截图
- feat: BaseComboBox 新增 set_value 方法

### CI & Issue 自动诊断
- feat: 新增 Issue 自动诊断 CI (opencode-triage)，新 Issue 自动分析日志并回复
- feat: analyze skill 吸收 MaaEnd 经验 — 常见模式速查表、版本感知分析、置信度
- fix: 多项 CI 稳定性修复 — git 认证、超时控制、编码兼容
- docs: 添加 Windows CI 编码陷阱说明到 AGENTS.md 和构建指南

### 其他
- feat: 更新系统新增 SHA256 校验与旧残留清理
- feat: 添加代码审阅基础设施
- chore: 添加资产管理器设计文档和提取脚本

## [1.5.0-canary.4] — 2026-04-28

### issue 管理 & 调试工具
- feat(issue_manager): 新增 `append_log()`、`reimport_issue()` 方法，支持运行时追加日志和重新导入
- feat(issue_replay): 新增 Markdown 编辑侧窗，支持 Typora 式源码/预览分栏编辑
- feat(issue_replay): 批注区域支持 Markdown 渲染显示，右键菜单唤出编辑
- feat(issue_replay): 表格增加行号列、交替行色、优化列宽
- fix(issue_replay): 修复无法接受资源管理器文件拖放

### 模拟器 & 汉化支持
- feat: 新增实验性开关「模拟器已安装零协汉化」，允许在模拟器上使用汉化
- fix: 改进模拟器汉化开关返回值语义（SKIPPED）与提示样式
- fix: 修复 Mumu 模拟器退出时序冲突导致连接断开 (fix #617)

### 自动化
- fix: 降低彩色图片匹配阈值至 0.85 以提高识别率
- fix: 全仓 29 处裸 except 统一改为 Exception 或 ValueError
- feat: 定时任务结束操作新增「退出模拟器」独立选项
- perf(battle): 支持按战斗次数动态调整超时时间
- fix: 连续作战最大次数非法值静默修正
- fix: 重构 Daily_task_wrapper 消除重复分支
- fix: 移除 _batch_combat 多余的重复 return

### 配置
- fix(config): 修复 ConfigDict 导入缺失导致 NameError
- fix(config): 商店刷新次数默认值从 2 改为 1
- chore(config): PostMessage 输入默认值改为 False
- feat: 可自定义鼠标按下延迟及是否使用异步方法

### 其他
- docs: 添加文件删除严格管控策略与灾难恢复指引
- i18n: 同步并更新英文翻译文件

## [1.5.0-canary.3] — 2026-04-27

### 镜牢稳定性
- fix(mirror): re_start 添加 check_times 超时兜底，战斗失败后放弃/重开时卡死 90 秒后杀进程重启
- fix(mirror): back_init_menu loop_count 移到 while 顶部，修复无限循环不递减导致无法触发兜底

### 调试
- feat(debug): 新增重试调试 (debug_retry)，还原镜牢退出/重启流程中的识别情况与日志断点
- fix(debug): debug_retry 适配调试模型宪法——添加双重门控、UI 开关、父开关关闭时自动复位
- style: 新增调试模型宪法文档及 AALC 日志压缩分析工具

### 稳定性
- fix: 连续作战最大次数为 0 时除零崩溃，默认值改为 1


### 队伍设置
- feat(team_setting): 刷新选项添加 tooltips 提示，移入商店配置区
- fix(team_setting): 移除 tooltip 中的消耗信息，并入 i18n 翻译系统
- style(team_setting): 第十行布局补充 addStretch() 保持对齐一致

### 日常刷取 (Luxcavation)
- fix(luxcavation): 经验本多关入口添加点击重试与 DEBUG 日志
- fix(luxcavation): 修复纽本进入超时和 tab 加载竞态，添加纽本调试模式

### 商店
- fix(shop): OCR 金钱读取失败时释放刷新降级兜底，修复治疗-1 哨兵误判
- fix(mirror): 重写商店刷新逻辑，修复只刷新一次的问题；新增自定义刷新上限与保留升级资金选项

### i18n
- fix(i18n): 将 i18n 文件同步回上游版本，只保留 fix 新增的三条翻译
- feat(i18n): 新增 i18n 完整性检查脚本和工作流

### 工具链
- feat(tools): 新增日志复现工具，支持读取问题日志热切换配置进行调试

### 自动化 & 输入
- fix(automation): 截图延迟保护从仅 Logitech 扩展为所有输入模式

### 配置 & 稳定性
- fix(config): debug_mode 等未定义字段导致 Pydantic 崩溃，添加 ConfigDict(extra=allow)
- fix: 新任务启动时重置暂停状态，防止上一轮的暂停穿透到新一轮
- fix: 修饰键和弦超时检测释放 Alt+Tab 残留
- fix: 定时任务设置保存后自动关闭弹窗；修复旧配置 team3_history 为 None 时升级崩溃
- fix: 应对 PR 评审意见 — 改进弹窗关闭异常处理；finished_signal 改用仅启动的专用槽

### 其他
- merge: 合并 upstream/main 并吸收连战功能
- docs: 新增本地 issue 追踪模板与 LLM 交互指南

---

## [V1.4.9] — 2026-04-07 (fork 初始版本)

### 输入
- 添加罗技驱动 DLL 支持，将 AALC 输入转换为驱动层鼠标输入
- 添加仿生移动轨迹，将鼠标轨迹变换伪装
- 优化驱动输入时的鼠标移动轨迹

### 采集
- 添加 OBS 源作为图像来源，规避常规截图检测
- 优化原有楼层识别逻辑
- 添加部分日常任务输入彩色图片进行匹配

### 镜牢
- 修复镜牢流程与多项识别稳定性问题
- 精简镜牢事件检测并补全罗技告警收尾
- 优化镜牢寻路缓存与视角调度
- 实现镜牢路线规划车道感知重构与拖拽特性配置
- 添加镜牢路线图渐进线段补检与调试截图落盘
- 收紧镜牢异常处理并移除通配符导入

### 镜像商店
- 补充暗色模式等级确认弹窗模板资产

### 日志与调试
- 将日志设置改为调试模式，新增镜牢寻路调试开关
- 为模板匹配接口添加 log_result 静默参数

### 脚本生命周期
- 实现脚本优雅停止机制
- 修复 userStopError 被中间层 except Exception 误拦截
- 优化启动阶段停止响应与 OBS 预检重连
- 修复命令行 --start 未实际启动脚本，拆分 finished_signal/script_finished 信号

### UI
- 日常设置保存后自动关闭弹窗

### 低分辨率支持
- 修复低分辨率图片匹配并更新实验性输入开关
- 修复缺图回退与邮箱入口语言判断
- 添加实验性功能以支持低分辨率优化和罗技驱动仿生轨迹

### 输入修复
- 修复开启轨迹仿真后，部分截图时机过快的问题
- 尝试修复 PostMessage 导致的点击事件被忽略的问题
- Guard farming hotkey listener lifecycle
- Harden exact hotkey listener callbacks
- Fix exact global hotkey matching
- 修复自动战斗工具的两个 bug：「不处理事件」选项无效 & 编队界面误触

### 组件
- fix: BaseComboBox 初始化时无法正确显示 False/0 值
- refactor(BaseComboBox): 优化 items 访问与循环逻辑

### 其他
- 更新 README.md，添加改动清单和新标签图像
- 合并上游 main 并保留镜牢与停止流程修复
- 更新 requirements.txt from uv.lock
- 添加代理指导文档以支持快速启动和架构概述
- 在 AGENTS 中补充调试开关层级重置与中文提交约定
