#!/usr/bin/env python3
"""Agent Notes gate for Python >= 3.9 (standard library only).

Reads ``<notes-dir>/agent-notes.config.json`` and enforces the contract in
``<notes-dir>/README.md``: the closed lifecycle/class tree, the in-file format,
bilingual pairs when counterpart languages are configured, and the sealed archive.
``gates/node/agent-notes.mts`` implements the same rules and prints identical
diagnostics; change both together.

Usage (run from the repository root):
  python3 agent_notes.py check                     verify everything
  python3 agent_notes.py seal                      verify, then append seals for newly archived files
  python3 agent_notes.py pair --write NOTE... | --all   re-record bilingual consistency sidecars
  python3 agent_notes.py lint [NOTE... | --all]    list prose candidates in changed notes (never fails)
Options: --repo-root DIR (default: cwd), --notes-dir DIR (default: <repo-root>/.agents/notes).
Environment: AGENT_NOTES_BASE_REF names the trusted commit whose manifest seals must survive
and against which `lint` finds changed notes (default HEAD; CI should pass the pull request
base SHA with full history checked out).
Exit status: 0 clean, 1 violations, 2 usage or configuration error. `lint` hits are candidates,
not violations; with `"proseLint": true` in the config, `check` lists them after a clean run.
"""

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

LIFECYCLES = ["proposed", "implemented", "rejected"]
ARCHIVE = "archived"
LIFECYCLE_ROOT_FILES = {"AGENTS.md", "CLAUDE.md"}
ARCHIVE_ROOT_FILES = {"AGENTS.md", "CLAUDE.md", "manifest.json"}
GRANDFATHER = "<!-- agent-note-format: alternatives-not-recorded (pre-format Agent Note) -->"
NOTE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-[^/]+\.md$")
LANG = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]+)?$")
HEADING_KEYS = ["problem", "proposal", "decision", "alternatives", "acceptance", "risks", "consequences"]
# The recall probes of references/prose.md, in the same order; change all three copies together.
# Explicit ASCII lookarounds instead of \b: Python treats CJK as word characters, JavaScript does not.
PROSE_PROBES = [
    ("scope-disclaimer",
     r"(does not|doesn't|cannot|can't|won't) (prove|guarantee|mean|imply|ensure|verify|judge)"
     r"|不能(证明|保证|判断|代表|说明)|不(意味着|代表|等于|保证)|并不|只(能)?说明|不配置|不提供|不涉及"),
    ("straw-man-or-escalation", r"not [^.]{1,40}, but|rather than|instead of|不是.*而是|而非|并非|不仅|既.*，也"),
    ("announcement-or-summary", r"worth noting|importantly|essentially|in short|值得注意|关键在于|本质上|总之|这样一来"),
    ("session-vantage",
     r"(?<![A-Za-z])this (PR|change|note|session)(?![A-Za-z])|本次|这次|此次|本笔记|维护者(的)?(明确)?要求|用户要求"
     r"|locally|本机|(Python|Node|node|python) ?v?[0-9]+\.[0-9]+\.[0-9]+"),
    ("draft-history",
     r"originally|previously|formerly|no longer|used to|the old |legacy|[0-9]+ original"
     r"|最初|原先|原本|原来|此前|曾经|不再|改为|原 ?[0-9]|旧 ?`"),
    ("vague-reference",
     r"(?<![A-Za-z])(etc\.|and so on|as needed|as appropriate|various|relevant (files|docs|code|parts|settings|rationale|changes))"
     r"|相关(文件|文档|代码|配置|逻辑|内容|部分|理由)|相应的?(文件|文档|代码|配置|修改|处理)|某些|若干|一些|适当|必要时|等等|之类"),
]
SUPERSEDES = r"supersed|replaces|取代"
NOTE_LINK = r"\]\((?![A-Za-z][A-Za-z0-9+.-]*:)([^)#\s]+\.md)(?:#[^)]*)?\)"


class UsageError(Exception):
    pass


# ---------- shared helpers ----------

def read_text(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as handle:
        return handle.read().replace("\r\n", "\n")


def sha256(content):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def valid_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        return False
    try:
        datetime.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return False
    return True


def is_string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item != "" for item in value)


