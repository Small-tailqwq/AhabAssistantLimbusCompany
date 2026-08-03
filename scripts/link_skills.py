"""Expose .agents/skills to harnesses that do not read it.

Codex, pi, and OpenCode discover project skills in .agents/skills. Claude Code
reads only .claude/skills, but follows a symlinked <skill-name> entry. This
script links each shared skill into .claude/skills so one source of truth serves
every harness.

Windows symlinks need Developer Mode or admin, and this repository sets
core.symlinks=false, so committed symlinks would check out as plain text files.
Directory junctions need no privilege and are transparent to readers, so
Windows gets junctions and POSIX gets relative symlinks. Either way the links
are local build output: .claude/skills is gitignored and rebuilt by this script.

    uv run python scripts/link_skills.py
    uv run python scripts/link_skills.py --check
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / ".agents" / "skills"
TARGET_ROOT = ROOT / ".claude" / "skills"


class NonLinkPathError(RuntimeError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"refusing to remove non-link path: {path}")


class LinkCreationError(RuntimeError):
    def __init__(self, target: Path, detail: str) -> None:
        super().__init__(f"could not link {target}: {detail}")


def is_link(path: Path) -> bool:
    """True for POSIX symlinks and Windows symlinks or junctions."""
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            return bool(getattr(path.lstat(), "st_reparse_tag", 0))
        except OSError:
            return False
    return False


def link_target(path: Path) -> Path | None:
    try:
        raw = os.readlink(path)
    except OSError:
        return None
    # Windows junctions report an extended-length path; resolve() keeps the
    # \\?\ prefix, so strip it before comparing against a normal path.
    if raw.startswith("\\\\?\\"):
        raw = raw[4:]
    return Path(raw)


def resolves_to(path: Path, expected: Path) -> bool:
    target = link_target(path)
    if target is None:
        return False
    if not target.is_absolute():
        target = path.parent / target
    return target.resolve() == expected.resolve()


def remove_link(path: Path) -> None:
    """Remove a link without touching whatever it points at.

    Never removes a real directory: a mislabelled delete here would destroy
    authored skill content.
    """
    if not is_link(path):
        raise NonLinkPathError(path)
    if path.is_symlink() and os.name != "nt":
        path.unlink()
    else:
        os.rmdir(path)


def create_link(source: Path, target: Path) -> None:
    if os.name == "nt":
        # /J needs no privilege, unlike /D and os.symlink (WinError 1314).
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise LinkCreationError(
                target, result.stderr.strip() or result.stdout.strip()
            )
    else:
        os.symlink(
            os.path.relpath(source, target.parent), target, target_is_directory=True
        )


def discover_skills() -> list[str]:
    return sorted(p.parent.name for p in SOURCE_ROOT.glob("*/SKILL.md"))


def plan(skills: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Return (missing, stale, orphaned) skill link names."""
    missing: list[str] = []
    stale: list[str] = []
    orphaned: list[str] = []

    for name in skills:
        target = TARGET_ROOT / name
        if not target.exists() and not is_link(target):
            missing.append(name)
        elif not is_link(target):
            stale.append(name)
        elif not resolves_to(target, SOURCE_ROOT / name):
            stale.append(name)

    if TARGET_ROOT.is_dir():
        known = set(skills)
        for entry in sorted(TARGET_ROOT.iterdir()):
            if entry.name not in known and is_link(entry):
                orphaned.append(entry.name)

    return missing, stale, orphaned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift without creating or removing links",
    )
    args = parser.parse_args()

    if not SOURCE_ROOT.is_dir():
        sys.stdout.write(f"No shared skills at {SOURCE_ROOT.relative_to(ROOT)}\n")
        return 1

    skills = discover_skills()
    if not skills:
        sys.stdout.write("No shared skills found\n")
        return 1

    missing, stale, orphaned = plan(skills)

    if args.check:
        if not (missing or stale or orphaned):
            sys.stdout.write(f"Skill links up to date: {len(skills)} skills\n")
            return 0
        lines = ["Skill links are out of date:"]
        lines.extend(f"- missing: {name}" for name in missing)
        lines.extend(f"- stale: {name}" for name in stale)
        lines.extend(f"- orphaned: {name}" for name in orphaned)
        lines.append("Run: uv run python scripts/link_skills.py")
        sys.stdout.write("\n".join(lines) + "\n")
        return 1

    try:
        return apply_links(skills, missing, stale, orphaned)
    except (NonLinkPathError, LinkCreationError) as error:
        sys.stdout.write(f"{error}\n")
        return 1


def apply_links(
    skills: list[str], missing: list[str], stale: list[str], orphaned: list[str]
) -> int:
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0

    for name in stale:
        target = TARGET_ROOT / name
        if not is_link(target):
            # A real directory here is authored content, not build output.
            sys.stdout.write(
                f"SKIP {name}: {target.relative_to(ROOT)} is a real directory, not a link.\n"
                "     Move or delete it yourself, then rerun.\n"
            )
            skipped += 1
            continue
        remove_link(target)
        create_link(SOURCE_ROOT / name, target)
        written += 1

    for name in missing:
        create_link(SOURCE_ROOT / name, TARGET_ROOT / name)
        written += 1

    for name in orphaned:
        remove_link(TARGET_ROOT / name)

    sys.stdout.write(
        f"Skill links ready: {len(skills)} skills "
        f"({written} written, {len(orphaned)} orphaned removed, {skipped} skipped)\n"
    )
    sys.stdout.write(f"Source: {SOURCE_ROOT.relative_to(ROOT)}\n")
    sys.stdout.write(f"Target: {TARGET_ROOT.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
