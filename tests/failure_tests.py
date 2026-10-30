"""Failure-injection checks for partial digests; no Unreal packages or network required."""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import patch

import bp_reader as B
import data_reader as R
import map_reader as M
import ue_repo_digest as D
import regress
from project_support import assess_project


def _scratch():
    cache = Path(__file__).resolve().parent / ".cache"
    cache.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="partial-digest-", dir=cache)


def _write_digest(root, bps=None, data=None, maps=None, **fields):
    value = {"blueprints": bps or {}, "data_assets": data or {}, "maps_detail": maps or {},
             "failures": {}, "data_failures": {}, "map_failures": {}, "lfs": {}, **fields}
    (root / "digest.json").write_text(json.dumps(value), encoding="utf-8")


def _index(root, bps=None, data=None, maps=None):
    with patch.object(D, "gameplay_tags", return_value=([], None)):
        D.build_index({"project_support": assess_project("5.8")}, root, {"classes": [], "modules": []}, bps or {}, {}, [], [], {}, root, None,
                      datas=data, levels=maps)
    return (root / "INDEX.md").read_text(encoding="utf-8")


def _fixture(bps=0, nodes=0):
    return {"expect": {"blueprints": bps, "nodes": nodes}}


def _reader_setup(stack):
    stack.enter_context(patch.object(B, "ensure_uasset_read"))
    stack.enter_context(patch.object(B, "_install_patches"))
    stack.enter_context(patch.object(B, "newer_format_note", return_value=""))


def _map(root, broken=False, partial=False, unlisted=None):
    path = root / "Test.umap"
    path.write_bytes(b"")

    class Package:
        def __init__(self, name):
            if Path(name) != path:
                raise ValueError("external actor failure")
            self.r = NS(summary=NS(), export_map=[NS()])
            self.issues, self.failed_props = [], set()

        def cls(self, index):
            return "WorldSettings"

        def props(self, index):
            if broken:
                self.failed_props.add(index)
                B.record_issue(self.issues, "properties", "WorldSettings", ValueError("settings failure"))
            return {}

        def actors(self, **kwargs):
            return []

        def close(self):
            pass

    summary = {"nodes_ok": 1 if partial else 0, "nodes_total": 2 if partial else 0,
               "entries": [], "issues": [], "parse_status": "partial" if partial else "ok"}
    if unlisted is not None:
        summary["unlisted_graph_nodes"] = unlisted
    with ExitStack() as stack:
        _reader_setup(stack)
        stack.enter_context(patch.object(M, "PackageActors", Package))
        stack.enter_context(patch.object(B, "read_blueprint", side_effect=ValueError("Level BP failure") if broken else None,
                                         return_value={"summary": summary, "markdown": "## Graphs\n(no graphs)"}))
        return M.read_map(str(path), "/Game/Test", ["Bad.uasset", "Skipped.uasset"] if broken else [], max_external=1)


def test_map_preserves_unlisted_level_script_exports_separately():
    with _scratch() as tmp:
        detail = {"schema_version": 1, "nodes_total": 1, "graphs": [{"nodes": [{"export_index": 17}]}]}
        summary = _map(Path(tmp), unlisted=detail)["summary"]
        assert summary["level_bp_unlisted_graph_nodes"] == detail
        assert summary["level_bp_nodes"] == (0, 0) and summary["level_bp_status"] == "ok"


def test_partial_map_reporting():
    with _scratch() as tmp:
        root = Path(tmp)
        result = _map(root, broken=True)
        summary = result["summary"]
        assert summary["level_bp_nodes"] is None and summary["level_bp_status"] == "error"
        assert not summary["game_mode_known"] and summary["parse_status"] == "partial"
        assert summary["external_actor_errors"] == 1 and summary["external_actors_truncated"] == 1
        assert {i["stage"] for i in summary["issues"]} == {"properties", "external_actor", "external_actors", "level_blueprint"}
        assert "Game mode override: unknown" in result["markdown"]
        maps = {"/Game/Test": result}
        index = _index(root, maps=maps)
        assert "everything decoded cleanly" not in index and "⚠ unreadable" in index
        _write_digest(root, maps={"/Game/Test": summary})
        errors = regress.check(_fixture(), root)
        assert any("Level Blueprint not decoded" in e for e in errors)
        assert any("external actors incomplete" in e for e in errors)