def listing(path):
    """Return (name, is_dir) entries sorted by name."""
    return sorted(((e.name, e.is_dir()) for e in os.scandir(path)), key=lambda e: e[0])


def markdown_under(base, rel_dir):
    out = []
    for name, is_dir in listing(os.path.join(base, rel_dir)):
        rel = rel_dir + "/" + name
        if is_dir:
            out.extend(markdown_under(base, rel))
        elif name.endswith(".md"):
            out.append(rel)
    return sorted(out)


def prose(lines):
    """Drop fenced code blocks (``` fences) so example headings are not treated as structure."""
    out = []
    in_fence = False
    for line in lines:
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return out


def line_at(lines, index):
    return lines[index] if 0 <= index < len(lines) else None


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# ---------- configuration ----------

def load_config(notes_dir):
    path = os.path.join(notes_dir, "agent-notes.config.json")
    if not os.path.exists(path):
        raise UsageError("config: %s is missing" % path)
    try:
        raw = json.loads(read_text(path))
    except ValueError:
        raise UsageError("config: agent-notes.config.json is not valid JSON")  # Parser wording differs across runtimes.

    def fail(msg):
        raise UsageError("config: " + msg)

    if not isinstance(raw, dict):
        fail("expected a JSON object")
    keys = ["version", "classes", "headings", "primaryLanguage", "counterpartLanguages", "formatAdopted", "forbiddenRoots"]
    for key in raw:
        if key not in keys + ["proseLint"]:
            fail('unknown field "%s"' % key)
    for key in keys:
        if key not in raw:
            fail('missing field "%s"' % key)
    if raw["version"] != 1 or isinstance(raw["version"], bool):
        fail('"version" must be 1')
    classes = raw["classes"]
    if not is_string_list(classes) or len(classes) == 0:
        fail('"classes" must be a non-empty list of strings')
    for cls in classes:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", cls):
            fail('class "%s" must be kebab-case' % cls)
    if len(set(classes)) != len(classes):
        fail('"classes" contains duplicates')
    headings = raw["headings"]
    if not isinstance(headings, dict):
        fail('"headings" must be an object')
    for key in headings:
        if key not in HEADING_KEYS + ["bannedInImplemented"]:
            fail('unknown field "headings.%s"' % key)
    for key in HEADING_KEYS:
        if not isinstance(headings.get(key), str) or headings[key].strip() == "":
            fail('"headings.%s" must be a non-empty string' % key)
    if not is_string_list(headings.get("bannedInImplemented")):
        fail('"headings.bannedInImplemented" must be a list of non-empty strings')
    primary = raw["primaryLanguage"]
    if not isinstance(primary, str) or not LANG.match(primary):
        fail('"primaryLanguage" must be a language tag such as "en" or "zh"')
    counterparts = raw["counterpartLanguages"]
    if not isinstance(counterparts, list) or not all(isinstance(l, str) and LANG.match(l) for l in counterparts):
        fail('"counterpartLanguages" must be a list of language tags')
    if primary in counterparts or len(set(counterparts)) != len(counterparts):
        fail('"counterpartLanguages" must be distinct and exclude the primary language')
    if not isinstance(raw["formatAdopted"], str) or not valid_date(raw["formatAdopted"]):
        fail('"formatAdopted" must be a YYYY-MM-DD date')
    if not is_string_list(raw["forbiddenRoots"]):
        fail('"forbiddenRoots" must be a list of repository-relative paths')
    if not isinstance(raw.get("proseLint", False), bool):
        fail('"proseLint" must be true or false')
    return {
        "proseLint": raw.get("proseLint", False),
        "classes": classes,
        "headings": headings,
        "primary": primary,
        "langs": counterparts,
        "formatAdopted": raw["formatAdopted"],
        "forbiddenRoots": raw["forbiddenRoots"],
    }


# ---------- tree ----------

def counterpart_language_of(name, config):
    for lang in config["langs"]:
        if name.endswith("." + lang + ".md"):
            return lang
    return None


