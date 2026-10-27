#!/usr/bin/env python3
"""Fast checks that need no repository clone (run automatically by tests/regress.py)."""
from __future__ import annotations

import io
import json
import os
import struct
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import bp_reader as B  # noqa: E402
import ue_repo_digest as D  # noqa: E402


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


def _output_scratch():
    cache = Path(__file__).resolve().parent / ".cache"
    cache.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="output-safety-", dir=cache)


def _digest_cli(args):
    # No assets are present: exercise the real CLI and filesystem, without parser installation or git.
    with patch.object(D, "classify_assets", return_value={}), \
         patch.object(D, "run", return_value=SimpleNamespace(stdout="", returncode=0)), \
         redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return D.main(args)


def _reject_output(args):
    # The original bug attempts deletion; fail before it can touch even the disposable fixture.
    with patch.object(D.shutil, "rmtree", side_effect=AssertionError("unexpected output deletion")):
        try:
            _digest_cli(args)
        except SystemExit as e:
            assert e.code != 0
        else:
            raise AssertionError("unsafe output was accepted")


def test_output_preserves_source():
    with _output_scratch() as tmp:
        base = Path(tmp).resolve()
        assert base.parent == Path(__file__).resolve().parent / ".cache"
        source = base / "원본 project"
        source.mkdir()
        marker = source / "Game.uproject"
        marker.write_text("{}", encoding="utf-8")
        # Include normalized aliases and an ancestor containing the input.
        for output in (source, source / ".." / source.name, base):
            _reject_output([str(source), "--out", str(output)])
            assert marker.read_text(encoding="utf-8") == "{}"
        alias = base / "source-alias"
        try:
            alias.symlink_to(source, target_is_directory=True)
        except OSError:
            print("SKIP  output symlink case (creation not permitted)")
        else:
            _reject_output([str(source), "--out", str(alias)])
            assert marker.is_file()


def test_output_preserves_unrelated_files():
    with _output_scratch() as tmp:
        base = Path(tmp)
        source, out = base / "source", base / "output"
        source.mkdir()
        out.mkdir()
        note = out / "notes.txt"
        note.write_text("keep me", encoding="utf-8")
        for manifest in (None, "{broken json", "[]", json.dumps({"tool": "another-tool"}),
                         json.dumps({"tool": "ue-repo-reader 1.5.0"})):
            if manifest is not None:
                (out / "digest.json").write_text(manifest, encoding="utf-8")
            _reject_output([str(source), "--out", str(out)])
            assert note.read_text(encoding="utf-8") == "keep me"
        _reject_output([str(source), "--out", str(note)])


def test_output_windows_junction():
    if os.name != "nt":
        return
    with _output_scratch() as tmp:
        base = Path(tmp)
        source, out, alias = base / "source", base / "digest", base / "junction"
        source.mkdir()
        assert _digest_cli([str(source), "--out", str(out)]) == 0
        before = (out / "INDEX.md").read_bytes()
        subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/c", "mklink", "/J", str(alias), str(out)],
                       check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        _reject_output([str(source), "--out", str(alias)])
        assert (out / "INDEX.md").read_bytes() == before


def test_output_rerun():
    with _output_scratch() as tmp:
        base = Path(tmp)
        source = base / "source"
        source.mkdir()
        (source / "Game.uproject").write_text("{}", encoding="utf-8")
        # New output, empty output, and a dedicated output subfolder inside the input are supported.
        for out in (base / "새 결과", base / "empty", source / "digest"):
            if out.name == "empty":
                out.mkdir()
            args = [str(source), "--out", str(out)]
            assert _digest_cli(args) == 0
            stale = out / "maps" / "stale.md"
            stale.write_text("old generated map", encoding="utf-8")
            (out / "INDEX.part10.md").write_text("old split index", encoding="utf-8")
            assert _digest_cli(args) == 0
            assert (out / "INDEX.md").is_file() and not stale.exists()
            assert (source / "Game.uproject").is_file()


def test_output_invalid_project_preserves_digest():
    with _output_scratch() as tmp:
        base = Path(tmp)
        source, out = base / "source", base / "output"
        source.mkdir()
        (source / "Game.uproject").write_text("{}", encoding="utf-8")
        assert _digest_cli([str(source), "--out", str(out)]) == 0
        before = (out / "INDEX.md").read_bytes()
        _reject_output([str(source), "--out", str(out), "--project", "Missing"])
        assert (out / "INDEX.md").read_bytes() == before
        # Even a recognized digest must not be removed if it contains the selected input project.
        (out / "cpp" / "Nested.uproject").write_text("{}", encoding="utf-8")
        _reject_output([str(source), "--out", str(out), "--project", "Nested"])
        assert (out / "cpp" / "Nested.uproject").is_file()


def test_output_validated_around_clone():
    with _output_scratch() as tmp:
        base = Path(tmp)
        source = base / "repo"
        args = ["https://example.com/repo.git", "--workdir", str(source)]
        with patch.object(D, "clone") as clone:
            _reject_output(args + ["--out", str(base)])
            clone.assert_not_called()

        out = source / "output"

        def checkout(*args):
            out.mkdir(parents=True)
            (out / "tracked.txt").write_text("repository file", encoding="utf-8")
            return {}

        with patch.object(D, "clone", side_effect=checkout) as clone:
            _reject_output(args + ["--out", str(out)])
            clone.assert_called_once()
        assert (out / "tracked.txt").read_text(encoding="utf-8") == "repository file"


def _utf8_stdio() -> None:
    """Windows consoles/pipes default to the ANSI code page (cp949 on Korean systems): never crash on output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def test_lfs_include_pattern():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import fnmatch
    import ue_repo_digest as D
    for p in ("Content/UI/WBP_A[1].uasset", "Content/Maps/Map,Night.umap", "Content/X/What?.uasset", "Content/a*b.uasset"):
        pat = D.lfs_include_pattern(p)
        assert not any(c in pat for c in "[]*,\\"), pat
        assert fnmatch.fnmatchcase(p, pat), (p, pat)


def main() -> int:
    _utf8_stdio()
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
