"""Verify the regression suite itself rejects missing assets, wrong oracles and corrupt downloads."""
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import asset_regress as A
import bp_reader as B
import regress


def _scratch():
    cache = Path(__file__).resolve().parent / ".cache"
    cache.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="coverage-check-", dir=cache)


def test_regress_detects_missing_assets():
    with _scratch() as tmp:
        root = Path(tmp)
        (root / "INDEX.md").write_text("Coverage: 0 Blueprints rendered, 0 failed; graph nodes decoded 0/0", encoding="utf-8")
        summary = {"issues": [], "parse_status": "ok", "level_bp_nodes": [0, 0], "level_bp_status": "ok",
                   "external_actors": 1, "world_partition": True, "actor_count": 2}
        value = {"blueprints": {}, "data_assets": {}, "maps_detail": {"/Game/World": summary},
                 "failures": {}, "data_failures": {}, "map_failures": {}, "lfs": {}}
        (root / "digest.json").write_text(json.dumps(value), encoding="utf-8")
        fixture = {"expect": {"blueprints": 0, "nodes": 0, "data_assets": 1, "maps": 2, "external_actors": 2},
                   "summary_checks": [{"collection": "maps_detail", "path": "/Game/World", "fields": {"actor_count": 3}}]}
        errors = regress.check(fixture, root)
        assert any("data_assets 0 != expected 1" in e for e in errors)
        assert any("maps 1 != expected 2" in e for e in errors)
        assert any("external actors 1 != expected 2" in e for e in errors)
        assert any("actor_count 2 != expected 3" in e for e in errors)


def test_asset_oracle_rejects_wrong_text():
    with _scratch() as tmp:
        root = Path(tmp)
        expected = [{"objectPath": "/Game/Keys.BP:EventGraph.split", "pinIndex": 0,
                     "pinId": "0102030405060708090A0B0C0D0E0F10", "source": "oracle source"}]
        (root / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
        case = {"kind": "blueprint", "engine": "5.8", "asset": {"path": "BP.uasset"}, "oracle": {"path": "expected.json"}}
        pin = NS(pin_id="04030201080706050C0B0A09100F0E0D", default_text_value="wrong text")
        node = NS(_export_object_name="split", pins=[pin])
        graph = NS(nodes=[node], subgraphs=[])
        rendered = {"markdown": "oracle source", "summary": {"issues": [], "parse_status": "ok"}}
        with patch.object(B, "read_blueprint", return_value=rendered), \
             patch.object(B, "_parse", return_value=(NS(graphs=[graph]), (1, 1))), \
             patch.object(B, "_read_summary", return_value=NS(saved_by_engine_version=NS(major=5, minor=8, patch=3))):
            try:
                A.check_case(case, root)
            except AssertionError as e:
                assert "wrong text" in str(e)
            else:
                raise AssertionError("wrong pin text passed its native oracle")
            pin.default_text_value = "oracle source"
            A.check_case(case, root)


def test_asset_download_hash_guard():
    with _scratch() as tmp:
        root = Path(tmp)
        with patch.object(A.urllib.request, "urlopen", return_value=io.BytesIO(b"corrupt")):
            try:
                A.fetch_file({"repository": "example/fixture", "commit": "a" * 40},
                             {"path": "asset.uasset", "blob": "b" * 40}, root)
            except ValueError as e:
                assert "hash mismatch" in str(e)
            else:
                raise AssertionError("corrupt asset was published")
        assert not (root / "asset.uasset").exists()
