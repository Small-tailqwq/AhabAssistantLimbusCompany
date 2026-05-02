import ast
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from module.config.config_typing import ConfigModel
from module.logger import log

ISSUES_DIR = Path("issues")
INDEX_PATH = ISSUES_DIR / ".aah_issues.json"


@dataclass
class IssueRecord:
    id: str
    name: str
    created_at: str
    modified_at: str
    aalc_version: str = ""
    notes: str = ""
    log_filename: str = ""
    config_count: int = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_time(iso_str: str) -> str:
    """将 ISO 8601 UTC 时间转换为本地可读格式。"""
    if not iso_str:
        return ""
    try:
        dt_utc = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()
        return dt_local.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_str


def _make_default_name(issue_id: str, version: str = "", iso_time: str = "") -> str:
    time_part = _format_time(iso_time) if iso_time else ""
    if version and time_part:
        return f"issue{issue_id} [v{version}] {time_part}"
    if time_part:
        return f"issue{issue_id} · {time_part}"
    return f"issue{issue_id}"


def find_config_snapshots(text: str) -> list[dict]:
    snapshots = []
    lines = text.split("\n")
    for line in lines:
        if "详细内容:" not in line:
            continue
        idx = line.index("详细内容:") + len("详细内容:")
        raw = line[idx:].strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                snapshots.append(ast.literal_eval(raw))
            except Exception:
                repaired = _repair_truncated_dict(raw)
                if repaired is not None:
                    snapshots.append(repaired)
    return snapshots


