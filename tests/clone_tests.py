"""Real local partial-clone regressions; no remote network or bundled binaries."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ue_repo_digest as D


def test_partial_clone_reuse_keeps_heavy_blobs_missing():
    cache = ROOT / "tests/.cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="partial-", dir=cache) as tmp:
        base = Path(tmp).resolve()
        origin, dest = base / "origin", base / "공백 [캐시],"
        origin.mkdir()
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")

        def git(root, *args, check=True):
            return subprocess.run(["git", "-C", str(root), *args], check=check, env=env,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)

        git(origin, "init", "-q")
        git(origin, "config", "uploadpack.allowFilter", "true")
        git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")
        git(origin, "config", "user.name", "Test")
        git(origin, "config", "user.email", "test@example.invalid")
        content = origin / "Content"
        content.mkdir()
        (origin / "Game.uproject").write_text("{}", encoding="utf-8")
        (origin / "Removed.txt").write_text("old only", encoding="utf-8")
        (content / "BP_Player[1],.uasset").write_bytes(b"old blueprint")
        (content / "T_Heavy.uasset").write_bytes(b"first texture" * 220000)
        git(origin, "add", ".")
        git(origin, "commit", "-qm", "first")
        first = git(origin, "rev-parse", "HEAD").stdout.strip()
        heavy1 = git(origin, "rev-parse", "HEAD:Content/T_Heavy.uasset").stdout.strip()
        (origin / "Removed.txt").unlink()
        (origin / "New.txt").write_text("new only", encoding="utf-8")
        (content / "BP_Player[1],.uasset").write_bytes(b"new blueprint")
        (content / "T_Heavy.uasset").write_bytes(b"second texture" * 220000)
        # A large gameplay asset must still materialize, even with blob filtering.
        (content / "BP_Large.uasset").write_bytes(b"large gameplay" * 220000)
        git(origin, "add", ".")
        git(origin, "commit", "-qm", "second")
        second = git(origin, "rev-parse", "HEAD").stdout.strip()
        heavy2 = git(origin, "rev-parse", "HEAD:Content/T_Heavy.uasset").stdout.strip()
        git(origin, "tag", "second", second)

        def missing(oid):
            result = git(dest, "--no-lazy-fetch", "cat-file", "-e", oid, check=False)
            assert result.returncode != 0, "heavy blob was fetched by checkout"

        report = D.clone(origin.as_uri(), dest, first)
        assert report["commit"] == first and report["skipped_large_files"]["count"] == 1
        missing(heavy1)
        assert (dest / "Removed.txt").is_file()
        # Fetch an absent ref with the same size filter, then selectively checkout.
        report = D.clone(origin.as_uri(), dest, "second")
        assert report["commit"] == second and report["skipped_large_files"]["count"] == 1
        missing(heavy1)
        missing(heavy2)
        assert not (dest / "Removed.txt").exists(), "deleted files survived a ref switch"
        assert (dest / "New.txt").read_text(encoding="utf-8") == "new only"
        assert (dest / "Content/BP_Player[1],.uasset").read_bytes() == b"new blueprint"
        assert (dest / "Content/BP_Large.uasset").stat().st_size > 2_000_000
        assert not (dest / "Content/T_Heavy.uasset").exists()
        # Resolve a local SHA without checkout/fetch; unchanged files stay untouched.
        timestamp = (dest / "New.txt").stat().st_mtime_ns
        for ref in (second[:12], None):
            report = D.clone(origin.as_uri(), dest, ref)
            assert report["commit"] == second and report["skipped_large_files"]["count"] == 1
            assert (dest / "New.txt").stat().st_mtime_ns == timestamp
            missing(heavy2)
        # Reject local edits, staged edits and untracked collisions without data loss.
        (dest / "New.txt").write_text("personal change", encoding="utf-8")
        try:
            D.clone(origin.as_uri(), dest, first)
        except SystemExit as exc:
            assert "local or staged" in str(exc)
        else:
            raise AssertionError("local edit overwritten")
        assert (dest / "New.txt").read_text(encoding="utf-8") == "personal change"
        assert git(dest, "rev-parse", "HEAD").stdout.strip() == second
        git(dest, "add", "New.txt")
        try:
            D.clone(origin.as_uri(), dest, first)
        except SystemExit as exc:
            assert "local or staged" in str(exc)
        else:
            raise AssertionError("staged edit overwritten")
        git(dest, "reset", "-q", "HEAD", "--", "New.txt")
        (dest / "New.txt").write_text("new only", encoding="utf-8")
        (dest / "Removed.txt").write_text("personal untracked", encoding="utf-8")
        try:
            D.clone(origin.as_uri(), dest, first)
        except SystemExit as exc:
            assert "untracked" in str(exc)
        else:
            raise AssertionError("untracked file overwritten")
        assert (dest / "Removed.txt").read_text(encoding="utf-8") == "personal untracked"
        (dest / "Removed.txt").unlink()
        report = D.clone(origin.as_uri(), dest, first)
        assert report["commit"] == first and not (dest / "New.txt").exists()
        missing(heavy1)
