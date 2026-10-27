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
