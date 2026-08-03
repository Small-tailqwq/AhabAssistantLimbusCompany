# Pull Request 生命周期

创建 PR 后或恢复既有贡献工作时使用本文件。

## 确认当前状态

读 PR 元数据、当前 head SHA、base SHA、检查、审阅、内联线程与维护者提交。不要只依赖时间线评论，已解决线程与 requested-change 状态可能藏在那里。

记录：

```text
PR URL:
Local validated SHA:
Remote head SHA:
Base branch and current base SHA:
Checks pending/failing/passing:
Unresolved actionable threads:
Maintainer edits:
```

本地与远端 head 不一致时，先弄清原因再编辑。

## 审阅迭代

对每条可执行评论：

1. 对照上游代码、行为契约与既有发现台账核实；
2. 归类为范围内修复、范围决策、澄清、重复或有证据的分歧；
3. 在贡献 worktree 中实现修复；
4. 重跑针对性测试与上游画像 `code-review`；
5. 只推送已审阅的提交集；
6. 用具体提交或证据回复；
7. 回复后确认线程状态。

不要机械满足引入冗余或违背上游模式的建议。用源码与测试证据解释分歧。
没有新证据不重开本地已核实或被拒绝的发现。维护者要求在冻结契约之外的行为时，先显式记录范围变更，再实现，而不是藏在审阅修复提交里。

## CI 迭代

每次更新后：

- 等待与新 head SHA 关联的检查，而不是上一轮运行；
- 检查失败日志，不要凭任务名猜测；
- 区分贡献失败与无关的上游基础设施失败；
- 修复贡献失败并重跑受影响的本地检查；
- 报告外部失败，不声称 PR 为绿。

## base 移动

上游 base 移动时，检查新提交是否与修复重叠。仅为正确性或项目策略需要才 rebase。rebase 后复审完整 diff，因为冲突解决可能重新引入下游形态代码。

## 终态

- **Merged：** 识别最终 merge/squash/rebase 提交，进入下游核对。
- **Closed unmerged：** 记录理由，检查上游是否应用了替代修复。
- **Blocked：** 报告精确的待办方/行动、当前 head SHA、最新检查与未解决线程。不要把普通等待称作已完成的贡献。
