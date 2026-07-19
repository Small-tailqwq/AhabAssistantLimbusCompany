---
name: canary-release
description: Prepare, publish, verify, repair, or roll back an AALC canary prerelease, including isolated release work, version and changelog updates, build and update-protocol checks, tags, GitHub Actions, release notes, artifact inventory, channel behavior, and post-release reporting. Use for any canary release operation.
---

# AALC Canary Release

Treat a canary as a stateful release transaction. A tag or an uploaded archive alone is not completion; the release must be consumable through the intended channel and its artifacts and notes must match the tagged source.

## Authority and safety

- Inspect the original workspace before changing git state. Preserve unrelated changes.
- Prefer a named release branch in an isolated worktree when the workspace is dirty or release preparation is more than a one-file edit.
- Never print or commit tokens. Use authenticated `gh` or a credential helper.
- Pushing, tagging, editing a release, deleting assets/tags, and rerunning remote workflows are external writes. Execute only the authorized scope.
- Show the exact branch, commit, tag, remote, and release mutation before the first irreversible or externally visible step.

## Preflight

1. Confirm the target version, previous release tag, target commit, and release channel.
2. Inspect `git status --short`, remotes, existing tags, and existing release with the same version.
3. Confirm user-visible changes and known risks.
4. Verify current release policy from repository workflows and build scripts rather than memory.
5. Keep the current `bootstrap_version` unless update-protocol compatibility actually changes.
6. Generate protocol sidecars through build scripts; never hand-edit them.

Common release-source files are `assets/config/version.txt` and `CHANGELOG.md`. Do not modify user `config.yaml`.

## Prepare and review

Update only the release-scoped files. If code or workflows require a release-blocking fix, keep that change separately reviewable.

Inspect the exact release diff, then run checks selected by the touched areas:

```powershell
uv run python -m py_compile scripts\build.py
uv run python .\scripts\build.py --version dev
uv run python .\scripts\check_i18n.py --update
```

If `scripts/build.py` changes, its console output must remain ASCII for Windows cp1252 CI. Run `code-review` on release code or workflow changes before committing.

## Commit and tag gate

Before pushing:

- show version and previous tag;
- show `git diff --stat` and version/changelog diff;
- show planned Chinese commit message and annotated tag;
- confirm the target remote and source commit;
- obtain any external-write confirmation not already granted.

Create the annotated tag only on the verified release commit. Verify `git rev-parse <tag>^{commit}` before push. Push the branch and tag without force.

## Follow CI to the matching SHA

Monitor the workflow triggered by the target tag and verify it is building the expected commit. A successful unrelated run does not count.

On failure:

1. inspect the failing job and logs;
2. determine whether the failure is source, environment, credentials, or release-state related;
3. repair source through a reviewed commit and new intentional tag state—do not silently retarget a published tag;
4. rerun local checks and the matching remote workflow.

## Verify the GitHub Release

For a consumable canary, verify:

- release tag and target commit match;
- release is marked prerelease;
- exactly one `AALC_<version>.7z` exists;
- exactly one `AALC.update_manifest.json` exists;
- stable-only checksum policy remains satisfied where applicable;
- no duplicate, stale, or wrong-version asset is present;
- manifest and archive came from the matching workflow run;
- canary channel can discover the prerelease while stable filtering remains unchanged.

Do not announce the release until these checks pass.

## Release notes

The GitHub Release body is the user-visible source of truth and must agree with `CHANGELOG.md`. Use a notes file with `gh release edit` to avoid shell escaping errors.

Title:

```text
vX.Y.Z-canary.N — 金丝雀预览版
```

Body:

```markdown
### 新功能
- feat: <用户可见变更>

### 修复
- fix: <用户可见修复>

### 其他
- refactor/chore/docs: <必要说明>

[查看完整变更](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/compare/<prev_tag>...<new_tag>)
```

Omit empty categories. For a single category, the list may stand alone. Do not add a top-level heading. The compare link is mandatory. Avoid `#n` shorthand because fork issue numbers can resolve ambiguously; use full URLs or `本地 issue N`.

## Recovery and rollback

- Duplicate or wrong asset: do not delete until the exact release and asset are identified and deletion is authorized.
- Published tag points to wrong commit: stop distribution and report; tag replacement is destructive and requires explicit approval.
- Canary visible to stable users: fix release metadata or channel filtering before announcement.
- Manifest mismatch: regenerate from build scripts and create a traceable corrected release state.
- Bad canary behavior: document rollback or previous known-good version in the release body and report channel impact.

## Final report

```markdown
## Canary 发布结果
- Version / tag / commit：
- Release URL：
- Workflow run and result：
- Artifact inventory：
- Prerelease/channel verification：
- Release notes / changelog consistency：
- Local checks：
- Repairs or rollback state：
- Remaining follow-up：
```
