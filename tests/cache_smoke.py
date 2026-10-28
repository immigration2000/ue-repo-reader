"""Real CLI cold/warm/disabled cache equivalence using an existing local UE project."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_changed_asset(base):
    from asset_regress import fetch_file
    manifest = json.loads((ROOT / "tests/asset_fixtures.json").read_text(encoding="utf-8"))
    fixture_cache = ROOT / "tests/.cache/asset-fixtures" / manifest["commit"]
    cases = {case["id"]: case for case in manifest["cases"]}
    project, out = base / "tiny-project", base / "tiny-out"
    content = project / "Content"
    content.mkdir(parents=True)
    (project / "Tiny.uproject").write_text("{}", encoding="utf-8")
    shutil.copyfile(fetch_file(manifest, manifest["license"], fixture_cache), project / "LICENSE")
    bp, data = content / "BP_Keys.uasset", content / "ST_LegacyText.uasset"
    shutil.copyfile(fetch_file(manifest, cases["pins-5.6"]["asset"], fixture_cache), bp)
    shutil.copyfile(fetch_file(manifest, cases["strings-4.27"]["asset"], fixture_cache), data)
    for phase, expected in (("cold", (0, 2, 2, 0)), ("warm", (2, 0, 0, 0)), ("changed", (1, 1, 1, 0))):
        if phase == "changed":
            shutil.copyfile(fetch_file(manifest, cases["pins-5.7"]["asset"], fixture_cache), bp)
        run = subprocess.run([sys.executable, str(ROOT / "scripts/ue_repo_digest.py"), str(project), "--out", str(out),
                              "--asset-cache-dir", str(base / "tiny-cache")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        assert run.returncode == 0, run.stderr
        match = re.search(r"\[cache\] hits=(\d+) misses=(\d+) writes=(\d+) errors=(\d+)", run.stderr)
        assert match and tuple(map(int, match.groups())) == expected, run.stderr
        digest = json.loads((out / "digest.json").read_text(encoding="utf-8"))
        summary = digest["blueprints"]["/Game/BP_Keys"]
        assert summary["nodes_ok"] == summary["nodes_total"] == 9
        assert summary["saved_with"].startswith("5.7" if phase == "changed" else "5.6")
        assert not digest["failures"] and not digest["data_failures"]
    print("PASS: replacing one real BP reparses only its graphs; untouched data stays cached (headers rescanned)", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="asset-smoke-", dir=ROOT / "tests/.cache") as tmp:
        base = Path(tmp)
        snapshots, counts = [], []
        for mode in ("cold", "warm", "disabled"):
            out = base / "out"
            cmd = [sys.executable, str(ROOT / "scripts/ue_repo_digest.py"), str(args.source.resolve()),
                   "--out", str(out), "--asset-cache-dir", str(base / "cache")]
            if mode == "disabled":
                cmd.append("--no-asset-cache")
            started = time.monotonic()
            run = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True,
                                 timeout=600, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            assert run.returncode == 0, run.stdout + run.stderr
            match = re.search(r"\[cache\] hits=(\d+) misses=(\d+) writes=(\d+) errors=(\d+)", run.stderr)
            counts.append(tuple(map(int, match.groups())) if match else None)
            snapshots.append({p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in out.rglob("*") if p.is_file()})
            print(f"{mode}: {time.monotonic() - started:.2f}s, cache={counts[-1]}, files={len(snapshots[-1])}", flush=True)
        for snapshot in snapshots[1:]:
            changed = [name for name in snapshots[0].keys() | snapshot.keys() if snapshots[0].get(name) != snapshot.get(name)]
            assert not changed, f"cache changed output: {changed}"
        assert counts[0] and counts[0][0] == 0 and counts[0][2] > 0, counts
        assert counts[1] and counts[1][0] > 0 and counts[1][2] == 0 and counts[1][3] == 0, counts
        print("PASS: every Markdown/JSON file is byte-identical (cold, warm, disabled)", flush=True)
        check_changed_asset(base)


if __name__ == "__main__":
    main()
