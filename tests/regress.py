#!/usr/bin/env python3
"""Regression test: build digests of pinned commits and compare them with tests/fixtures.json.

  python tests/regress.py                        # all fixtures (clones into tests/.cache/)
  python tests/regress.py --only eg ar           # some fixtures
  python tests/regress.py --only assets          # small assets with independent editor oracles
  python tests/regress.py --repo eg=D:/clones/ExtractionGame_Fin   # reuse a local clone (must be at the pinned SHA)

Exit code 0 = all passed, 1 = a check failed, 2 = a digest could not be built.

Every asset must decode cleanly and completely unless the fixture pins the exception:
  known_issues[collection][path] = [[stage, context, message], ...]  exact set of accepted issues
  blueprint_nodes[path] = [nodes_ok, nodes_total]                    exact per-Blueprint coverage
  level_blueprints[path] = [nodes_ok, nodes_total, level_bp_status]  exact per-map Level Blueprint
blueprint_nodes/level_blueprints are exhaustive once present (every rendered asset listed), and
parse_status is derived from those pins, so nothing grants blanket permission for future issues.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGEST = ROOT / "scripts" / "ue_repo_digest.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures.json"
CACHE = Path(__file__).resolve().parent / ".cache"
COVERAGE = re.compile(r"Coverage: (\d+) Blueprints rendered, (\d+) failed; graph nodes decoded (\d+)/(\d+)")


def git_head(path: Path) -> str:
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout.strip()


def build(name: str, fx: dict, local: Path | None, out: Path, log: Path) -> tuple[bool, str]:
    if local:
        head = git_head(local)
        if head and head != fx["sha"]:
            return False, f"local clone {local} is at {head[:10]}, fixture needs {fx['sha'][:10]}"
        cmd = [sys.executable, str(DIGEST), str(local), "--out", str(out)]
    else:
        cmd = [sys.executable, str(DIGEST), fx["url"], "--ref", fx["sha"], "--workdir", str(CACHE / name), "--out", str(out)]
    if fx.get("best_effort"):
        cmd.append("--best-effort")
    t = time.time()
    with log.open("w", encoding="utf-8") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                            env=dict(os.environ, PYTHONIOENCODING="utf-8:replace")).returncode
    secs = time.time() - t
    if rc != 0 or not (out / "INDEX.md").is_file():
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        return False, f"digest failed (exit {rc}): " + " | ".join(tail)
    return True, f"{secs:.0f}s"


def issue_signature(issue) -> tuple[str, str, str]:
    """Identity of one parse issue, compared exactly: (stage, context, message).

    Most stages record a game path or a saved object name, which is the same on every machine.
    Some do not: `external_actor` records the package's path inside the clone, so its context
    moves with the clone location (tests/.cache/<name> vs. a --repo checkout). Pin an issue only
    when its context is machine-independent; for a clone-path context, fix the cause or pin the
    asset's node/Level Blueprint counts instead of the issue text. The pins in fixtures.json are
    game paths and saved export names only.
    """
    if not isinstance(issue, dict):
        return ("?", "?", repr(issue))
    return (str(issue.get("stage")), str(issue.get("context")), str(issue.get("message")))


def compare_issues(gp: str, reported, pinned) -> list[str]:
    """Exact multiset comparison of reported vs. pinned issues.

    A new, changed or duplicated issue fails even inside an asset that is already allowed to
    have known issues; a pinned issue that stopped being reported fails too, so a stale pin
    can never silently keep granting permission.
    """
    errors = []
    want = Counter()
    for sig in pinned or []:
        if not isinstance(sig, (list, tuple)) or len(sig) != 3:
            errors.append(f"{gp}: malformed pinned issue {sig!r} (expected [stage, context, message])")
            continue
        want[tuple(str(f) for f in sig)] += 1
    got = Counter(issue_signature(i) for i in reported or [])
    for sig, n in sorted((got - want).items()):
        errors.append(f"{gp}: unexpected parse issue (×{n}) " + " · ".join(sig))
    for sig, n in sorted((want - got).items()):
        errors.append(f"{gp}: pinned parse issue no longer reported (×{n}) " + " · ".join(sig))
    return errors


def check(fx: dict, out: Path) -> list[str]:
    errors = []
    index = (out / "INDEX.md").read_text(encoding="utf-8")
    m = COVERAGE.search(index)
    if not m:
        return ["INDEX.md has no Coverage line"]
    bps, failed, ok, total = map(int, m.groups())
    exp = fx["expect"]
    if bps != exp["blueprints"]:
        errors.append(f"blueprints {bps} != expected {exp['blueprints']}")
    if failed != 0:
        errors.append(f"{failed} Blueprints failed")
    if ok != exp.get("nodes_ok", total):  # nodes_ok: pinned partial coverage for engines older than supported
        errors.append(f"nodes decoded {ok}/{total} (expected {exp.get('nodes_ok', total)}/{total})")
    if total != exp["nodes"]:
        errors.append(f"node total {total} != expected {exp['nodes']}")
    try:
        digest = json.loads((out / "digest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return errors + [f"digest.json could not be read: {e}"]
    if "navigation" in digest:
        documents = (digest["navigation"] or {}).get("documents") or {}
        expected_docs = {folder + gp + ".md" for folder, group in
                         (("blueprints", "blueprints"), ("data", "data_assets"), ("maps", "maps_detail"))
                         for gp in (digest.get(group) or {})}
        if (digest.get("cpp") or {}).get("classes"):
            expected_docs.add("cpp/CLASSES.md")
        if set(documents) != expected_docs:
            errors.append("navigation does not cover every rendered asset/C++ document")
        if {r.get("rank") for r in documents.values()} != set(range(1, len(documents) + 1)):
            errors.append("navigation ranks are not a complete sequence")
        if len(index.encode("utf-8")) > 9_000 or not (out / "CATALOG.md").is_file():
            errors.append("missing full catalog or INDEX exceeds its 9KB budget")
        for doc, record in documents.items():
            path = out / doc
            if not path.is_file() or "Reading context:" not in path.read_text(encoding="utf-8")[:2500]:
                errors.append(f"{doc}: missing document/context header")
            if (set(record.get("incoming") or ()) | set(record.get("outgoing") or ())) - documents.keys():
                errors.append(f"{doc}: unresolved navigation link")
    support = digest.get("source", {}).get("project_support", {})
    for field, expected in exp.get("project_support", {}).items():
        if support.get(field) != expected or type(support.get(field)) is not type(expected):
            errors.append(f"project support {field} {support.get(field)!r} != expected {expected!r}")
    for key in ("failures", "data_failures", "map_failures"):
        if not isinstance(digest.get(key), dict):
            errors.append(f"digest.json: missing or invalid {key}")
            continue
        if digest.get(key):
            errors.append(f"{key}: {len(digest[key])} assets failed")
    if "allow_issues" in exp:
        errors.append("fixture uses the removed blanket allow_issues flag; pin known_issues/"
                      "blueprint_nodes/level_blueprints per asset instead")
    known_issues = exp.get("known_issues") or {}
    pinned_nodes = exp.get("blueprint_nodes") or {}
    pinned_levels = exp.get("level_blueprints") or {}
    if pinned_nodes:  # the per-asset pins and the repo-wide Coverage line must describe the same digest
        pin = (sum(c[0] for c in pinned_nodes.values()), sum(c[1] for c in pinned_nodes.values()))
        want = (exp.get("nodes_ok", exp.get("nodes")), exp.get("nodes"))
        if pin != want:
            errors.append(f"fixture inconsistent: pinned Blueprint nodes sum to {pin[0]}/{pin[1]}, "
                          f"expected totals {want[0]}/{want[1]}")
    for key in ("blueprints", "data_assets", "maps_detail"):
        if not isinstance(digest.get(key), dict):
            errors.append(f"digest.json: missing or invalid {key}")
            continue
        allowed = known_issues.get(key) or {}
        for gp in sorted(set(allowed) - set(digest[key])):
            errors.append(f"{gp}: known issues pinned for an asset that is no longer rendered in {key}")
        # A pin set is exhaustive once used: every asset of that kind is listed, so a node total
        # moving between assets cannot keep the repo-wide Coverage line unchanged.
        exhaustive, field = ((pinned_nodes, "blueprint_nodes") if key == "blueprints" else
                             (pinned_levels, "level_blueprints") if key == "maps_detail" else ({}, ""))
        if exhaustive:
            for gp in sorted(set(exhaustive) ^ set(digest[key])):
                side = "no longer rendered" if gp in exhaustive else f"not pinned in {field}"
                errors.append(f"{gp}: {field} must cover every rendered {key} entry exactly ({side})")
        for gp, summary in digest[key].items():
            if "issues" not in summary or "parse_status" not in summary:
                errors.append(f"{gp}: missing structured parse status/issues")
            errors += compare_issues(gp, summary.get("issues"), allowed.get(gp))
            if summary.get("enum_resolution", {}).get("unresolved"):
                errors.append(f"{gp}: unresolved enum labels")
            partial_nodes = False
            if key == "blueprints":
                got = (summary.get("nodes_ok"), summary.get("nodes_total"))
                if not all(isinstance(v, int) for v in got):
                    errors.append(f"{gp}: missing node counts {got}")
                else:
                    # Unpinned Blueprints must decode every node; pinned ones must match exactly, so a
                    # coverage loss or a node moving between assets cannot hide inside the repo totals.
                    want = tuple(pinned_nodes[gp]) if gp in pinned_nodes else (got[1], got[1])
                    if got != want:
                        errors.append(f"{gp}: nodes decoded {got[0]}/{got[1]} != pinned {want[0]}/{want[1]}")
                    partial_nodes = want[0] < want[1]
            if key == "maps_detail":
                nodes = summary.get("level_bp_nodes")
                status = summary.get("level_bp_status")
                if not (isinstance(nodes, (list, tuple)) and len(nodes) == 2):
                    errors.append(f"{gp}: Level Blueprint not decoded ({nodes}, {status})")
                else:
                    got = (nodes[0], nodes[1], status)
                    want = tuple(pinned_levels[gp]) if gp in pinned_levels else (nodes[1], nodes[1], "ok")
                    if got != want:
                        errors.append(f"{gp}: Level Blueprint {got[0]}/{got[1]} {got[2]} != pinned "
                                      f"{want[0]}/{want[1]} {want[2]}")
                if any(summary.get(k) for k in ("external_actor_errors", "external_actors_truncated", "external_actors_not_downloaded")):
                    errors.append(f"{gp}: external actors incomplete")
            # parse_status is derived, never granted: "partial" exactly when a known issue or a pinned
            # incomplete node count explains it. A missing or null status is neither a confirmed
            # success nor a pinned partial state, so it fails like any other wrong value.
            want_status = "partial" if (allowed.get(gp) or partial_nodes) else "ok"
            if summary.get("parse_status") != want_status:
                errors.append(f"{gp}: parse status {summary.get('parse_status')!r} != expected {want_status!r}")
    if (digest.get("lfs") or {}).get("failed"):
        errors.append(f"{digest['lfs']['failed']} LFS downloads failed")
    for field, collection in (("data_assets", "data_assets"), ("maps", "maps_detail")):
        if field in exp and len(digest.get(collection) or {}) != exp[field]:
            errors.append(f"{field} {len(digest.get(collection) or {})} != expected {exp[field]}")
    if "external_actors" in exp:
        count = sum(s.get("external_actors", 0) for s in (digest.get("maps_detail") or {}).values())
        if count != exp["external_actors"]:
            errors.append(f"external actors {count} != expected {exp['external_actors']}")
    for check in fx.get("summary_checks", []):
        summary = (digest.get(check["collection"]) or {}).get(check["path"], {})
        for field, expected in check["fields"].items():
            if field not in summary or summary[field] != expected:
                errors.append(f"{check['path']}: {field} {summary.get(field)!r} != expected {expected!r}")
    for c in fx.get("checks", []):
        f = out / c["file"]
        if not f.is_file():
            errors.append(f"[{c.get('bug', '?')}] missing file {c['file']}")
            continue
        text = f.read_text(encoding="utf-8")
        for s in c.get("must_contain", []):
            if s not in text:
                errors.append(f"[{c.get('bug', '?')}] {c['file']}: missing {s!r}")
        for s in c.get("must_not_contain", []):
            if s in text:
                errors.append(f"[{c.get('bug', '?')}] {c['file']}: still contains {s!r}")
        for pat in c.get("must_not_match", []):
            if re.search(pat, text, re.M):
                errors.append(f"[{c.get('bug', '?')}] {c['file']}: matches /{pat}/")
    return errors


def _utf8_stdio() -> None:
    """Windows consoles/pipes default to the ANSI code page (cp949 on Korean systems): never crash on output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> int:
    _utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="fixture names to run (eg, ar, ves, assets)")
    ap.add_argument("--repo", action="append", default=[], help="NAME=PATH: use an existing local clone")
    ap.add_argument("--keep", action="store_true", help="keep digests in tests/.cache/<name>_digest (always kept)")
    a = ap.parse_args()
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    unknown = set(a.only or []) - set(fixtures) - {"assets"}
    if unknown:
        ap.error("unknown fixtures: " + ", ".join(sorted(unknown)))
    local = dict(r.split("=", 1) for r in a.repo)
    CACHE.mkdir(exist_ok=True)
    unit = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "unit_tests.py")],
                          env=dict(os.environ, PYTHONIOENCODING="utf-8:replace"))
    worst = 1 if unit.returncode else 0
    if not a.only or "assets" in a.only:
        assets = subprocess.run([sys.executable, str(ROOT / "tests" / "asset_regress.py")],
                                env=dict(os.environ, PYTHONIOENCODING="utf-8:replace"))
        worst = max(worst, assets.returncode)
    for name, fx in fixtures.items():
        if a.only and name not in a.only:
            continue
        out = CACHE / f"{name}_digest"
        ok, info = build(name, fx, Path(local[name]) if name in local else None, out, CACHE / f"{name}.log")
        if not ok:
            print(f"FAIL  {name}: {info}")
            worst = max(worst, 2)
            continue
        errors = check(fx, out)
        if name == "eg":
            from editor_oracle_regress import check_eg, check_eg_declarations
            try:
                graph, full = check_eg(Path(local[name]) if name in local else CACHE / name, fx["sha"])
                print(f"PASS native eg BFL_Util: {graph['checked']} graph observations; {len(full['unavailable'])} exact declared gaps")
                for case, graph, full in check_eg_declarations(Path(local[name]) if name in local else CACHE / name, fx["sha"]):
                    print(f"PASS native eg {case}: {graph['checked']} graph observations; {len(full['unavailable'])} exact declared gaps")
                from editor_state_evidence import check_eg_loaded_state
                print(f"PASS eg loaded-state evidence: {check_eg_loaded_state(Path(local[name]) if name in local else CACHE / name, fx['sha'])}")
            except Exception as error:
                errors.append(f"native editor oracle: {type(error).__name__}: {error}")
        if name == "ar":
            from editor_state_evidence import check_ar_saved_membership
            try:
                count = check_ar_saved_membership(Path(local[name]) if name in local else CACHE / name, fx["sha"])
                print(f"PASS ar saved Nodes evidence: {count} members; unlisted export preserved separately")
            except Exception as error:
                errors.append(f"saved graph membership evidence: {type(error).__name__}: {error}")
        print(f"{'PASS' if not errors else 'FAIL'}  {name} ({info}) — digest: {out}")
        for e in errors:
            print(f"      - {e}")
        if errors:
            worst = max(worst, 1)
    return worst


if __name__ == "__main__":
    sys.exit(main())
