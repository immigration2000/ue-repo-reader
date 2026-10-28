"""Real CLI enum-only invalidation: cached dependent data gets new labels, never stale names."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "DeltaForce/Data"
GAME = "/Game/" + PACKAGE


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=ROOT / "tests/.cache/eg")
    args = ap.parse_args()
    fixture = json.loads((ROOT / "tests/fixtures.json").read_text(encoding="utf-8"))["eg"]
    head = subprocess.run(["git", "-C", str(args.repo), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()
    assert head == fixture["sha"], "use the pinned eg fixture from tests/regress.py"
    with tempfile.TemporaryDirectory(prefix="enum-공백 [값],-", dir=ROOT / "tests/.cache") as tmp:
        base = Path(tmp).resolve()
        project, out = base / "project", base / "out"
        for relative in ("Enum/E_Crates.uasset", "DataAsset/PDA_PlayerData.uasset", "DataAsset/DA_PlayerData.uasset"):
            target = project / "Content" / PACKAGE / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.repo / "Content" / PACKAGE / relative, target)
        (project / "Tiny.uproject").write_text("{}", encoding="utf-8")
        enum_file = project / "Content" / PACKAGE / "Enum/E_Crates.uasset"
        snapshots = []
        for phase, expected in (("cold", (0, 3, 3, 0)), ("warm", (3, 0, 0, 0)),
                                ("enum_changed", (2, 1, 1, 0)), ("enum_missing", (2, 0, 0, 0))):
            if phase == "enum_changed":
                old, new = b"GTIWeaponCrate", b"NEWWeaponCrate"
                data = enum_file.read_bytes()
                assert len(old) == len(new) and data.count(old) == 2
                enum_file.write_bytes(data.replace(old, new))  # valid same-length FString; original fixture untouched
            elif phase == "enum_missing":
                enum_file.unlink()
            run = subprocess.run([sys.executable, str(ROOT / "scripts/ue_repo_digest.py"), str(project),
                                  "--out", str(out), "--workers", "2", "--asset-cache-dir", str(base / "cache")],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            assert run.returncode == 0, run.stderr
            match = re.search(r"\[cache\] hits=(\d+) misses=(\d+) writes=(\d+) errors=(\d+)", run.stderr)
            assert match and tuple(map(int, match.groups())) == expected, run.stderr
            digest = json.loads((out / "digest.json").read_text(encoding="utf-8"))
            doc = (out / ("data" + GAME + "/DataAsset/DA_PlayerData.md")).read_text(encoding="utf-8")
            resolution = digest["data_assets"][GAME + "/DataAsset/DA_PlayerData"]["enum_resolution"]
            if phase in ("cold", "warm"):
                assert 'E_Crates::NewEnumerator10(6, display="GTIWeaponCrate")' in doc
                snapshots.append({p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()})
            elif phase == "enum_changed":
                assert 'display="NEWWeaponCrate"' in doc and "GTIWeaponCrate" not in doc
            else:
                assert "E_Crates::NewEnumerator10(value unresolved)" in doc and "WeaponCrate" not in doc
                assert "everything decoded cleanly" not in (out / "INDEX.md").read_text(encoding="utf-8")
            assert resolution == ({"resolved": 0, "unresolved": 5} if phase == "enum_missing" else {"resolved": 5, "unresolved": 0})
            assert not digest["failures"] and not digest["data_failures"]
            print(f"PASS enum CLI {phase}: cache={expected}, resolution={resolution}", flush=True)
        assert snapshots[0] == snapshots[1], "cold/warm output bytes differ"
        print("PASS enum cache invalidation: enum-only edit/missing reuses dependent data, no stale labels", flush=True)


if __name__ == "__main__":
    main()
