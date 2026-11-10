export const title = "镜牢奖励结算的确认条件";
export const state = v => ({
  Observe: "观察通关结算",
  Ready: v.scenario === "noClear" ? "尚无通关证据" : v.scenario === "keep" ? "保留结算奖励"
    : v.selected > 0 ? `周奖励已选${v.selected}次` : "可以确认模块",
  WaitingWeekly: `等待已选${v.selected}次周奖励减少`,
  Submitted: "模块确认已发送",
  Receipt: "领取回执可见",
  Returning: "回执已确认等待入口",
  Done: v.claimed ? "领取完成" : "保留奖励且不轮换",
  Failed: v.returned ? "已回入口但缺少回执" : "结算未确认并停止"
}[v.phase]);
export const step = (action, from) => ({
  ObserveCompletion: from.scenario === "noClear" ? "观察不到通关标记" : "观察到通关标记",
  KeepRewards: "按配置保留奖励",
  MissingCompletion: "观察达到上限且不花模块",
  RequestWeeklyChange: "取消最右侧周奖励 [选中数量超过配置]",
  ObserveWeeklyDecrease: "新帧确认选中数量下降",
  WeeklyUnchanged: "八次等待仍未观察到变化",
  SubmitModules: "确认模块 [选中数量符合配置]",
  ObserveReceipt: "观察到领取回执",
  SubmissionUnconfirmed: "达到结算观察上限",
  ReturnWithoutReceipt: "直接观察到入口但没有回执",
  AcknowledgeReceipt: "确认领取回执",
  ObserveEntrance: "新帧确认已返回入口",
  ReturnUnconfirmed: "达到观察上限仍未返回入口",
  Done: "保持结果"
}[action]);
export const group = v => v.phase === "Failed" ? "未确认" : "正常";
export const colors = {正常: "teal", 未确认: "orange"};
