export const title = "桌面分身启动运行与注销";
export const state = v => {
  if (v.shutdownFinished) return v.waiting && !v.readyDelivery ? "分身已注销但启动仍在等待" : "分身已注销";
  if (v.state === "Stopping" && v.cancelDelivery) return "正在通知启动已取消";
  return {Idle:"未启动", Connecting:"正在连接", LaunchingWorker:"正在启动分身内进程", Ready:"分身已就绪", Running:"任务运行中", Stopping:"正在注销"}[v.state];
};
export const step = action => ({Start:"启动分身", RdpConnected:"Windows 登录完成", WorkerReady:"分身内进程就绪", DeliverReady:"启动调用收到通知", Run:"开始任务", RunResult:"任务返回结果", BeginShutdown:"停止并注销", CancelStarting:"取消启动等待", FinishShutdown:"系统确认注销", Done:"保持已注销"}[action]);
export const group = v => v.state === "Running" ? "运行" : "常规";
export const colors = {运行:"teal", 常规:"blue"};
