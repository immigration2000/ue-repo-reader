"""Real CLI cold/warm/disabled cache equivalence using an existing local UE project."""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


if __name__ == "__main__":
    main()