def _repair_truncated_dict(raw: str) -> Optional[dict]:
    for cut_pos in range(len(raw) - 1, len(raw) // 2, -1):
        if raw[cut_pos] == "," or raw[cut_pos] == " ":
            continue
        candidate = raw[:cut_pos] + ("" if raw[cut_pos] in "\"'" else "") + "}"
        for cl in ("'", '"'):
            if candidate.count(cl) % 2 != 0:
                break
        else:
            try:
                return ast.literal_eval(candidate + "}")
            except Exception:
                continue
    return None


def find_metadata(text: str) -> dict:
    meta = {}
    for line in text.split("\n"):
        if "AALC 版本:" in line:
            m = re.search(r"AALC 版本: (\S+),", line)
            if m:
                meta["version"] = m.group(1)
            m = re.search(r"配置文件版本: (\d+)", line)
            if m:
                meta["config_version"] = m.group(1)
        if "游戏分辨率:" in line:
            m = re.search(r"游戏分辨率: (\d+)", line)
            if m:
                meta["resolution"] = m.group(1)
            m = re.search(r"截图间隔: ([\d.]+)", line)
            if m:
                meta["screenshot_interval"] = m.group(1)
            m = re.search(r"鼠标间隔 ([\d.]+)", line)
            if m:
                meta["mouse_interval"] = m.group(1)
    return meta


def validate_config(data: dict) -> list[str]:
    warnings = []
    try:
        ConfigModel.model_validate(data)
    except Exception as e:
        warnings.append(f"配置校验失败: {e}")
    gp = data.get("game_path", "")
    if gp and "(x86" in gp and "(x86)" not in gp:
        warnings.append(f"game_path 疑似缺少闭合括号: {gp}")
    for key, val in data.items():
        if isinstance(val, str) and val.endswith("..."):
            warnings.append(f"配置项 '{key}' 的值可能被截断: {val}")
    return warnings


def repair_game_path(data: dict) -> dict:
    gp = data.get("game_path", "")
    if gp and "(x86" in gp and "(x86)" not in gp:
        data["game_path"] = gp.replace("(x86", "(x86)")
        log.info("已自动修复 game_path 括号缺失")
    return data


def _quote_str(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _yaml_val(value, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, str):
        if not value:
            return ['""']
        return [_quote_str(value)]
    if isinstance(value, list | tuple):
        if not value:
            return ["[]"]
        if all(isinstance(v, (str, int, float, bool, type(None))) for v in value):
            items = []
            for v in value:
                if isinstance(v, str):
                    items.append(_quote_str(v))
                elif isinstance(v, bool):
                    items.append(str(v).lower())
                elif v is None:
                    items.append("null")
                else:
                    items.append(str(v))
            return [f"[{', '.join(items)}]"]
        lines = []
        for v in value:
            if isinstance(v, dict):
                sub = _yaml_val(v, indent + 1)
                lines.append(f"{pad}- {{")
                for s in sub:
                    lines.append(f"{pad}  {s}")
                lines.append(f"{pad}  }}")
            else:
                sub = _yaml_val(v, indent + 1)
                for i, s in enumerate(sub):
                    lines.append(f"{pad}{'- ' if i == 0 else '  '}{s}")
        return lines
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            yk = _yaml_key(k)
            sub = _yaml_val(v, indent)
            if len(sub) == 1 and isinstance(v, (str, int, float, bool, type(None), list)):
                lines.append(f"{pad}{yk}: {sub[0]}")
            else:
                lines.append(f"{pad}{yk}:")
                for s in sub:
                    lines.append(f"{pad}  {s}")
        return lines
    return [str(value)]


def _yaml_key(k) -> str:
    sk = str(k)
    if isinstance(k, int | float) or re.fullmatch(r"\d+(\.\d+)?", sk):
        return f'"{sk}"'
    return sk


def dict_to_yaml(data: dict) -> str:
    lines = []
    for key, value in data.items():
        yk = _yaml_key(key)
        sub = _yaml_val(value, 1)
        if isinstance(value, dict):
            lines.append(f"{yk}:")
            for s in sub:
                lines.append(f"  {s}")
        else:
            for i, s in enumerate(sub):
                lines.append(f"{yk}: {s}" if i == 0 else f"  {s}")
    return "\n".join(lines)


class IssueManager:
    def __init__(self):
        self._issues: dict[str, IssueRecord] = {}
        ISSUES_DIR.mkdir(parents=True, exist_ok=True)
        self._load_index()
        self._sync_from_disk()

    def _load_index(self) -> None:
        if not INDEX_PATH.exists():
            return
        try:
            data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            for issue_id, info in data.get("issues", {}).items():
                self._issues[issue_id] = IssueRecord(
                    id=issue_id,
                    name=info.get("name", f"issue{issue_id}"),
                    created_at=info.get("created_at", ""),
                    modified_at=info.get("modified_at", ""),
                    aalc_version=info.get("aalc_version", ""),
                    notes=info.get("notes", ""),
                    log_filename=info.get("log_filename", ""),
                    config_count=info.get("config_count", 0),
                )
        except Exception as e:
            log.error(f"加载问题索引失败: {e}")

    def _save_index(self) -> None:
        data = {"next_id": self._next_auto_id(), "issues": {}}
        for issue_id, rec in self._issues.items():
            data["issues"][issue_id] = {
                "name": rec.name,
                "created_at": rec.created_at,
                "modified_at": rec.modified_at,
                "aalc_version": rec.aalc_version,
                "notes": rec.notes,
                "log_filename": rec.log_filename,
                "config_count": rec.config_count,
            }
        tmp = INDEX_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(INDEX_PATH)

    def _next_auto_id(self) -> str:
        if not self._issues:
            return "1"
        ids = sorted(int(k) for k in self._issues if k.isdigit())
        return str(ids[-1] + 1) if ids else "1"

    def _sync_from_disk(self) -> None:
        for entry in ISSUES_DIR.iterdir():
            if not entry.is_dir():
                continue
            issue_id = entry.name
            if issue_id in self._issues:
                continue
            config_yaml = entry / "extracted_config.yaml"
            if not config_yaml.exists():
                continue
            meta_json = entry / "metadata.json"
            created_at = _now_iso()
            modified_at = _now_iso()
            name = f"issue{issue_id}"
            if meta_json.exists():
                try:
                    meta = json.loads(meta_json.read_text(encoding="utf-8"))
                    created_at = meta.get("created_at", created_at)
                    modified_at = meta.get("modified_at", modified_at)
                    name = meta.get("name", name)
                except Exception:
                    pass
            self._issues[issue_id] = IssueRecord(
                id=issue_id,
                name=name,
                created_at=created_at,
                modified_at=modified_at,
            )
        self._save_index()

    def list_issues(self) -> list[IssueRecord]:
        def _sort_key(r: IssueRecord):
            try:
                return (0, int(r.id))
            except ValueError:
                return (1, r.id)
        return sorted(self._issues.values(), key=_sort_key)

    def get_issue(self, issue_id: str) -> Optional[IssueRecord]:
        return self._issues.get(issue_id)

    def get_issue_dir(self, issue_id: str) -> Path:
        return ISSUES_DIR / issue_id

    def get_config_path(self, issue_id: str) -> Path:
        return self.get_issue_dir(issue_id) / "extracted_config.yaml"

    def get_log_path(self, issue_id: str) -> Path:
        return self.get_issue_dir(issue_id) / "original.log"

    def get_notes_path(self, issue_id: str) -> Path:
        return self.get_issue_dir(issue_id) / "dev_notes.md"

    def _write_issue_files(
        self,
        issue_dir: Path,
        log_text: str,
        log_filename: str,
        config_index: int,
        auto_repair: bool = False,
    ) -> tuple[list[dict], dict, list[str]]:
        (issue_dir / "original.log").write_text(log_text, encoding="utf-8")

        meta = find_metadata(log_text)
        snapshots = find_config_snapshots(log_text)

        if not snapshots:
            return [], meta, ["未能在日志中找到任何配置快照"]

        if config_index >= len(snapshots):
            config_index = 0
        config = snapshots[config_index]

        if auto_repair:
            config = repair_game_path(config)

        warnings = validate_config(config)

        (issue_dir / "extracted_config.yaml").write_text(dict_to_yaml(config), encoding="utf-8")

        meta_lines = [
            f"来源日志: {log_filename}",
            f"AALC 版本: {meta.get('version', '未知')}",
            f"配置文件版本: {meta.get('config_version', '未知')}",
            f"游戏分辨率: {meta.get('resolution', '未知')}",
            f"截图间隔: {meta.get('screenshot_interval', '未知')}",
            f"鼠标间隔: {meta.get('mouse_interval', '未知')}",
        ]
        (issue_dir / "meta_info.txt").write_text("\n".join(meta_lines), encoding="utf-8")

        return snapshots, meta, warnings

    def import_issue(
        self,
        log_text: str,
        log_filename: str = "",
        config_index: int = 0,
        auto_repair: bool = False,
    ) -> tuple[Optional[str], list[dict], dict, list[str]]:
        issue_id = self._next_auto_id()
        issue_dir = self.get_issue_dir(issue_id)
        issue_dir.mkdir(parents=True, exist_ok=True)

        snapshots, meta, warnings = self._write_issue_files(
            issue_dir, log_text, log_filename, config_index, auto_repair
        )

        if not snapshots:
            shutil.rmtree(issue_dir)
            return None, [], meta, warnings

        created_at = _now_iso()
        default_name = _make_default_name(issue_id, meta.get("version", ""), created_at)
        metadata = {
            "id": issue_id,
            "name": default_name,
            "created_at": created_at,
            "modified_at": created_at,
            "aalc_version": meta.get("version", ""),
            "log_filename": log_filename,
            "config_count": len(snapshots),
        }
        (issue_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        rec = IssueRecord(
            id=issue_id,
            name=default_name,
            created_at=created_at,
            modified_at=created_at,
            aalc_version=meta.get("version", ""),
            log_filename=log_filename,
            config_count=len(snapshots),
        )
        self._issues[issue_id] = rec
        self._save_index()

        return issue_id, snapshots, meta, warnings

    def rename_issue(self, issue_id: str, new_name: str) -> bool:
        rec = self._issues.get(issue_id)
        if not rec:
            return False
        rec.name = new_name
        rec.modified_at = _now_iso()
        self._save_index()
        self._sync_issue_metadata(issue_id)
        return True

    def delete_issue(self, issue_id: str) -> bool:
        rec = self._issues.pop(issue_id, None)
        if rec is None:
            return False
        issue_dir = self.get_issue_dir(issue_id)
        if issue_dir.exists():
            shutil.rmtree(issue_dir)
        self._save_index()
        return True

    def set_notes(self, issue_id: str, notes: str) -> bool:
        rec = self._issues.get(issue_id)
        if not rec:
            return False
        rec.notes = notes
        rec.modified_at = _now_iso()
        self._save_index()
        self._sync_issue_metadata(issue_id)
        notes_path = self.get_notes_path(issue_id)
        if notes:
            notes_path.write_text(notes, encoding="utf-8")
        elif notes_path.exists():
            notes_path.unlink()
        return True

    def get_notes(self, issue_id: str) -> str:
        notes_path = self.get_notes_path(issue_id)
        if notes_path.exists():
            return notes_path.read_text(encoding="utf-8")
        rec = self._issues.get(issue_id)
        return rec.notes if rec else ""

    def append_log(self, issue_id: str, log_text: str, log_filename: str = "") -> str:
        issue_dir = self.get_issue_dir(issue_id)
        if not issue_dir.exists():
            raise ValueError(f"issue{issue_id} 目录不存在")

        existing_logs = sorted(
            p for p in issue_dir.iterdir()
            if p.is_file() and p.suffix in (".log", ".txt")
            and p.stem.startswith(("original", "supplement"))
        )
        next_index = len(existing_logs)
        if next_index == 0:
            log_path = issue_dir / "original.log"
        else:
            log_path = issue_dir / f"supplement_{next_index}.log"

        log_path.write_text(log_text, encoding="utf-8")

        rec = self._issues.get(issue_id)
        if rec:
            rec.modified_at = _now_iso()
            if log_filename:
                rec.log_filename = log_filename
            self._save_index()
            self._sync_issue_metadata(issue_id)

        return str(log_path)

    def reimport_issue(
        self,
        issue_id: str,
        log_text: str,
        log_filename: str = "",
        config_index: int = 0,
    ) -> tuple[bool, list[dict], dict, list[str]]:
        issue_dir = self.get_issue_dir(issue_id)
        if not issue_dir.exists():
            return False, [], {}, [f"issue{issue_id} 目录不存在"]

        rec = self._issues.get(issue_id)
        if not rec:
            return False, [], {}, [f"issue{issue_id} 不在索引中"]

        snapshots, meta, warnings = self._write_issue_files(
            issue_dir, log_text, log_filename, config_index
        )

        if not snapshots:
            return False, [], meta, warnings

        rec.aalc_version = meta.get("version", rec.aalc_version)
        rec.log_filename = log_filename
        rec.config_count = len(snapshots)
        rec.modified_at = _now_iso()
        self._save_index()
        self._sync_issue_metadata(issue_id)

        return True, snapshots, meta, warnings

    def _sync_issue_metadata(self, issue_id: str) -> None:
        rec = self._issues.get(issue_id)
        if not rec:
            return
        meta_json = self.get_issue_dir(issue_id) / "metadata.json"
        metadata = {
            "id": rec.id,
            "name": rec.name,
            "created_at": rec.created_at,
            "modified_at": rec.modified_at,
            "aalc_version": rec.aalc_version,
            "log_filename": rec.log_filename,
            "config_count": rec.config_count,
            "notes": rec.notes,
        }
        meta_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