def walk_tree(repo_root, notes_dir, config, errors):
    for name, is_dir in listing(notes_dir):
        if name == "INDEX.md":
            errors.append("tree: INDEX.md — centralized indexes are forbidden; browse the lifecycle/class folders or search")
        elif is_dir and name != ARCHIVE and name not in LIFECYCLES:
            errors.append("tree: %s/ — unknown lifecycle folder (allowed: %s, plus %s/)" % (name, ", ".join(LIFECYCLES), ARCHIVE))
    notes = []
    for lifecycle in LIFECYCLES:
        if not os.path.exists(os.path.join(notes_dir, lifecycle)):
            errors.append("tree: %s/ — required lifecycle folder is missing" % lifecycle)
            continue
        unknown = set()
        for name, is_dir in listing(os.path.join(notes_dir, lifecycle)):
            if is_dir and name not in config["classes"]:
                errors.append('tree: %s/%s/ — unknown class folder "%s" (allowed: %s)' % (lifecycle, name, name, ", ".join(config["classes"])))
                unknown.add(name)
        for rel in markdown_under(notes_dir, lifecycle):
            segs = rel.split("/")
            name = segs[-1]
            if len(segs) > 2 and segs[1] in unknown:
                continue
            if len(segs) == 2 and name in LIFECYCLE_ROOT_FILES:
                continue
            if counterpart_language_of(name, config) is not None:
                continue
            if len(segs) != 3:
                errors.append("tree: %s — expected {lifecycle}/{class}/yyyy-mm-dd-topic.md (got depth %d)" % (rel, len(segs)))
                continue
            m = NOTE_NAME.match(name)
            if m is None or not valid_date(m.group(1)):
                errors.append("tree: %s — filename must be yyyy-mm-dd-topic.md with a real date" % rel)
                continue
            notes.append({"lifecycle": lifecycle, "rel": rel, "date": m.group(1)})
    for root in config["forbiddenRoots"]:
        if os.path.exists(os.path.join(repo_root, root)):
            errors.append("tree: %s — forbidden legacy location; Agent Notes live under the notes directory" % root)
    return notes


# ---------- format ----------

def banned_heading(heading, banned):
    text = heading[3:].lower()
    for b in banned:
        word = b.lower()
        if text == word or text.startswith(word + " ") or text.startswith(word + ":") or text.startswith(word + "："):
            return True
    return False


def check_format(notes_dir, notes, config, errors):
    h = config["headings"]
    required = {
        "proposed": [h["proposal"], h["acceptance"], h["risks"]],
        "implemented": [h["decision"], h["consequences"]],
        "rejected": [h["proposal"]],
    }
    grammar = {
        "proposed": re.compile(r"^Status: proposed$"),
        "implemented": re.compile(r"^Status: implemented$"),
        "rejected": re.compile(r"^Status: rejected — \S.*$"),
    }
    for note in notes:
        def fail(msg, note=note):
            errors.append("format: %s — %s" % (note["rel"], msg))

        lifecycle = note["lifecycle"]
        lines = read_text(os.path.join(notes_dir, note["rel"])).split("\n")
        body = prose(lines)
        if not re.match(r"^# Agent Note: \S", line_at(lines, 0) or ""):
            fail("line 1 must be `# Agent Note: <title>`")
        if line_at(lines, 1) != "":
            fail("line 2 must be blank")
        if not grammar[lifecycle].match(line_at(lines, 2) or ""):
            shown = "`Status: rejected — <reason>`" if lifecycle == "rejected" else "`Status: %s`" % lifecycle
            fail("line 3 must be the %s status line (%s)" % (lifecycle, shown))
        if line_at(lines, 3) != "":
            fail("line 4 must be blank")
        if len([l for l in body if l.startswith("Status:")]) > 1:
            fail("the line-3 `Status:` line must be the only one outside code fences")
        h2s = [l.rstrip() for l in body if l.startswith("## ")]
        first = json.dumps(h2s[0] if h2s else "<none>", ensure_ascii=False)
        if not h2s or h2s[0] != "## " + h["problem"]:
            fail("the first section must be `## %s` (got %s)" % (h["problem"], first))
        for name in required[lifecycle]:
            if "## " + name not in h2s:
                fail("missing the required `## %s` section" % name)
        if lifecycle == "implemented":
            for heading in [x for x in h2s if banned_heading(x, h["bannedInImplemented"])]:
                fail("`%s` is a proposal-era heading; an implemented note states what is (fold it into `## %s` or `## %s`)"
                     % (heading, h["decision"], h["consequences"]))
        has_section = "## " + h["alternatives"] in h2s
        has_grandfather = GRANDFATHER in body
        if has_section and has_grandfather:
            fail("carries both `## %s` and the grandfather comment; drop the comment" % h["alternatives"])
        if not has_section and not has_grandfather:
            fail("missing `## %s`" % h["alternatives"])
        if has_grandfather and note["date"] >= config["formatAdopted"]:
            fail("the grandfather comment is only valid for notes dated before %s" % config["formatAdopted"])