def test_empty_and_partial_level_blueprints():
    with _scratch() as tmp:
        root = Path(tmp)
        empty = _map(root)
        assert empty["summary"]["level_bp_nodes"] == (0, 0)
        assert empty["summary"]["level_bp_status"] == "ok" and not empty["summary"]["issues"]
        assert "everything decoded cleanly" in _index(root, maps={"/Game/Test": empty})
        _write_digest(root, maps={"/Game/Test": empty["summary"]})
        assert regress.check(_fixture(), root) == []
        partial = _map(root, partial=True)
        assert partial["summary"]["parse_status"] == "partial"
        assert partial["summary"]["issues"][0]["stage"] == "level_blueprint.nodes"
        assert "everything decoded cleanly" not in _index(root, maps={"/Game/Test": partial})
        _write_digest(root, maps={"/Game/Test": partial["summary"]})
        assert any("Level Blueprint 1/2 partial" in e for e in regress.check(_fixture(), root))


def test_graph_render_failure_reporting():
    with _scratch() as tmp:
        root = Path(tmp)
        path = root / "Test.uasset"
        path.write_bytes(b"")
        node = NS(class_name="TestNode", pins=[NS()])
        graph = NS(graph_name="EventGraph", nodes=[node], subgraphs=[])
        result = NS(summary=NS(), blueprint=None, graphs=[graph])
        ctx = NS(issues=[], props=lambda obj: {}, obj_name=lambda ref: "", export_by_name=lambda name: None)
        renderer = NS(nodes=[node], mode=lambda: "exec", var_refs={}, unused_events=[])

        def fail():
            raise ValueError("injected graph failure")

        renderer.render_exec = fail
        with ExitStack() as stack:
            _reader_setup(stack)
            for name, value in (("_parse", (result, (1, 1))), ("Ctx", ctx), ("_find_blueprint_object", (None, None)),
                                ("_graph_key", "EventGraph"), ("GraphRenderer", renderer), ("_components", []),
                                ("_widget_tree", []), ("_timelines", []), ("_variables", ([], set())),
                                ("_variable_metadata", {}), ("_cdo_lines", []),
                                ("build_graph_ir", {"status": "complete", "schema_version": 1, "issues": []})):
                stack.enter_context(patch.object(B, name, return_value=value))
            bp = B.read_blueprint(str(path), "/Game/Test")
        assert bp["summary"]["nodes_ok"] == bp["summary"]["nodes_total"] == 1
        assert bp["summary"]["parse_status"] == "partial"
        assert bp["summary"]["issues"][0]["stage"] == "graph_render"
        assert "injected graph failure" in bp["markdown"]
        assert "everything decoded cleanly" not in _index(root, bps={"/Game/Test": bp})
        _write_digest(root, bps={"/Game/Test": bp["summary"]})
        assert any("unexpected parse issue" in e for e in regress.check(_fixture(1, 1), root))


