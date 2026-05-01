# TODO

## 镜牢商店（issues/8）

- [ ] Bug #1: `leave_shop_confirm` 在 Mumu background_click 下点击无效，循环逃生路径被 `continue` 跳过
  - 方向：要么补 `loop_count -= 1` 让计时能逃生，要么换成前台点击
- [ ] Bug #2: DARK 主题下 `_get_cost()` OCR 金钱读取失败，需确认是 bbox 偏移还是 OCR 兼容性
  - 背景：困难镜牢里的特殊商店（非普通商店），需要有账号才能测试
  - 方向：debug_shop 已加，跑一次看 `logs/shop_debug/` 截图
- [ ] Bug #3: `back_init_menu` 卡死后强重启，未知 UI 状态未覆盖
  - 方向：需要 DARK 主题下的异常状态截图分析

## DARK 主题资产覆盖

- [ ] `assets/images/dark/` 缺少 `mirror/theme_pack/feature_theme_pack_assets.png`
  - 已用 `threshold=0.75` 临时绕过
- [ ] 全局盘点：还有哪些图片只有 default 没有 dark 变体且匹配度临界

## 其他

- [ ] 商店 `enhance_gifts` 滚动代码被注释掉了（`in_shop.py:1106-1110`），列表外饰品永远找不到
- [ ] `sell_gifts` 中 `system_sell` 从未在售卖路径设为 False，靠 `sell_chance` 20 次兜底
- [ ] 模拟器镜牢寻路卡死 — `mirror_keyboard_navigation` 在 Mumu 后台模式下无效
  - 临时修复：`enter_mirror_road()` + `confirm_current_mirror_node()` 跳过键盘，改用鼠标点击
  - 长期：需要系统性地处理 `mirror_keyboard_navigation && cfg.simulator` 冲突
