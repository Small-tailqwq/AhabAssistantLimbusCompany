from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
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
    if len(lines) > 500:
        problems.append(f"{relative}: SKILL.md exceeds the 500-line disclosure limit")

    for link in MARKDOWN_LINK_PATTERN.findall(read_text(path)):
        target = link.split("#", 1)[0]
        if not target or "://" in target or target.startswith("#"):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            problems.append(f"{relative}: missing linked resource {link!r}")


def iter_guidance_markdown() -> list[Path]:
    paths = [ROOT / "AGENTS.md"]
    claude = ROOT / "CLAUDE.md"
    if claude.exists():
        paths.append(claude)
    for base in (ROOT / ".agents", ROOT / ".opencode" / "agents", ROOT / ".github"):
        if base.exists():
            paths.extend(base.rglob("*.md"))
    return sorted(set(paths))


def validate_guidance_paths(problems: list[str]) -> None:
    stale_patterns = (".opencode/skills/", ".opencode/reference/")
    for path in iter_guidance_markdown():
        text = read_text(path)
        for pattern in stale_patterns:
            if pattern in text:
                problems.append(
                    f"{path.relative_to(ROOT)}: stale guidance path contains {pattern}"
                )

    legacy_skills = list((ROOT / ".opencode" / "skills").glob("*/SKILL.md"))
    for path in legacy_skills:
        problems.append(
            f"{path.relative_to(ROOT)}: project skills must live under .agents/skills"
        )

    agents = ROOT / "AGENTS.md"
    claude = ROOT / "CLAUDE.md"
    agents_text = read_text(agents)
    if len(agents_text.splitlines()) > 150:
        problems.append("AGENTS.md exceeds the 150-line project-guidance limit")
    if claude.exists() and read_text(agents) != read_text(claude):
        problems.append("AGENTS.md and local CLAUDE.md have drifted")


def validate_opencode_ci(problems: list[str]) -> None:
    agent = read_text(ROOT / ".opencode" / "agents" / "pr-review.md")
    agent_fragments = (
        "mode: primary",
        "write: false",
        "edit: false",
        "bash: false",
        "code-reviewer: allow",
        "automation-reviewer: allow",
        "i18n-reviewer: allow",
    )
    for fragment in agent_fragments:
        if fragment not in agent:
            problems.append(f".opencode/agents/pr-review.md: missing {fragment!r}")
    for fragment in ("finding ledger", "scope decisions", "new evidence"):
        if fragment not in agent:
            problems.append(f".opencode/agents/pr-review.md: missing {fragment!r}")

    comment_agent = read_text(ROOT / ".opencode" / "agents" / "pr-comment.md")
    for fragment in agent_fragments:
        if fragment not in comment_agent:
            problems.append(f".opencode/agents/pr-comment.md: missing {fragment!r}")

    workflow = read_text(ROOT / ".github" / "workflows" / "pr-review.yml")
    required_fragments = (
        "types: [opened, synchronize, reopened, ready_for_review]",
        "pull_request_review_comment:",
        "workflow_dispatch:",
        "ref: ${{ steps.context.outputs.base_sha }}",
        "refs/remotes/opencode/pr-head",
        "actual_head_sha=$(git rev-parse refs/remotes/opencode/pr-head)",
        "prior_review: priorReview?.body || ''",
        "scripts/build_pr_review_context.py",
        "opencode --pure run",
        "--agent pr-review",
        "opencode --pure github run",
        "AGENT: pr-comment",
        '--version "${OPENCODE_VERSION}"',
        "<!-- opencode-pr-review -->",
    )
    for fragment in required_fragments:
        if fragment not in workflow:
            problems.append(f".github/workflows/pr-review.yml: missing {fragment!r}")

    forbidden_fragments = (
        "ocr review",
        "OpenCodeReview",
        ".opencodereview",
        ".github/review-context.md",
        "ref: ${{ github.event.pull_request.head.sha",
    )
    for fragment in forbidden_fragments:
        if fragment in workflow:
            problems.append(
                f".github/workflows/pr-review.yml: forbidden legacy or unsafe fragment {fragment!r}"
            )

    context_builder = ROOT / "scripts" / "build_pr_review_context.py"
    if not context_builder.exists():
        problems.append("scripts/build_pr_review_context.py: missing PR context generator")

    issue_workflow = read_text(ROOT / ".github" / "workflows" / "issue-analyze.yml")
    for fragment in (
        '--version "${OPENCODE_VERSION}"',
        "opencode --pure debug agent triage",
        "opencode --pure run",
        "--agent triage",
    ):
        if fragment not in issue_workflow:
            problems.append(f".github/workflows/issue-analyze.yml: missing {fragment!r}")

    triage_agent = read_text(ROOT / ".opencode" / "agents" / "triage.md")
    for fragment in ("mode: primary", "webfetch: deny", '"gh issue *": allow'):
        if fragment not in triage_agent:
            problems.append(f".opencode/agents/triage.md: missing {fragment!r}")


def validate_review_convergence(problems: list[str]) -> None:
    upstream_skill = read_text(
        ROOT / ".agents" / "skills" / "upstream-contribution" / "SKILL.md"
    )
    for fragment in (
        "references/review-convergence.md",
        "stable finding IDs",
        "two consecutive re-reviews",
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
        "## Maintain one finding ledger",
        "## Triage before implementation",
        "## Impact note before every review fix",
        "## Convergence stop condition",
    ):
        if fragment not in convergence:
            problems.append(
                "upstream-contribution/references/review-convergence.md: "
                f"missing {fragment!r}"
            )

    review_skill = read_text(ROOT / ".agents" / "skills" / "code-review" / "SKILL.md")
    for fragment in ("stable finding IDs", "scope decision", "new evidence"):
        if fragment not in review_skill:
            problems.append(
                f".agents/skills/code-review/SKILL.md: missing {fragment!r}"
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
    validate_opencode_ci(problems)
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
