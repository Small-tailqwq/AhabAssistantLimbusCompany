# Changelog

## [Unreleased] — Canary

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
