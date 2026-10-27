#!/usr/bin/env python3
"""Regression test: build digests of pinned commits and compare them with tests/fixtures.json.

  python tests/regress.py                        # all fixtures (clones into tests/.cache/)
  python tests/regress.py --only eg ar           # some fixtures
  python tests/regress.py --repo eg=D:/clones/ExtractionGame_Fin   # reuse a local clone (must be at the pinned SHA)

Exit code 0 = all passed, 1 = a check failed, 2 = a digest could not be built.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
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
    t = time.time()
    with log.open("w", encoding="utf-8") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                            env=dict(os.environ, PYTHONIOENCODING="utf-8:replace")).returncode
    secs = time.time() - t
    if rc != 0 or not (out / "INDEX.md").is_file():
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        return False, f"digest failed (exit {rc}): " + " | ".join(tail)
    return True, f"{secs:.0f}s"


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
    if ok != total:
        errors.append(f"nodes decoded {ok}/{total} (some unreadable)")
    if total != exp["nodes"]:
        errors.append(f"node total {total} != expected {exp['nodes']}")
    try:
        digest = json.loads((out / "digest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return errors + [f"digest.json could not be read: {e}"]
    for key in ("failures", "data_failures", "map_failures"):
        if not isinstance(digest.get(key), dict):
            errors.append(f"digest.json: missing or invalid {key}")
            continue
        if digest.get(key):
            errors.append(f"{key}: {len(digest[key])} assets failed")
    for key in ("blueprints", "data_assets", "maps_detail"):
        if not isinstance(digest.get(key), dict):
            errors.append(f"digest.json: missing or invalid {key}")
            continue
        for gp, summary in digest[key].items():
            if "issues" not in summary or "parse_status" not in summary:
                errors.append(f"{gp}: missing structured parse status/issues")
            if summary.get("issues"):
                errors.append(f"{gp}: {len(summary['issues'])} parse/render issues")
            if summary.get("parse_status") not in (None, "ok"):
                errors.append(f"{gp}: parse status {summary['parse_status']}")
            if key == "maps_detail":
                nodes = summary.get("level_bp_nodes")
                if nodes is None or nodes[0] != nodes[1] or summary.get("level_bp_status") != "ok":
                    errors.append(f"{gp}: Level Blueprint incomplete ({nodes}, {summary.get('level_bp_status')})")
                if any(summary.get(k) for k in ("external_actor_errors", "external_actors_truncated", "external_actors_not_downloaded")):
                    errors.append(f"{gp}: external actors incomplete")
    if (digest.get("lfs") or {}).get("failed"):
        errors.append(f"{digest['lfs']['failed']} LFS downloads failed")
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
    ap.add_argument("--only", nargs="*", help="fixture names to run")
    ap.add_argument("--repo", action="append", default=[], help="NAME=PATH: use an existing local clone")
    ap.add_argument("--keep", action="store_true", help="keep digests in tests/.cache/<name>_digest (always kept)")
    a = ap.parse_args()
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    local = dict(r.split("=", 1) for r in a.repo)
    CACHE.mkdir(exist_ok=True)
    unit = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "unit_tests.py")],
                          env=dict(os.environ, PYTHONIOENCODING="utf-8:replace"))
    worst = 1 if unit.returncode else 0
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
        print(f"{'PASS' if not errors else 'FAIL'}  {name} ({info}) — digest: {out}")
        for e in errors:
            print(f"      - {e}")
        if errors:
            worst = max(worst, 1)
    return worst


if __name__ == "__main__":
    sys.exit(main())
