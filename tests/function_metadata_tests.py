"""Saved function metadata: field presence, scoping, opaque fallback, truthful failures and rendering."""
import json
import struct
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import bp_reader as B
import data_reader as D
from failure_tests import _index


def context(fields):
    return NS(issues=[], props=lambda index: {"MetaData": {"fields": fields}})


def node(index=1):
    return NS(class_name="K2Node_FunctionEntry", _export_index=index, _export_object_name="K2Node_FunctionEntry_0", pins=[object()])


def extract(ctx):
    return B._function_metadata(ctx, node(), "unused.uasset", NS(), "Graph:Entry")


def test_function_metadata_fields_and_explicit_booleans():
    import data_reader as D
    # bCallInEditor is a stored BoolProperty; exercise both serialized bool values.
    for payload, expected in ((b"\x00", False), (b"\x01", True)):
        flag = struct.unpack("<?", payload)[0]
        ctx = context({"ToolTip": NS(source_string="좌측상단 인덱스"), "Category": NS(source_string="Tools|Grid"),
                       "bCallInEditor": flag})
        info = extract(ctx)
        assert info == {"category": "Tools|Grid", "tooltip": "좌측상단 인덱스", "call_in_editor": expected}
        assert not ctx.issues
    assert "call_in_editor" not in extract(context({"ToolTip": "saved tooltip"})), "absent bool was invented"
    assert extract(context({"Category": "", "ToolTip": ""})) == {"category": "", "tooltip": ""}
    assert B._function_metadata(NS(props=lambda index: {}, issues=[]), node(), "", NS(), "Entry") == {}
    assert B._function_metadata(NS(issues=[]), NS(), "", NS(), "Entry") == {}
    unreadable = D.UnreadableValue("TextProperty", ValueError("truncated text"))
    ctx = context({"Category": unreadable, "ToolTip": unreadable})
    info = extract(ctx)
    assert "category" not in info and "tooltip" not in info
    assert info["unreadable"] == ["Category", "ToolTip"] and len(ctx.issues) == 2
    literal = str(unreadable)
    assert extract(context({"Category": literal, "ToolTip": literal})) == {"category": literal, "tooltip": literal}


def test_function_metadata_comment_literals_preserve_text_safely():
    text = '한글 "quoted"\n```\nfunction Fake()\r\t\u2028```\u0085end\u2029' + "long " * 600
    comments = B._function_metadata_comments({"category": "Tools\nGrid", "tooltip": text, "call_in_editor": False}, "Entry")
    assert len(comments) == 2 and all(len(line.splitlines()) == 1 for line in comments)
    assert json.loads(comments[1].split(": ", 1)[1]) == text, "tooltip was truncated or changed"
    assert 'Category="Tools\\nGrid"; CallInEditor=false' in comments[0]
    assert "한글" in comments[1]
    assert B._function_metadata_comments({}, "Entry") == []


def test_function_metadata_opaque_fallback_uses_exact_export_and_closes():
    exports = [NS(object_name="K2Node_FunctionEntry_0"), NS(object_name="K2Node_FunctionEntry_0")]
    selected, closed = [], []
    ctx = NS(issues=[], props=lambda index: {"MetaData": {"kind": "binary_or_native_property", "raw_data": b"opaque"}})
    class Reader:
        def __init__(self, path, result, owner): pass
        def export_stream(self, export):
            selected.append(export)
            return [("MetaData", {"fields": {"Category": "SecondGraph", "bCallInEditor": True}})], 0
        def close(self): closed.append(True)
    with patch.object(D, "TaggedReader", Reader):
        info = B._function_metadata(ctx, node(2), "fixture", NS(export_map=exports), "SecondGraph:Entry")
    assert selected == [exports[1]] and closed == [True]
    assert info == {"category": "SecondGraph", "call_in_editor": True} and not ctx.issues
    class Broken(Reader):
        def export_stream(self, export): raise ValueError("metadata decode failed")
    with patch.object(D, "TaggedReader", Broken):
        info = B._function_metadata(ctx, node(2), "fixture", NS(export_map=exports), "SecondGraph:Entry")
    assert closed == [True, True] and info == {"unreadable": ["MetaData"]}
    assert ctx.issues[0]["stage"] == "function_metadata" and "decode failed" in ctx.issues[0]["message"]


def test_function_metadata_invalid_fields_never_become_false_defaults():
    ctx = context({"ToolTip": {"kind": "opaque"}, "Category": "Known", "bCallInEditor": "false"})
    info = extract(ctx)
    assert info["category"] == "Known" and "tooltip" not in info and "call_in_editor" not in info
    assert set(info["unreadable"]) == {"ToolTip", "bCallInEditor"}
    assert len(ctx.issues) == 2 and all(issue["stage"] == "function_metadata" for issue in ctx.issues)
    comments = "\n".join(B._function_metadata_comments(info, "Entry"))
    assert "unknown:" in comments and "CallInEditor=false" not in comments


def test_function_metadata_reaches_markdown_summary_and_parse_report():
    with tempfile.TemporaryDirectory() as tmp:
        root, entry = Path(tmp), node()
        path = root / "Test.uasset"
        path.write_bytes(b"")
        graph = NS(graph_name="Action", nodes=[entry], subgraphs=[])
        result = NS(summary=NS(), blueprint=None, graphs=[graph])
        original = "Do work GridWidth_18_EF302CA945656BC9DD62659509343FD0"
        for fields, partial in (({"Category": "Tools", "ToolTip": NS(source_string=original), "bCallInEditor": False}, False),
                                ({"ToolTip": {"kind": "opaque"}}, True)):
            ctx = context(fields)
            ctx.obj_name, ctx.export_by_name = lambda ref: "", lambda name: None
            renderer = NS(nodes=[entry], mode=lambda: "exec", var_refs={}, unused_events=[],
                          render_exec=lambda: ["function Action()", "  return true"])
            with ExitStack() as stack:
                for name, value in (("ensure_uasset_read", None), ("_install_patches", None), ("newer_format_note", ""),
                                    ("_parse", (result, (1, 1))), ("Ctx", ctx), ("_find_blueprint_object", (None, None)),
                                    ("_graph_key", "Action"), ("GraphRenderer", renderer), ("_components", []),
                                    ("_widget_tree", []), ("_timelines", []), ("_variables", ([], set())),
                                    ("_variable_metadata", {}), ("_cdo_lines", []),
                                    ("build_graph_ir", {"status": "complete", "schema_version": 1, "issues": []})):
                    stack.enter_context(patch.object(B, name, return_value=value))
                rendered = B.read_blueprint(str(path), "/Game/Test")
            metadata = rendered["summary"]["function_metadata"]
            assert len(metadata) == 1 and metadata[0]["graph"] == "Action"
            assert "function Action()\n  return true" in rendered["markdown"], "execution flow changed"
            assert rendered["summary"]["parse_status"] == ("partial" if partial else "ok")
            if partial:
                assert "unknown: ToolTip" in rendered["markdown"] and "Parse warnings" in rendered["markdown"]
                assert "everything decoded cleanly" not in _index(root, bps={"/Game/Test": rendered})
            else:
                assert metadata[0]["call_in_editor"] is False and "CallInEditor=false" in rendered["markdown"]
                assert 'Function tooltip [K2Node_FunctionEntry_0]: "' + original + '"' in rendered["markdown"]
                assert metadata[0]["tooltip"] == original, "author text was changed by struct-name cleanup"