def test_property_failure_reporting():
    reader = R.TaggedReader.__new__(R.TaggedReader)
    reader.issues, reader.names = [], []
    reader.ar = io.BytesIO(b"\0" * 32)
    tags = iter([NS(name="SavedValue", type="IntProperty", value_start_offset=0, value_end_offset=4), NS(name="None")])
    reader._read_tag = lambda *a, **k: next(tags)
    reader.r = NS(export_map=[], summary=NS())

    def fail(*args):
        raise ValueError("injected property failure")

    reader._parse_value = fail
    assert "unreadable" in reader.stream(32)[0][1]
    assert reader.issues[0]["context"] == "SavedValue"
    pkg = M.PackageActors.__new__(M.PackageActors)
    pkg.path, pkg._props, pkg.failed_props, pkg.issues = "Test.umap", {}, set(), []
    pkg.r = NS(export_map=[NS(object_name="Settings")])
    pkg.reader = NS(export_stream=fail)
    assert pkg.props(1) == {} and pkg.props(1) == {}
    assert len(pkg.issues) == 1 and pkg.failed_props == {1}
    pkg._props, pkg.failed_props, pkg.issues = {}, set(), []

    def partial(export):
        B.record_issue(pkg.issues, "properties", export.object_name, "property stream stopped early")
        return [], 0

    pkg.reader.export_stream = partial
    assert pkg.props(1) == {} and pkg.failed_props == {1}


def test_data_failure_defaults_unknown():
    with _scratch() as tmp:
        root = Path(tmp)
        path = root / "Data.uasset"
        path.write_bytes(b"")
        result = NS(summary=NS(), export_map=[NS(object_name="Data")], all_objects=[])
        ctx = NS(issues=[])

        class Reader:
            def __init__(self, *args):
                self.r, self.issues = result, ctx.issues

            def export_stream(self, export):
                B.record_issue(self.issues, "properties", export.object_name, ValueError("data failure"))
                return [], 0

            def close(self):
                pass

        module = ModuleType("uasset_read.parse_uasset")
        module.parse_uasset_with_linker = lambda *a, **k: result
        with ExitStack() as stack:
            _reader_setup(stack)
            stack.enter_context(patch.dict(sys.modules, {"uasset_read.parse_uasset": module}))
            stack.enter_context(patch.object(B, "Ctx", return_value=ctx))
            stack.enter_context(patch.object(R, "TaggedReader", Reader))
            data = R.read_data_asset(str(path), "/Game/Data", "DataAsset")
        assert data["summary"]["issues"] and data["summary"]["parse_status"] == "partial"
        assert "defaults are unknown" in data["markdown"] and "everything is at its class defaults" not in data["markdown"]
        assert "everything decoded cleanly" not in _index(root, data={"/Game/Data": data})
        _write_digest(root, data={"/Game/Data": data["summary"]})
        assert any("unexpected parse issue" in e for e in regress.check(_fixture(), root))


def test_regress_checks_non_blueprint_failures():
    with _scratch() as tmp:
        root = Path(tmp)
        (root / "INDEX.md").write_text("Coverage: 0 Blueprints rendered, 0 failed; graph nodes decoded 0/0", encoding="utf-8")
        for key in ("data_failures", "map_failures"):
            _write_digest(root, **{key: {"/Game/Broken": "read failed"}})
            assert any(key in e for e in regress.check(_fixture(), root))
        _write_digest(root, lfs={"failed": 1})
        assert any("LFS downloads failed" in e for e in regress.check(_fixture(), root))
        _write_digest(root, data_assets=None)
        assert any("invalid data_assets" in e for e in regress.check(_fixture(), root))


def test_native_struct_not_probed_as_tags():
    for size in (8, 16):
        reader = R.TaggedReader.__new__(R.TaggedReader)
        reader.ar = io.BytesIO(b"\0" * size + b"NEXT")
        reader.names, reader.issues = ["SavedViewOffset"], []

        def forbidden(*args, **kwargs):
            raise AssertionError("native vector was parsed as property tags")

        reader._read_tag = forbidden
        tag = NS(struct_type="DeprecateSlateVector2D", size=size, value_start_offset=0, value_end_offset=size)
        value = reader._tagged_struct(tag, 0)
        assert isinstance(value, dict), "native payload was not preserved"
        assert value["kind"] == "binary_or_native_property" and value["raw_data"] == b"\0" * size
        assert reader.ar.read() == b"NEXT" and not reader.issues
