from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COPILOT_INSTRUCTIONS = ROOT / ".github" / "copilot-instructions.md"
PROMPT_OUTPUT_DIR = ROOT / ".github" / "prompts" / "opencode"
MCP_OUTPUT = ROOT / ".vscode" / "mcp.json"

BEGIN_MARKER = "<!-- opencode:begin -->"
END_MARKER = "<!-- opencode:end -->"

TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
STRUCTURED_EXTENSIONS = {".json", ".jsonc", ".toml", ".yaml", ".yml"}
MAX_FILE_BYTES = 256_000

PROMPT_KEYWORDS = {"skill", "skills", "prompt", "prompts"}
CONSTRAINT_KEYWORDS = {
    "agent",
    "agents",
    "constraint",
    "constraints",
    "instruction",
    "instructions",
    "rule",
    "rules",
    "system",
    "policy",
}
MCP_KEYWORDS = {"mcp", "server", "servers"}
IGNORE_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__"}
INSTRUCTION_KEYS = {
    "instruction",
    "instructions",
    "constraint",
    "constraints",
    "rule",
    "rules",
    "system",
    "system_prompt",
    "prompt",
    "content",
}


@dataclass(slots=True)
class TextResource:
    source: Path
    category: str
    content: str


@dataclass(slots=True)
class ImportSummary:
    roots: list[Path] = field(default_factory=list)
    constraints: list[TextResource] = field(default_factory=list)
    prompts: list[TextResource] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    mcp_sources: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import local OpenCode skills, agent constraints, and MCP servers into VS Code workspace files."
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        type=Path,
        help="Extra OpenCode search root. Can be provided multiple times.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and print the import plan without writing files.",
    )
    parser.add_argument(
        "--max-chars-per-file",
        type=int,
        default=4_000,
        help="Maximum imported constraint characters from a single source file.",
    )
    parser.add_argument(
        "--max-total-chars",
        type=int,
        default=20_000,
        help="Maximum total imported constraint characters written into copilot-instructions.md.",
    )
    return parser.parse_args()


def default_search_roots() -> list[Path]:
    env_roots = []
    appdata = os.getenv("APPDATA")
    local_appdata = os.getenv("LOCALAPPDATA")
    home = Path.home()

    if appdata:
        env_roots.append(Path(appdata) / "opencode")
    if local_appdata:
        env_roots.append(Path(local_appdata) / "opencode")

    env_roots.extend(
        [
            ROOT / ".opencode",
            home / ".opencode",
            home / ".config" / "opencode",
            home / "AppData" / "Roaming" / "opencode",
            home / "AppData" / "Local" / "opencode",
        ]
    )

    roots: list[Path] = []
    seen: set[Path] = set()
    for root in env_roots:
        resolved = root.resolve()
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)
    return roots


def tokenize_path(path: Path) -> set[str]:
    tokens: set[str] = set()
    for part in path.parts:
        for token in re.split(r"[^a-z0-9]+", part.lower()):
            if token:
                tokens.add(token)
    return tokens


def classify_text_path(path: Path) -> str | None:
    tokens = tokenize_path(path)
    if tokens & CONSTRAINT_KEYWORDS:
        return "constraint"
    if tokens & PROMPT_KEYWORDS:
        return "prompt"
    return None


def is_relevant_structured_path(path: Path) -> bool:
    tokens = tokenize_path(path)
    return bool(tokens & (PROMPT_KEYWORDS | CONSTRAINT_KEYWORDS | MCP_KEYWORDS | {"opencode"}))


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower().endswith(".prompt.md")


def should_skip(path: Path) -> bool:
    return any(part.lower() in IGNORE_DIRS for part in path.parts)


def read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def strip_json_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    escape = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    while index < len(text):
        current = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_line_comment:
            if current in "\r\n":
                in_line_comment = False
                result.append(current)
            index += 1
            continue

        if in_block_comment:
            if current == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if in_string:
            result.append(current)
            if escape:
                escape = False
            elif current == "\\":
                escape = True
            elif current == '"':
                in_string = False
            index += 1
            continue

        if current == '"':
            in_string = True
            result.append(current)
            index += 1
            continue

        if current == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue

        if current == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue

        result.append(current)
        index += 1

    return "".join(result)


def load_structured_file(path: Path) -> Any | None:
    suffix = path.suffix.lower()
    raw = read_text(path)
    if suffix == ".toml":
        return tomllib.loads(raw)
    if suffix in {".json", ".jsonc"}:
        source = strip_json_comments(raw) if suffix == ".jsonc" else raw
        return json.loads(source)
    return None


