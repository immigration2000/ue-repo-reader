"""Q4: complete decoded map values survive compact Markdown, JSON and raw-result caching."""
import base64
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import asset_cache as C
import bp_reader as B
import map_reader as M


def test_map_saved_values_preserve_nested_literals_and_types():
    @dataclass
    class NativeValue:
        source_string: str
        fields: dict
    text = '한글 | "quote"\n```\nName_1_' + 'A' * 32 + 'x' * 900
    value = {"text": text, "array": list(range(40)), "deep": {"a": {"b": {"c": {"d": [False, 0, None]}}}},
             "native": NativeValue(text, {"Bytes": bytes(range(256)), "Map": {1: "int key", "1": "string key"}}),
             "reference": B.ObjRef(-3), "opaque": {"kind": "binary_or_native_property", "raw_data": b"\x00\xff"}}
    ctx = NS(issues=[], obj_name=lambda index: "/Game/Full.Asset")
    saved = json.loads(json.dumps(M._saved_value(value, ctx, "Actor"), ensure_ascii=False, allow_nan=False))
    assert saved["text"] == text and saved["array"] == list(range(40))
    assert saved["deep"]["a"]["b"]["c"]["d"] == [False, 0, None]
    assert saved["native"]["fields"]["source_string"] == text
    assert base64.b64decode(saved["native"]["fields"]["fields"]["Bytes"]["data"]) == bytes(range(256))
    assert len(saved["native"]["fields"]["fields"]["Map"]["entries"]) == 2
    assert saved["reference"] == {"kind": "object_reference", "index": -3, "name": "/Game/Full.Asset"}
    assert saved["opaque"]["kind"] == "binary_or_native_property" and not ctx.issues


def test_map_saved_values_unknowns_are_explicit_and_reported():
    cycle = []
    cycle.append(cycle)
    ctx = NS(issues=[])
    value = M._saved_value({"Good": "keep", "Unknown": object(), "Cycle": cycle, "Infinity": float("inf")}, ctx, "Actor")
    assert value["Good"] == "keep" and len(ctx.issues) == 2
    assert value["Unknown"]["kind"] == "unavailable" and value["Cycle"][0]["kind"] == "unavailable"
    assert {issue["stage"] for issue in ctx.issues} == {"actor_values"}
    assert value["Infinity"] == {"kind": "float", "value": "inf"}
    json.dumps(value, allow_nan=False)


def test_map_actor_full_values_do_not_reuse_compact_preview():
    actor = M.PackageActors.__new__(M.PackageActors)
    actor.path, actor.package_path = "Map.umap", "/Game/Map"
    actor.ctx = NS(issues=[])
    actor.failed_props = set()
    actor.children = {1: [2]}
    actor.child = lambda owner, name: 2 if name == "Root" else None
    actor.name = lambda index: "Root" if index == 2 else "Actor"
    root = {"RelativeLocation": {"struct_type": "Vector", "fields": {"X": 1.234567, "Y": 2, "Z": 3}}}
    actor.props = lambda index: root
    properties = {"RootComponent": "Root", "ActorLabel": "Actor", **{f"P{i}": list(range(20)) for i in range(12)},
                  "Long": "z" * 900, "bOverrideFlag": True}
    result = actor.describe(1, "BP_Actor_C", properties)
    saved = result["saved"]
    assert len(result["overrides"]) > 8 and "…" in result["overrides"][0]
    assert saved["saved_properties"]["P11"] == list(range(20))
    assert saved["saved_properties"]["Long"] == "z" * 900 and saved["saved_properties"]["bOverrideFlag"] is True
    assert saved["root_component"]["saved_properties"]["RelativeLocation"]["fields"]["X"] == 1.234567
    assert saved["source_package"] == "/Game/Map" and saved["export_index"] == 1
    actor.failed_props.add(2)
    assert actor.describe(1, "BP_Actor_C", properties)["saved"]["properties_status"] == "partial"
    actor.failed_props.clear()
    malformed = actor.describe(1, "BP_Actor_C", {"ActorLabel": {"Bad": "not a label"}})
    assert malformed["label"] == "Actor" and malformed["saved"]["properties_status"] == "partial"
    assert malformed["saved"]["saved_properties"]["ActorLabel"] == {"Bad": "not a label"}
    json.dumps(malformed, allow_nan=False)
    assert actor.ctx.issues[-1]["context"] == "Actor.ActorLabel"


def test_map_full_values_reach_summary_and_cache_with_external_identity():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        main = root / "Map.umap"
        main.write_bytes(b"map")
        external = [root / "Content/__ExternalActors__/Map" / folder / "Same.uasset" for folder in ("A", "B")]
        for path in external:
            path.parent.mkdir(parents=True)
            path.write_bytes(b"actor")
        class Package:
            def __init__(self, path):
                self.path, self.issues, self.failed_props = path, [], set()
                self.r = NS(summary=NS())
            def actors(self, **kwargs):
                return [{"name": "Same", "label": "Same", "class": "BP_Actor_C", "loc": None, "rot": None,
                         "overrides": ["P=preview"], "hidden": False, "tags": [], "folder": "",
                         "saved": {"source_package": self.package_path, "export_index": 1,
                                   "saved_properties": {"P": list(range(30))}}}]
            def close(self): pass
        info = {"game_mode": None, "game_mode_known": True, "world_partition": True, "streaming": [], "settings": []}
        ir = {"schema_version": 1, "status": "complete", "graphs": []}
        bp = {"markdown": "## Graphs\n(no graphs)", "summary": {"issues": [], "parse_status": "ok", "nodes_ok": 0, "nodes_total": 0, "graph_ir": ir}}
        with patch.object(B, "ensure_uasset_read"), patch.object(B, "_install_patches"), \
                patch.object(B, "newer_format_note", return_value=""), patch.object(M, "PackageActors", Package), \
                patch.object(M, "_world_info", return_value=info), patch.object(B, "read_blueprint", return_value=bp):
            result = M.read_map(str(main), "/Plugin/Map", [str(path) for path in external])
        actors = result["summary"]["actors"]
        assert result["summary"]["level_bp_graph_ir"] == ir
        assert len(actors) == result["summary"]["actor_count"] == 3
        assert len({actor["source_package"] for actor in actors}) == 3
        assert actors[1]["source_package"] == "/Plugin/__ExternalActors__/Map/A/Same"
        assert "Full decoded actor/root-component" in result["markdown"]
        cache = C.AssetCache(root / "cache", root, "q4-test", fingerprint="q4")
        key = cache.key("map", (main, "/Plugin/Map", external))
        cache.store(key, result)
        assert cache.load(key) == json.loads(json.dumps(result))
        assert cache.load(key)["summary"]["actors"][2]["saved_properties"]["P"] == list(range(30))
