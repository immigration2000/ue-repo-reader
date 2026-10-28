"""Asset-cache invalidation, worker scheduling, corruption and eviction regressions."""
import gzip
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import asset_cache as C
import ue_repo_digest as D


def result(path="/Game/A"):
    return {"markdown": "# A\n", "summary": {"path": path, "parse_status": "ok", "issues": [],
            "nodes_ok": 2, "nodes_total": 2}, "seconds": 3}


def test_asset_cache_hash_and_dependency_invalidation():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        asset, external = base / "A.uasset", base / "E.uasset"
        asset.write_bytes("한글\nbytes\r\n".encode("utf-8"))
        external.write_bytes(b"external")
        expected = subprocess.run(["git", "hash-object", "--no-filters", str(asset)], check=True,
                                  capture_output=True, text=True, encoding="utf-8").stdout.strip()
        assert C.blob_sha(asset) == expected
        cache = C.AssetCache(base / "cache", base, "v1", fingerprint="decoder")
        key = cache.key("bp", (asset, "/Game/A"))
        cache.store(key, result())
        loaded = cache.load(key)
        assert loaded["summary"]["nodes_total"] == 2 and "seconds" not in loaded
        assert list(loaded["summary"]) == list(result()["summary"])
        loaded["summary"]["placed_in"] = {"old map": 1}
        assert "placed_in" not in cache.load(key)["summary"], "enrichment leaked into cache"
        for version, fingerprint, game_path in (("v2", "decoder", "/Game/A"), ("v1", "new", "/Game/A"),
                                                ("v1", "decoder", "/Plugin/A")):
            other = C.AssetCache(base / "cache", base, version, fingerprint=fingerprint)
            assert other.load(other.key("bp", (asset, game_path))) is None
        old_time = asset.stat().st_mtime_ns
        asset.write_bytes(b"x" * asset.stat().st_size)
        os.utime(asset, ns=(old_time, old_time))
        assert cache.load(cache.key("bp", (asset, "/Game/A"))) is None, "mtime/size hid changed bytes"
        assert cache.key("map", (asset, "/Game/M", []))[0] != cache.key("map", (asset, "/Game/M", [external]))[0]
        map_key = cache.key("map", (asset, "/Game/M", [external, asset]))
        assert map_key[0] != cache.key("map", (asset, "/Game/M", [asset, external]))[0]
        external.write_bytes(b"different actor")
        assert map_key[0] != cache.key("map", (asset, "/Game/M", [external, asset]))[0]
        cache.store(key, result())  # file changed since key creation
        assert cache.stats["errors"] == 1


def test_asset_cache_corruption_partial_and_eviction():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        asset = base / "A.uasset"
        asset.write_bytes(b"asset")
        cache = C.AssetCache(base / "cache", base, "v1", fingerprint="decoder", log=lambda _: None)
        key = cache.key("bp", (asset, "/Game/A"))
        for field, value in (("parse_status", "partial"), ("issues", [{"message": "failed"}]),
                             ("newer_format", "unknown version"), ("nodes_ok", 1), ("level_bp_status", "error")):
            bad = result()
            bad["summary"][field] = value
            cache.store(key, bad)
            assert cache.load(key) is None
        cache.store(key, result())
        key[2].write_bytes(b"broken gzip")
        assert cache.load(key) is None
        cache.store(key, result())
        entry = json.loads(gzip.decompress(key[2].read_bytes()))
        entry["value"]["markdown"] = "false data"
        key[2].write_bytes(gzip.compress(json.dumps(entry).encode("utf-8")))
        assert cache.load(key) is None, "checksum was not checked"
        cache.store(key, result())
        unrelated = key[2].parent / "user.json.gz"
        unrelated.write_bytes(b"keep")
        cache.prune(byte_limit=0)
        assert not key[2].exists() and unrelated.read_bytes() == b"keep"
        # An actual Windows junction must never turn eviction into deletion outside the cache.
        if os.name == "nt":
            outside = base / "outside"
            outside.mkdir()
            victim = outside / ("ZZ" + "a" * 41 + ".json.gz")
            victim.write_bytes(b"keep")
            junction = cache.root / "ZZ"
            subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], check=True,
                           capture_output=True, encoding="utf-8", errors="replace")
            try:
                cache.prune(byte_limit=0)
                assert victim.read_bytes() == b"keep"
            finally:
                junction.rmdir()  # removes only the junction, not its contents


def test_asset_cache_only_changed_assets_start_workers():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        paths = [base / name for name in ("A.uasset", "B.uasset")]
        for path in paths:
            path.write_bytes(b"asset")
        items = [(str(path), "/Game/" + path.stem) for path in paths]
        cache = C.AssetCache(base / "cache", base, "v1", fingerprint="decoder")
        for item in items:
            cache.store(cache.key("bp", item), result(item[1]))
            cache.store(cache.key("class", item[0]), "Blueprint")
        with patch.object(D.mp, "get_context") as context:
            assert len(D.process_blueprints(items, 1, 1, cache=cache)[0]) == 2
            assert len(D.classify_assets([item[0] for item in items], 1, cache=cache)) == 2
            context.assert_not_called()
        paths[0].write_bytes(b"changed")
        class Job:
            def get(self, timeout):
                return items[0][1], result(), None
        class Pool:
            scheduled = []
            def apply_async(self, worker, args):
                self.scheduled.append(args[0])
                return Job()
            def terminate(self): pass
            def join(self): pass
        pool = Pool()
        with patch("bp_reader.ensure_uasset_read"), patch.object(D.mp, "get_context") as context:
            context.return_value.Pool.return_value = pool
            values, failed = D.process_blueprints(items, 1, 1, cache=cache)
        assert not failed and list(values) == [item[1] for item in items]
        assert pool.scheduled == [items[0]], "unchanged asset was reparsed"


def test_asset_cache_preflight_preserves_previous_digest():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project, out = base / "project", base / "out"
        project.mkdir()
        (project / "P.uproject").write_text("{}", encoding="utf-8")
        out.mkdir()
        (out / "digest.json").write_text('{"tool":"ue-repo-reader 1.6.0"}', encoding="utf-8")
        (out / "INDEX.md").write_text("keep old result", encoding="utf-8")
        try:
            D.main([str(project), "--out", str(out), "--asset-cache-dir", str(out / "cache")])
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("overlapping cache/output accepted")
        assert (out / "INDEX.md").read_text(encoding="utf-8") == "keep old result"
