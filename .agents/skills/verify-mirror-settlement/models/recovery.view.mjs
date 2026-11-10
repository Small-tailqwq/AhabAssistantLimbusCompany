export const title = "镜牢结算中断与队列保存";
export const state = v => {
  if (v.payments > 1) return "一轮计划再次确认模块";
  return {
    Settlement: v.entered > 0 ? "额外镜牢已经通关" : "当前轮通关待领奖",
    Receipt: "模块已确认等待领取回执",
    InputBlocked: "回执点击被系统拒绝",
    RetryEntryWithReceipt: "输入恢复后回执仍在",
    Failed: "回执无法接管且任务失败",
    AwaitEntrance: "领取回执已确认待观察入口",
    FatalObserved: "回执后观察到致命提示",
    Restarted: "游戏重启且本轮尚未计数",
    HomeAfterRestart: "已经确认返回主页",
    MirrorHub: "打开镜牢入口",
    FreshEntry: "进入新的镜牢入口",
    SecondDungeon: "一轮计划又开启新镜牢",
    Claimed: "本轮领取完成待轮换",
    SavingQueue: "内存队列已轮换待保存",
    StopRequested: "停止已请求且队列尚未保存",
    Done: "队列已保存且任务完成",
    Cancelled: "领取完成但取消丢失轮换"
  }[v.phase];
};
export const step = action => ({
  SubmitModules: "确认模块",
  InputBlocked: "确认回执时光标移动被拒绝",
  WaitForInputRecovery: "等待十五秒后重新观察入口",
  EntryCannotRecognizeReceipt: "恢复输入后入口观察达到上限",
  ConfirmReceipt: "确认领取回执",
  ObserveFatalPage: "下一帧观察到致命提示",
  RestartGame: "重启游戏并抛出重启异常",
  ObserveHomeAfterRestart: "恢复处理重新观察并确认主页",
  NavigateFromHome: "点击主页的驾驶入口",
  NavigateToEntry: "打开新的镜牢进入面板",
  EnterAnotherDungeon: "点击进入并开启新镜牢",
  CompleteAnotherDungeon: "额外镜牢通关",
  ObserveEntrance: "下一帧确认返回入口",
  RotateQueue: "把已完成队伍移至队尾",
  SaveQueue: "保存队列",
  CancelBeforeSave: "停止令牌在保存前取消",
  RejectCanceledSave: "保存回调检查取消并结束任务",
  Done: "保持结果"
}[action]);
export const group = v => v.entered > 0 || v.phase === "Failed" || v.phase === "Cancelled" ? "风险" : "正常";
export const colors = {正常: "teal", 风险: "orange"};
