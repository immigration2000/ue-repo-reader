#!/usr/bin/env python3
"""Fast checks that need no repository clone (run automatically by tests/regress.py)."""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import bp_reader as B  # noqa: E402


class _Ar:
    def __init__(self, data: bytes):
        self.b = io.BytesIO(data)

    def read_i32(self, key=""):
        return struct.unpack("<i", self.b.read(4))[0]

    def read_bytes(self, n, key=""):
        return self.b.read(n)

    def tell(self):
        return self.b.tell()


def test_devnotes():
    # empty note: just the length
    ar = _Ar(struct.pack("<i", 0) + b"NEXT")
    assert B._skip_devnotes(ar) == 4 and ar.b.read() == b"NEXT"
    # ANSI note "hi\0"
    ar = _Ar(struct.pack("<i", 3) + b"hi\x00" + b"NEXT")
    assert B._skip_devnotes(ar) == 7 and ar.b.read() == b"NEXT"
    # UTF-16 note "한\0" (length -2 → 4 bytes)
    ar = _Ar(struct.pack("<i", -2) + "한\x00".encode("utf-16-le") + b"NEXT")
    assert B._skip_devnotes(ar) == 8 and ar.b.read() == b"NEXT"


def test_member_names():
    assert B.clean_member_names("New Var.GridWidth_18_EF302CA945656BC9DD62659509343FD0 * 2") == "New Var.GridWidth * 2"


def test_pin_struct():
    assert B._fmt_pin_struct("Vector", "0.000000,0.000000,80.000000") == "Vector{X=0, Y=0, Z=80}"
    assert B._fmt_pin_struct("GameplayTag", '(TagName="Status.Stunned")') == "GameplayTag{TagName=Status.Stunned}"
    assert B._fmt_pin_struct("LinearColor", "(R=1.000000,G=0.000000,B=0.000000,A=0.500000)") == "LinearColor{R=1, G=0, B=0, A=0.5}"


def test_newer_format_note():
    B._VERS_CACHE["fake58"] = {B._FNMB_GUID: 268, B._RELEASE_GUID: 44}
    B._FILE_UE5["fake58"] = 1018
    assert B.newer_format_note("fake58") == ""
    B._VERS_CACHE["fake59"] = {B._FNMB_GUID: 275}
    B._FILE_UE5["fake59"] = 1019
    note = B.newer_format_note("fake59")
    assert "FileVersionUE5 1019 > 1018" in note and "FFortniteMainBranchObjectVersion 275 > 268" in note, note


def test_combo_order():
    B._VERS_CACHE["fake425"] = {B._RELEASE_GUID: 30}      # UE 4.25: no UObject wrapper flag yet
    B._FILE_UE5["fake425"] = 0
    first = B._combo_order("fake425", ue5=False)[0]
    assert first[1] == 0 and first[2] == 0, first
    B._VERS_CACHE["fake51"] = {B._RELEASE_GUID: 44, B._UE5RS_GUID: 41}
    first = B._combo_order("fake51", ue5=True)[0]
    assert first[1] == 1 and first[2] == 1, first


def test_split_md():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import ue_repo_digest as D
    text = "# T\n\n```text\n" + "".join(f"line {i}\n" for i in range(3000)) + "```\n\n## After\nend\n"
    parts = D.split_md_text(text, 5000)
    assert len(parts) > 1 and all(len(p) <= 5000 for p in parts), [len(p) for p in parts]
    assert all(p.count("```") % 2 == 0 for p in parts), "every part must have balanced fences"
    joined = "".join(parts).replace("```\n```text\n", "")
    assert all(f"line {i}\n" in joined for i in (0, 1500, 2999)) and joined.endswith("end\n")


def main() -> int:
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  unit {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  unit {name}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
