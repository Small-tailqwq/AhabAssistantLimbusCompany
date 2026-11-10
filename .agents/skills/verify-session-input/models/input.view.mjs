export const title = "游戏输入时限检查与事件处理";
export const state = v => ({Observed:"已取得画面", Checked:"输入前检查通过", Published:v.expired?"事件处理期间到达时限":"事件发布完成", Blocked:"输入已被拒绝", Sent:v.sentExpired?"到达时限后仍发送输入":"已发送输入", Timeout:"发送后才报告超时", Done:"本次输入完成"}[v.phase]);
export const step = action => ({ExpireBeforeCheck:"输入调用前到达时限", NewObservation:"新画面替代旧画面", CheckAccepted:"检查时限和画面", CheckRejected:"发现超时或旧画面", PublishQuickly:"事件处理返回", PublishAtDeadline:"事件处理耗尽剩余时间", RecheckRejected:"发送前再次检查并拒绝输入", SendInput:"再次检查后调用输入设备", PostInputCheck:"检查输入返回后的时限", Done:"保持结束"}[action]);
export const group = v => ["Blocked","Timeout"].includes(v.phase)?"结束":"常规";
export const colors = {结束:"orange", 常规:"blue"};