# ---------- bilingual pairs ----------

def sections(text):
    out = [{"key": "(preamble)", "level": 0, "lines": []}]
    in_fence = False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else re.match(r"^(#{1,6}) +(.*)$", line)
        if m is not None:
            out.append({"key": line.rstrip(), "level": len(m.group(1)), "lines": []})
        out[-1]["lines"].append(line)
    return [{"key": s["key"], "level": s["level"], "hash": sha256("\n".join(s["lines"]))[:16]} for s in out]


def sidecar_of(rel):
    return rel[: -len(".md")] + ".i18n.json"


def counterpart_of(rel, lang):
    return rel[: -len(".md")] + "." + lang + ".md"


def compute_record(base_dir, rel, primary, langs):
    """Compute the consistency record for a group, or the reasons it cannot be recorded."""
    errors = []
    primary_text = read_text(os.path.join(base_dir, rel))
    base = sections(primary_text)
    sides = {primary: base}
    primary_lines = primary_text.split("\n")

    def levels(secs):
        return ",".join(str(s["level"]) for s in secs)

    for lang in langs:
        crel = counterpart_of(rel, lang)
        if not os.path.exists(os.path.join(base_dir, crel)):
            errors.append("%s — missing %s counterpart" % (crel, lang))
            continue
        text = read_text(os.path.join(base_dir, crel))
        lines = text.split("\n")
        if not (line_at(lines, 0) or "").startswith("# Agent Note: "):
            errors.append("%s — line 1 must start with `# Agent Note: `" % crel)
        if line_at(lines, 2) != line_at(primary_lines, 2):
            errors.append("%s — line 3 must repeat the primary status line verbatim" % crel)
        secs = sections(text)
        if levels(secs) != levels(base):
            errors.append("%s — heading structure differs from %s (levels %s vs %s)" % (crel, rel, levels(base), levels(secs)))
            continue
        sides[lang] = secs
    if errors:
        return None, errors
    rows = []
    for i, s in enumerate(base):
        row = {"key": s["key"]}
        for lang in [primary] + list(langs):
            row[lang] = sides[lang][i]["hash"]
        rows.append(row)
    return {"version": 1, "sections": rows}, errors