def looks_like_mcp_server(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    indicator_keys = {"command", "url", "transport", "type", "args", "env", "headers", "cwd"}
    return bool(set(value) & indicator_keys)


def extract_mcp_servers(node: Any, source: Path) -> dict[str, dict[str, Any]]:
    source_tokens = tokenize_path(source)
    found: dict[str, dict[str, Any]] = {}

    def visit(current: Any, trail: tuple[str, ...] = ()) -> None:
        if isinstance(current, dict):
            for key, value in current.items():
                key_text = str(key)
                key_lower = key_text.lower()
                next_trail = trail + (key_text,)
                trail_tokens = set(re.split(r"[^a-z0-9]+", "/".join(part.lower() for part in next_trail)))
                if key_lower in {"mcpservers", "mcp_servers"} and isinstance(value, dict):
                    for server_name, server_value in value.items():
                        if looks_like_mcp_server(server_value):
                            found[str(server_name)] = dict(server_value)
                elif key_lower == "servers" and isinstance(value, dict):
                    has_mcp_context = "mcp" in source_tokens or "mcp" in trail_tokens
                    if has_mcp_context:
                        for server_name, server_value in value.items():
                            if looks_like_mcp_server(server_value):
                                found[str(server_name)] = dict(server_value)
                visit(value, next_trail)
        elif isinstance(current, list):
            for index, item in enumerate(current[:32]):
                visit(item, trail + (str(index),))

    visit(node)
    return found


def extract_instruction_strings(node: Any) -> list[tuple[str, str]]:
    collected: list[tuple[str, str]] = []

    def visit(current: Any, trail: tuple[str, ...] = ()) -> None:
        if len(collected) >= 24:
            return
        if isinstance(current, dict):
            for key, value in current.items():
                key_text = str(key)
                next_trail = trail + (key_text,)
                if isinstance(value, str) and key_text.lower() in INSTRUCTION_KEYS and value.strip():
                    collected.append((".".join(next_trail), value.strip()))
                else:
                    visit(value, next_trail)
        elif isinstance(current, list):
            for index, item in enumerate(current[:16]):
                visit(item, trail + (str(index),))

    visit(node)
    return collected


def shorten_text(text: str, limit: int) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def relative_to_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def collect_from_root(root: Path, summary: ImportSummary) -> None:
    for candidate in root.rglob("*"):
        if not candidate.is_file() or should_skip(candidate):
            continue

        try:
            size = candidate.stat().st_size
        except OSError as error:
            summary.warnings.append(f"无法读取文件大小，已跳过: {candidate} ({error})")
            continue

        if size > MAX_FILE_BYTES:
            summary.warnings.append(f"文件过大，已跳过: {candidate}")
            continue

        if is_text_file(candidate):
            category = classify_text_path(candidate)
            if not category:
                continue
            try:
                content = read_text(candidate).strip()
            except OSError as error:
                summary.warnings.append(f"无法读取文本文件: {candidate} ({error})")
                continue
            if not content:
                continue
            resource = TextResource(source=candidate.resolve(), category=category, content=content)
            if category == "constraint":
                summary.constraints.append(resource)
            else:
                summary.prompts.append(resource)
            continue

        if candidate.suffix.lower() not in STRUCTURED_EXTENSIONS or not is_relevant_structured_path(candidate):
            continue

        try:
            structured = load_structured_file(candidate)
        except (OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
            summary.warnings.append(f"无法解析结构化文件: {candidate} ({error})")
            continue

        if structured is None:
            category = classify_text_path(candidate)
            if category:
                try:
                    content = read_text(candidate).strip()
                except OSError as error:
                    summary.warnings.append(f"无法读取结构化文本文件: {candidate} ({error})")
                    continue
                if content:
                    resource = TextResource(source=candidate.resolve(), category=category, content=content)
                    if category == "constraint":
                        summary.constraints.append(resource)
                    else:
                        summary.prompts.append(resource)
            elif "mcp" in tokenize_path(candidate):
                summary.warnings.append(f"暂不支持解析此格式的 MCP 配置: {candidate}")
            continue

        for server_name, server_value in extract_mcp_servers(structured, candidate).items():
            existing_source = summary.mcp_sources.get(server_name)
            if existing_source and existing_source != candidate.resolve():
                summary.warnings.append(
                    f"MCP 服务器名称重复，已使用后发现的配置覆盖: {server_name} ({existing_source} -> {candidate})"
                )
            summary.mcp_servers[server_name] = server_value
            summary.mcp_sources[server_name] = candidate.resolve()

        category = classify_text_path(candidate)
        if category in {"constraint", "prompt"}:
            snippets = extract_instruction_strings(structured)
            if snippets:
                content = "\n\n".join(
                    f"### {label}\n\n{snippet}" for label, snippet in snippets
                )
                resource = TextResource(source=candidate.resolve(), category=category, content=content)
                if category == "constraint":
                    summary.constraints.append(resource)
                else:
                    summary.prompts.append(resource)


def render_constraint_block(
    constraints: list[TextResource],
    max_chars_per_file: int,
    max_total_chars: int,
) -> str:
    header = (
        "## OpenCode 导入约束\n\n"
        "本节由 scripts/import_opencode_to_vscode.py 自动维护。"
        "需要修改时，请编辑 OpenCode 原始资源后重新运行导入脚本。"
    )
    if not constraints:
        return header + "\n\n未发现可导入的 agent 约束或指令资源。"

    sections: list[str] = [header, "\n### 来源\n"]
    sections.extend(f"- {relative_to_root(item.source)}" for item in constraints)
    sections.append("\n### 内容\n")

    remaining = max_total_chars
    for item in constraints:
        if remaining <= 0:
            sections.append("\n其余内容因长度限制未写入。")
            break
        trimmed = shorten_text(item.content, min(max_chars_per_file, remaining))
        sections.append(f"\n#### {relative_to_root(item.source)}\n\n{trimmed}\n")
        remaining -= len(trimmed)

    return "\n".join(sections).rstrip() + "\n"


def update_copilot_instructions(
    constraints: list[TextResource],
    max_chars_per_file: int,
    max_total_chars: int,
    dry_run: bool,
) -> None:
    existing = COPILOT_INSTRUCTIONS.read_text(encoding="utf-8") if COPILOT_INSTRUCTIONS.exists() else ""
    managed_block = (
        f"{BEGIN_MARKER}\n"
        f"{render_constraint_block(constraints, max_chars_per_file, max_total_chars)}\n"
        f"{END_MARKER}"
    )

    if BEGIN_MARKER in existing and END_MARKER in existing:
        updated = re.sub(
            re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
            managed_block,
            existing,
            count=1,
            flags=re.DOTALL,
        )
    elif not existing:
        updated = managed_block + "\n"
    else:
        separator = "\n" if existing.endswith("\n") else "\n\n"
        updated = existing + separator + managed_block + "\n"

    if dry_run:
        return

    COPILOT_INSTRUCTIONS.parent.mkdir(parents=True, exist_ok=True)
    COPILOT_INSTRUCTIONS.write_text(updated, encoding="utf-8")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "resource"


def render_prompt(resource: TextResource) -> str:
    title = resource.source.stem.replace("_", " ").replace("-", " ").strip() or resource.source.name
    return (
        f"# {title}\n\n"
        f"来源: {relative_to_root(resource.source)}\n\n"
        f"以下内容由 OpenCode 资源导入生成。\n\n"
        f"{resource.content.strip()}\n"
    )


def write_prompt_files(prompts: list[TextResource], dry_run: bool) -> None:
    if dry_run:
        return

    PROMPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for existing in PROMPT_OUTPUT_DIR.glob("opencode-*.prompt.md"):
        existing.unlink()

    for index, resource in enumerate(prompts, start=1):
        filename = f"opencode-{index:02d}-{slugify(resource.source.stem)}.prompt.md"
        target = PROMPT_OUTPUT_DIR / filename
        target.write_text(render_prompt(resource), encoding="utf-8")


def merge_mcp_config(imported_servers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if MCP_OUTPUT.exists():
        raw = MCP_OUTPUT.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"{MCP_OUTPUT} 不是对象 JSON")
        existing = parsed

    target_key = "servers"
    if isinstance(existing.get("mcpServers"), dict) and not isinstance(existing.get("servers"), dict):
        target_key = "mcpServers"

    merged_servers = dict(existing.get(target_key, {})) if isinstance(existing.get(target_key), dict) else {}
    merged_servers.update(imported_servers)
    existing[target_key] = merged_servers
    return existing


def write_mcp_config(imported_servers: dict[str, dict[str, Any]], dry_run: bool) -> None:
    if not imported_servers or dry_run:
        return
    merged = merge_mcp_config(imported_servers)
    MCP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MCP_OUTPUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover_roots(extra_roots: list[Path]) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()

    for root in [*default_search_roots(), *extra_roots]:
        resolved = root.expanduser().resolve()
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)
    return roots


def print_summary(summary: ImportSummary, dry_run: bool) -> None:
    mode = "dry-run" if dry_run else "write"
    print(f"[opencode-import] mode={mode}")
    if summary.roots:
        print("[opencode-import] scanned roots:")
        for root in summary.roots:
            print(f"  - {root}")
    else:
        print("[opencode-import] no OpenCode roots found")

    print(f"[opencode-import] constraints={len(summary.constraints)}")
    print(f"[opencode-import] prompts={len(summary.prompts)}")
    print(f"[opencode-import] mcp_servers={len(summary.mcp_servers)}")

    if summary.mcp_servers:
        print("[opencode-import] MCP sources:")
        for server_name in sorted(summary.mcp_servers):
            print(f"  - {server_name}: {summary.mcp_sources[server_name]}")

    if summary.warnings:
        print("[opencode-import] warnings:")
        for warning in summary.warnings:
            print(f"  - {warning}")


def main() -> int:
    args = parse_args()
    roots = discover_roots(args.root)
    summary = ImportSummary(roots=roots)

    for root in roots:
        collect_from_root(root, summary)

    summary.constraints.sort(key=lambda item: relative_to_root(item.source))
    summary.prompts.sort(key=lambda item: relative_to_root(item.source))

    update_copilot_instructions(
        summary.constraints,
        max_chars_per_file=args.max_chars_per_file,
        max_total_chars=args.max_total_chars,
        dry_run=args.dry_run,
    )
    write_prompt_files(summary.prompts, dry_run=args.dry_run)

    try:
        write_mcp_config(summary.mcp_servers, dry_run=args.dry_run)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        summary.warnings.append(f"无法写入 MCP 配置: {error}")

    print_summary(summary, dry_run=args.dry_run)

    if not roots:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())