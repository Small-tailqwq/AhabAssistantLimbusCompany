# Agent Note: 资产管理用共享 YAML 元数据和本地版本回收站

Status: implemented

## 问题

`assets/images/{theme}/{lang}/{category}/` 下有数百张模板图片，相似图片的用途只能靠文件名和目录推断。游戏更新后替换模板需要手动查找和覆盖，旧图没有保留，替换出错时无法回退。

## 决策

[AssetManager](../../../../tasks/tools/asset_manager.py) 是工具页中的独立窗口，数据与逻辑位于 [asset_library](../../../../tasks/tools/asset_library/)。

- **元数据共享。** `data/asset_library/library/<分类>.yaml` 纳入版本控制，每条记录保存相对 `assets/images/` 的 `file`、业务名、标签（语言、主题）、用途备注、SHA256 `checksum` 与 `status`（`active`、`missing`、`archived`）。分类由 `model.py` 中的路径前缀映射决定，不匹配的资产进入 `uncategorized`。
- **历史本地化。** `data/asset_library/recycle/`、`scan_cache.json` 和 `thumbnails/` 被 git 忽略，也不进入发行包。替换图片时，当前文件先作为新版本归档到 `recycle/files/<asset_key>/`，版本链记录在 `_meta.yaml`，新图片以原文件名写回原路径。切换到历史版本时，当前文件先追加为新版本再恢复，原路径文件缺失时直接恢复并记录来源；回收站目标文件不存在则报错。
- **扫描不阻塞界面。** 扫描在后台线程完成，先比对缓存中的 mtime 与大小，变化时才计算 SHA256。新增文件追加记录；校验值变化时旧记录标为 `archived` 并追加新记录；文件消失时标为 `missing` 并保留记录。
- **防抖写入。** 编辑只标记脏分类，1.5 秒单发计时器到期、切换资产或关闭窗口时统一写盘。

<!-- agent-note-format: alternatives-not-recorded (pre-format Agent Note) -->

## 后果

业务名称和用途说明随仓库共享，图片历史只在各自机器上可回退；换机或清理 `data/asset_library/recycle/` 后无法恢复旧版本。删除记录只改 YAML 状态，不删除图片文件。

新增图片目录时需要同步路径前缀映射，否则资产进入 `uncategorized`。YAML 以分类为单位整文件写回，多人同时编辑同一分类会产生合并冲突。