def render_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def check_pairing(notes_dir, notes, config, errors):
    primaries = {n["rel"] for n in notes}
    for lifecycle in LIFECYCLES:
        if not os.path.exists(os.path.join(notes_dir, lifecycle)):
            continue
        for cls in config["classes"]:
            class_dir = os.path.join(notes_dir, lifecycle, cls)
            if not os.path.exists(class_dir):
                continue
            for name, _ in listing(class_dir):
                rel = "%s/%s/%s" % (lifecycle, cls, name)
                lang = counterpart_language_of(name, config) if name.endswith(".md") else None
                if lang is not None and rel[: -len("." + lang + ".md")] + ".md" not in primaries:
                    errors.append("pairing: %s — counterpart has no primary note" % rel)
                elif name.endswith(".i18n.json") and rel[: -len(".i18n.json")] + ".md" not in primaries:
                    errors.append("pairing: %s — sidecar has no primary note" % rel)
    if not config["langs"]:
        return
    for note in notes:
        record, group_errors = compute_record(notes_dir, note["rel"], config["primary"], config["langs"])
        errors.extend("pairing: " + e for e in group_errors)
        srel = sidecar_of(note["rel"])
        if not os.path.exists(os.path.join(notes_dir, srel)):
            errors.append("pairing: %s — missing consistency sidecar; run `pair --write %s` after syncing the counterpart" % (srel, note["rel"]))
            continue
        if record is None:
            continue
        recorded = read_text(os.path.join(notes_dir, srel))
        if recorded == render_json(record):
            continue
        try:
            parsed = json.loads(recorded)
        except ValueError:
            parsed = None  # An unparseable sidecar is reported as a whole-file mismatch below.
        rows = parsed["sections"] if isinstance(parsed, dict) and isinstance(parsed.get("sections"), list) else []
        changed = ["%d:%s" % (i, row["key"]) for i, row in enumerate(record["sections"])
                   if i >= len(rows) or compact(rows[i]) != compact(row)]
        detail = "sections " + " | ".join(changed) if changed and len(rows) == len(record["sections"]) else "section list"
        errors.append("pairing: %s — out of date (%s); sync the counterpart, then run `pair --write %s`" % (srel, detail, note["rel"]))


