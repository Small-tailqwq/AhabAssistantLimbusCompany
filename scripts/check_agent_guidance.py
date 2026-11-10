from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Keep entry instructions small; cold-path detail belongs in references/.
SKILL_LINE_BUDGET = 180
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_skill_frontmatter(path: Path, problems: list[str]) -> dict[str, str]:
    lines = read_text(path).splitlines()
    if not lines or lines[0] != "---":
        problems.append(f"{path.relative_to(ROOT)}: missing opening YAML frontmatter")
        return {}

    try:
        closing = lines.index("---", 1)
    except ValueError:
        problems.append(f"{path.relative_to(ROOT)}: missing closing YAML frontmatter")
        return {}

    metadata: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:closing], start=2):
        if not line.strip():
            continue
        if ":" not in line:
            problems.append(
                f"{path.relative_to(ROOT)}:{line_number}: unsupported frontmatter syntax"
            )
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in metadata:
            problems.append(
                f"{path.relative_to(ROOT)}:{line_number}: duplicate frontmatter key {key}"
            )
        metadata[key] = value

    unexpected = sorted(set(metadata) - {"name", "description"})
    if unexpected:
        problems.append(
            f"{path.relative_to(ROOT)}: unsupported frontmatter keys: {', '.join(unexpected)}"
        )
    return metadata


def validate_skill(path: Path, seen_names: dict[str, Path], problems: list[str]) -> None:
    relative = path.relative_to(ROOT)
    metadata = parse_skill_frontmatter(path, problems)
    name = metadata.get("name", "")
    description = metadata.get("description", "")

    if not name:
        problems.append(f"{relative}: missing skill name")
    elif not NAME_PATTERN.fullmatch(name):
        problems.append(f"{relative}: invalid skill name {name!r}")
    elif name != path.parent.name:
        problems.append(
            f"{relative}: skill name {name!r} does not match directory {path.parent.name!r}"
        )

    if name in seen_names:
        problems.append(
            f"{relative}: duplicate skill name also used by {seen_names[name].relative_to(ROOT)}"
        )
    elif name:
        seen_names[name] = path

    if not description:
        problems.append(f"{relative}: missing skill description")
    elif len(description) > 1024:
        problems.append(f"{relative}: description exceeds 1024 characters")

    lines = read_text(path).splitlines()
    if len(lines) > SKILL_LINE_BUDGET:
        problems.append(
            f"{relative}: SKILL.md exceeds the {SKILL_LINE_BUDGET}-line budget; "
            "move cold-path detail into references/"
        )

    for link in MARKDOWN_LINK_PATTERN.findall(read_text(path)):
        target = link.split("#", 1)[0]
        if not target or "://" in target or target.startswith("#"):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            problems.append(f"{relative}: missing linked resource {link!r}")


def validate_guidance_paths(problems: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    claude = ROOT / "CLAUDE.md"
    agents_text = read_text(agents)
    if len(agents_text.splitlines()) > 150:
        problems.append("AGENTS.md exceeds the 150-line project-guidance limit")
    if claude.exists():
        # CLAUDE.md is a tracked pointer, not a second copy. A duplicated mirror
        # drifts silently from the tracked source, so it must forward instead.
        claude_text = read_text(claude)
        if not any(point in claude_text for point in ("@AGENTS.md", "](AGENTS.md)")):
            problems.append(
                "CLAUDE.md must point at AGENTS.md instead of duplicating it"
            )


def validate_review_convergence(problems: list[str]) -> None:
    upstream_skill = read_text(
        ROOT / ".agents" / "skills" / "upstream-contribution" / "SKILL.md"
    )
    for fragment in (
        "references/review-convergence.md",
        "稳定的 finding ID",
        "连续两轮复审",
    ):
        if fragment not in upstream_skill:
            problems.append(
                f".agents/skills/upstream-contribution/SKILL.md: missing {fragment!r}"
            )

    convergence = read_text(
        ROOT
        / ".agents"
        / "skills"
        / "upstream-contribution"
        / "references"
        / "review-convergence.md"
    )
    for fragment in (
        "## 维护单一发现台账",
        "## 实施前分诊",
        "## 每次修复前记录影响说明",
        "## 收敛停止条件",
    ):
        if fragment not in convergence:
            problems.append(
                "upstream-contribution/references/review-convergence.md: "
                f"missing {fragment!r}"
            )

    review_skill = read_text(ROOT / ".agents" / "skills" / "code-review" / "SKILL.md")
    if "references/pr-protocol.md" not in review_skill:
        problems.append(
            ".agents/skills/code-review/SKILL.md: missing 'references/pr-protocol.md'"
        )

    pr_protocol = read_text(
        ROOT / ".agents" / "skills" / "code-review" / "references" / "pr-protocol.md"
    )
    for fragment in ("稳定的 finding ID", "范围决策", "新证据"):
        if fragment not in pr_protocol:
            problems.append(
                f"code-review/references/pr-protocol.md: missing {fragment!r}"
            )


def main() -> int:
    problems: list[str] = []
    skill_files = sorted(SKILL_ROOT.glob("*/SKILL.md"))
    if not skill_files:
        problems.append(".agents/skills: no shared skills found")

    seen_names: dict[str, Path] = {}
    for path in skill_files:
        validate_skill(path, seen_names, problems)

    validate_guidance_paths(problems)
    validate_review_convergence(problems)

    if problems:
        lines = ["Agent guidance validation failed:"]
        lines.extend(f"- {problem}" for problem in problems)
        sys.stdout.write("\n".join(lines) + "\n")
        return 1

    sys.stdout.write(
        f"Agent guidance validation passed: {len(skill_files)} shared skills\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
