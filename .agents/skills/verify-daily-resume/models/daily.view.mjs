export const title = "日常采光重启后的批次续跑";
export const state = v => {
  if(v.starts > 1) return "同一计划批次再次开战";
  return {Home:v.done?"已记录完成并回到主页":v.victories>0?"已回到主页但胜利未记入批次":"回到主页且批次未记录", Formation:v.victories>0?"重新选关与编队":"选关与编队", Fighting:"批次战斗中", Victory:"已经胜利但尚未记录", CommitPending:"结算已确认", Checkpointed:"完成记录已写入", RecoveringVictory:"胜利后重启", HomeSettlement:"恢复后发现胜利结算", RecoveryCommitPending:"恢复后的结算已确认", ReturningHome:"恢复的批次完成记录已写入", RecoveringDone:"记录完成后重启", Done:"日常已完成"}[v.phase];
};
export const step = action => ({EnterBatch:"进入未记录的批次", StartBattle:"开始战斗", BattleWon:"战斗胜利", RestartBeforeCheckpoint:"观察失败并重启游戏", ObserveRecoveredSettlement:"返回主页时识别结算", DismissRecoveredSettlement:"确认恢复后的结算", RecordRecoveredCheckpoint:"将胜利记入当前批次", ObserveHomeAfterRecovery:"重新观察并确认主页", ConfirmBattleSettlement:"确认胜利结算", RecordCheckpoint:"记录批次完成", RestartAfterCheckpoint:"后续观察失败并重启", ReturnHome:"返回主页", Complete:"跳过已记录的批次", Done:"保持完成"}[action]);
export const group = v => v.starts > 1 ? "风险" : "常规";
export const colors = {风险:"orange", 常规:"teal"};