def write_pairs(notes_dir, notes, config, targets, all_notes):
    if not config["langs"]:
        raise UsageError("pair: no counterpartLanguages configured")
    by_rel = {n["rel"]: n for n in notes}
    selected = list(notes) if all_notes else []
    for target in targets:
        rel = target.replace("\\", "/")
        if rel.startswith("./"):
            rel = rel[2:]
        if rel not in by_rel:
            raise UsageError("pair: %s is not an active primary note path relative to the notes directory" % target)
        selected.append(by_rel[rel])
    errors = []
    for note in selected:
        record, group_errors = compute_record(notes_dir, note["rel"], config["primary"], config["langs"])
        errors.extend("pairing: " + e for e in group_errors)
        if record is not None:
            with open(os.path.join(notes_dir, sidecar_of(note["rel"])), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(render_json(record))
    return errors


# ---------- archive ----------

def parse_manifest(content):
    try:
        value = json.loads(content)
    except ValueError:
        raise ValueError("not valid JSON")  # Parser wording differs across runtimes.
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    if sorted(value.keys()) != ["files", "version"]:
        raise ValueError('expected exactly the fields "version" and "files"')
    if value["version"] != 1 or isinstance(value["version"], bool):
        raise ValueError("unsupported manifest version (expected 1)")
    if not isinstance(value["files"], dict):
        raise ValueError('"files" must be an object')
    for path, digest in value["files"].items():
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("invalid content hash for %s" % path)
    return dict(value["files"])


def git(cwd, args):
    try:
        result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return False, ""
    return result.returncode == 0, result.stdout


def baseline_manifest(archive_dir):
    """Read the manifest at the baseline commit; an unborn default HEAD counts as an empty baseline."""
    explicit = os.environ.get("AGENT_NOTES_BASE_REF")
    ref = explicit if explicit is not None else "HEAD"
    if not git(archive_dir, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"])[0]:
        return {} if explicit is None else "cannot resolve baseline %s" % json.dumps(ref)
    ok, out = git(archive_dir, ["show", ref + ":./manifest.json"])
    if not ok:
        return {}
    try:
        return parse_manifest(out)
    except ValueError as error:
        return "baseline manifest is invalid: %s" % error


def check_archive_metadata(path, text, note_date):
    lines = text.split("\n")
    status = next((i for i, l in enumerate(lines) if l.startswith("Status:")), -1)
    errors = []
    if status < 0 or lines[status] != "Status: implemented":
        errors.append("archive: %s — requires `Status: implemented`" % path)
    nxt = "" if status < 0 else (line_at(lines, status + 1) or "")
    m = re.match(r"^Archived: (\d{4}-\d{2}-\d{2})$", nxt)
    if m is None or not valid_date(m.group(1)):
        errors.append("archive: %s — requires `Archived: YYYY-MM-DD` with a real date immediately after the status line" % path)
        return errors, None
    if m.group(1) < note_date:
        errors.append("archive: %s — archive date %s predates the note filename" % (path, m.group(1)))
    return errors, m.group(1)


def check_archive(notes_dir, config, write, errors):
    archive_dir = os.path.join(notes_dir, ARCHIVE)
    if not os.path.exists(archive_dir):
        errors.append("archive: %s/ — required folder is missing" % ARCHIVE)
        return 0
    if not os.path.exists(os.path.join(archive_dir, "AGENTS.md")):
        errors.append("archive: %s/AGENTS.md — required instructions file is missing" % ARCHIVE)
    artifacts = {}
    for name, is_dir in listing(archive_dir):
        if not is_dir:
            if name not in ARCHIVE_ROOT_FILES:
                errors.append("archive: %s/%s — unexpected root file" % (ARCHIVE, name))
            continue
        if name not in config["classes"]:
            errors.append("archive: %s/%s/ — unknown class folder" % (ARCHIVE, name))
            continue
        for child, child_is_dir in listing(os.path.join(archive_dir, name)):
            if child == ".gitkeep":
                continue
            rel = name + "/" + child
            if child_is_dir:
                errors.append("archive: %s — class folders hold files only" % rel)
            else:
                with open(os.path.join(archive_dir, rel), "rb") as handle:
                    artifacts[rel] = handle.read()
    for cls in config["classes"]:
        if not os.path.exists(os.path.join(archive_dir, cls)):
            errors.append("archive: %s/%s/ — required class folder is missing" % (ARCHIVE, cls))

    # A `foo.xx.md` file is a counterpart only when `foo.i18n.json` exists beside it.
    sidecar_stems = {r[: -len(".i18n.json")] for r in artifacts if r.endswith(".i18n.json")}
    groups = {}
    for rel in sorted(artifacts):
        lang = None
        if rel.endswith(".i18n.json"):
            stem = rel[: -len(".i18n.json")]
        elif rel.endswith(".md"):
            m = re.match(r"^(.*)\.([a-z]{2,3}(?:-[A-Za-z0-9]+)?)\.md$", rel)
            if m is not None and m.group(1) in sidecar_stems:
                stem, lang = m.group(1), m.group(2)
            else:
                stem = rel[: -len(".md")]
        else:
            errors.append("archive: %s — unexpected file; archives hold notes, counterparts, and sidecars only" % rel)
            continue
        base = stem.split("/")[1]
        if not NOTE_NAME.match(base + ".md") or not valid_date(base[:10]):
            errors.append("archive: %s — expected {class}/yyyy-mm-dd-topic.md (or a counterpart/sidecar of one)" % rel)
            continue
        group = groups.setdefault(stem, {"primary": False, "langs": [], "sidecar": False})
        if rel.endswith(".i18n.json"):
            group["sidecar"] = True
        elif lang is None:
            group["primary"] = True
        else:
            group["langs"].append(lang)
    for stem in sorted(groups):
        group = groups[stem]
        if not group["primary"]:
            errors.append("archive: %s.md — missing primary note for archived counterpart or sidecar" % stem)
            continue
        if group["sidecar"] and not group["langs"]:
            errors.append("archive: %s.i18n.json — sidecar has no archived counterpart" % stem)
            continue
        note_date = stem.split("/")[1][:10]
        langs = sorted(group["langs"])
        dates = set()
        for rel in [stem + ".md"] + ["%s.%s.md" % (stem, l) for l in langs]:
            text = artifacts[rel].decode("utf-8", errors="replace").replace("\r\n", "\n")
            meta_errors, date = check_archive_metadata(rel, text, note_date)
            errors.extend(meta_errors)
            if date is not None:
                dates.add(date)
        if len(dates) > 1:
            errors.append("archive: %s — archive dates differ across languages" % stem)
        if group["sidecar"]:
            record, pair_errors = compute_record(archive_dir, stem + ".md", config["primary"], langs)
            errors.extend("archive: " + e for e in pair_errors)
            if record is not None and read_text(os.path.join(archive_dir, stem + ".i18n.json")) != render_json(record):
                errors.append("archive: %s.i18n.json — sidecar must match the archived contents (run `pair --write` on the active note after adding the Archived line, then move the group)" % stem)

    manifest_path = os.path.join(archive_dir, "manifest.json")
    files = {}
    if os.path.exists(manifest_path):
        try:
            files = parse_manifest(read_text(manifest_path))
        except ValueError as error:
            errors.append("archive: manifest.json — %s" % error)
    elif not write:
        errors.append("archive: manifest.json — missing; run `seal` to create it")
    baseline = baseline_manifest(archive_dir)
    if isinstance(baseline, str):
        errors.append("archive: manifest.json — " + baseline)
    else:
        for path in sorted(baseline):
            if path not in files:
                errors.append("archive: %s — seal removed from manifest.json" % path)
            elif files[path] != baseline[path]:
                errors.append("archive: %s — seal changed in manifest.json" % path)
    for path in sorted(files):
        if path not in artifacts:
            errors.append("archive: %s — sealed file is missing" % path)
        elif "sha256:" + sha256(artifacts[path]) != files[path]:
            errors.append("archive: %s — sealed file changed; archived notes are frozen" % path)
    added = sorted(p for p in artifacts if p not in files)
    if not write:
        for path in added:
            errors.append("archive: %s — not sealed; run `seal`" % path)
        return 0
    if errors:
        return 0
    merged = dict(files)
    for path in added:
        merged[path] = "sha256:" + sha256(artifacts[path])
    rendered = render_json({"version": 1, "files": {k: merged[k] for k in sorted(merged)}})
    current = read_text(manifest_path) if os.path.exists(manifest_path) else None
    if current != rendered:
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    return len(added)


# ---------- prose lint ----------

def lint_baseline(repo_root):
    """Return the baseline ref, or None for an unborn default HEAD (everything counts as new)."""
    explicit = os.environ.get("AGENT_NOTES_BASE_REF")
    ref = explicit if explicit is not None else "HEAD"
    if git(repo_root, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"])[0]:
        return ref
    if explicit is not None:
        raise UsageError("lint: cannot resolve baseline %s" % json.dumps(ref))
    return None


def changed_note_files(repo_root, notes_dir, ref):
    """Active note files in any language that differ from the baseline or are untracked."""
    rel_notes = os.path.relpath(notes_dir, repo_root).replace(os.sep, "/")
    if ref is None:
        out = git(repo_root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", rel_notes])[1]
    else:
        out = git(repo_root, ["diff", "-z", "--name-only", "--relative", ref, "--", rel_notes])[1]
        out += git(repo_root, ["ls-files", "-z", "--others", "--exclude-standard", "--", rel_notes])[1]
    files = set()
    for path in out.split("\0"):
        if not path.startswith(rel_notes + "/"):
            continue
        rel = path[len(rel_notes) + 1:]
        segs = rel.split("/")
        if len(segs) == 3 and segs[0] in LIFECYCLES and rel.endswith(".md") and os.path.isfile(os.path.join(notes_dir, rel)):
            files.add(rel)
    return files


def lint_file(repo_root, notes_dir, rel, ref):
    hits = []
    path = os.path.join(notes_dir, rel)
    in_fence = False
    for number, line in enumerate(read_text(path).split("\n"), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for rule, pattern in PROSE_PROBES:
            m = re.search(pattern, line, re.I)
            if m is not None:
                hits.append("%s:%d: [%s] %s" % (rel, number, rule, m.group(0)))
        if re.search(SUPERSEDES, line, re.I) is None:
            continue
        for target in re.findall(NOTE_LINK, line):
            linked = os.path.normpath(os.path.join(os.path.dirname(path), target))
            repo_rel = os.path.relpath(linked, repo_root).replace(os.sep, "/")
            if ref is None or not git(repo_root, ["cat-file", "-e", "%s:./%s" % (ref, repo_rel)])[0]:
                hits.append("%s:%d: [draft-supersession] %s is absent from the baseline" % (rel, number, target))
    return hits


def lint(repo_root, notes_dir, config, targets, all_notes):
    """Return report lines: prose-probe hits in changed (or named) notes, both languages."""
    ref = lint_baseline(repo_root)
    if all_notes or targets:
        primaries = [n["rel"] for n in walk_tree(repo_root, notes_dir, config, [])] if all_notes else targets
        files = set()
        for rel in primaries:
            files.add(rel)
            if counterpart_language_of(os.path.basename(rel), config) is None:
                files.update(counterpart_of(rel, lang) for lang in config["langs"])
        files = {f for f in files if os.path.isfile(os.path.join(notes_dir, f))}
    else:
        files = changed_note_files(repo_root, notes_dir, ref)
    hits = []
    for rel in sorted(files):
        hits.extend(lint_file(repo_root, notes_dir, rel, ref))
    if not hits:
        return ["agent-notes: lint found no prose candidates in %d file(s)." % len(files)]
    return ["agent-notes: lint found %d prose candidate(s) in %d file(s); these are not violations. Judge each "
            "with the prose checks of the agent-notes skill, rewrite what fails, and report a keep or rewrite "
            "verdict for every hit:" % (len(hits), len(files))] + ["  " + h for h in hits]


# ---------- CLI ----------

def main(argv):
    args = list(argv)
    command = args.pop(0) if args else None
    repo_root = os.getcwd()
    notes_dir = None
    write_flag = False
    all_notes = False
    targets = []
    while args:
        arg = args.pop(0)
        if arg in ("--repo-root", "--notes-dir"):
            if not args:
                raise UsageError("%s needs a value" % arg)
            value = os.path.abspath(args.pop(0))
            if arg == "--repo-root":
                repo_root = value
            else:
                notes_dir = value
        elif arg == "--write":
            write_flag = True
        elif arg == "--all":
            all_notes = True
        elif arg.startswith("--"):
            raise UsageError("unknown option %s" % arg)
        else:
            targets.append(arg)
    directory = notes_dir or os.path.join(repo_root, ".agents", "notes")
    if not os.path.exists(directory):
        raise UsageError("notes directory %s does not exist" % directory)
    config = load_config(directory)
    errors = []

    if command == "pair":
        if not write_flag or all_notes == (len(targets) > 0):
            raise UsageError("usage: pair --write (--all | NOTE...)")
        notes = walk_tree(repo_root, directory, config, [])
        errors.extend(write_pairs(directory, notes, config, targets, all_notes))
        if not errors:
            count = len(notes) if all_notes else len(targets)
            print("agent-notes: re-recorded %d pair(s); review the sidecar diff as your confirmation that both sides say the same thing." % count)
            return 0
    elif command in ("check", "seal"):
        if write_flag or all_notes or targets:
            raise UsageError("usage: %s [--repo-root DIR] [--notes-dir DIR]" % command)
        notes = walk_tree(repo_root, directory, config, errors)
        check_format(directory, notes, config, errors)
        check_pairing(directory, notes, config, errors)
        sealed = check_archive(directory, config, command == "seal", errors)
        if not errors:
            if command == "seal":
                print("agent-notes: sealed %d new archived file(s); existing seals unchanged." % sealed)
            else:
                print("agent-notes: %d active note(s) conform." % len(notes))
                if config["proseLint"]:
                    print("\n".join(lint(repo_root, directory, config, [], False)))
            return 0
    elif command == "lint":
        if write_flag or (all_notes and targets):
            raise UsageError("usage: lint [NOTE... | --all] [--repo-root DIR] [--notes-dir DIR]")
        print("\n".join(lint(repo_root, directory, config, targets, all_notes)))
        return 0
    else:
        raise UsageError("usage: agent-notes (check | seal | pair --write (--all | NOTE...) | lint [NOTE... | --all]) [--repo-root DIR] [--notes-dir DIR]")
    print("agent-notes: violations found:", file=sys.stderr)
    for error in errors:
        print("  " + error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    # Match the Node gate byte for byte: UTF-8 and bare LF on every platform.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        sys.exit(main(sys.argv[1:]))
    except UsageError as error:
        print("agent-notes: %s" % error, file=sys.stderr)
        sys.exit(2)
