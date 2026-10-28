"""Q8: compact previews never drop entries silently — every display limit states the exact count.

Synthetic values only (no package needed). The point of each check is that a reader can tell
"this document does not show the value" apart from "the value is this" or "the value failed to parse".
"""
from __future__ import annotations

import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import bp_reader as B
import data_reader as R


class StructValue:  # class names matter: both readers dispatch on type(v).__name__
    def __init__(self, struct_type, fields):
        self.struct_type, self.fields = struct_type, fields


class MapValue:
    def __init__(self, entries):
        self.entries = entries


def _pairs(count, key="F"):
    return {f"{key}{i}": i for i in range(count)}


def test_blueprint_dict_and_struct_previews_mark_exact_missing_counts():
    # generic dict: 6 shown, nothing marked at the boundary
    assert B.fmt_value(_pairs(6, key="K")) == "{" + ", ".join(f"K{i}={i}" for i in range(6)) + "}"
    assert B.fmt_value(_pairs(7, key="K")) == "{" + ", ".join(f"K{i}={i}" for i in range(6)) + ", …(+1)}"
    assert B.fmt_value(_pairs(26, key="K")).endswith(", …(+20)}")
    # struct fields: 8 shown, both for decoded dicts and for parser struct objects
    eight = ", ".join(f"F{i}={i}" for i in range(8))
    assert B.fmt_value({"struct_type": "S", "fields": _pairs(8)}) == f"S{{{eight}}}"
    assert B.fmt_value({"struct_type": "S", "fields": _pairs(9)}) == f"S{{{eight}, …(+1)}}"
    assert B.fmt_value(StructValue("S", _pairs(9))) == f"S{{{eight}, …(+1)}}"
    assert B.fmt_value({"struct_type": "UnknownStruct", "fields": _pairs(10)}) == "{" + eight + ", …(+2)}"
    # empty / opaque struct rendering is unchanged (no entries exist, so no count)
    assert B.fmt_value({"struct_type": "UnknownStruct", "fields": {}}) == "<opaque>"
    assert B.fmt_value({"struct_type": "S", "fields": {}}) == "S{}"
    assert B.fmt_value({"kind": "binary_or_native_property", "struct_type": "Fancy"}) == "<Fancy>"
    # arrays keep their existing marker, written through the same helper
    assert B.fmt_value(list(range(8))) == "[" + ", ".join(str(i) for i in range(8)) + "]"
    assert B.fmt_value(list(range(9))).endswith(", …(+1)]")
    # nested: inner and outer are counted independently
    nested = B.fmt_value({"struct_type": "Outer", "fields": {"Inner": _pairs(7, key="K"), **_pairs(8)}})
    assert "Inner={K0=0, K1=1, K2=2, K3=3, K4=4, K5=5, …(+1)}" in nested
    assert nested.endswith("F6=6, …(+1)}")


def test_blueprint_previews_keep_literal_scalars_and_special_structs():
    fields = {"bFlag": False, "Count": 0, "Name": "", "Ratio": 0.0, "Missing": None, **_pairs(4)}
    shown = B.fmt_value({"struct_type": "S", "fields": fields})
    assert shown == "S{bFlag=false, Count=0, Name=, Ratio=0, Missing=None, F0=0, F1=1, F2=2, …(+1)}"
    # explicit false/0/empty are values, not omissions: the marker is the only "…" in the line
    assert shown.count("…") == 1
    # special compact native structs are rendered by their own branch, before any field limit
    vector = type("VectorValue", (), {})()
    vector.x, vector.y, vector.z = 1.0, 2.0, 3.5
    assert B.fmt_value(vector) == "(1, 2, 3.5)"
    text = type("TextValue", (), {})()
    text.source_string = "말 그대로"
    assert B.fmt_value(text) == '"말 그대로"'


def test_data_struct_previews_mark_exact_missing_counts():
    ten = ", ".join(f"F{i}={i}" for i in range(10))
    assert R._val(StructValue("Row", _pairs(10))) == f"Row{{{ten}}}"
    assert R._val(StructValue("Row", _pairs(11))) == f"Row{{{ten}, …(+1)}}"
    assert R._val({"struct_type": "Row", "fields": _pairs(11)}) == f"Row{{{ten}, …(+1)}}"
    assert R._val({"struct_type": "UnknownStruct", "fields": _pairs(12)}) == "{" + ten + ", …(+2)}"
    # UserDefinedStruct field names stay cleaned, and literal names are otherwise untouched
    assert R._val(StructValue("Row", {"Health_5_" + "A" * 32: 0, "bRaw_Name": False})) == "Row{Health=0, bRaw_Name=false}"
    # nested: outer is at its limit (10 fields) and stays unmarked while the inner struct is marked
    nested = R._val(StructValue("Outer", {"Inner": StructValue("Inner", _pairs(11)), **_pairs(9)}))
    assert nested.startswith("Outer{Inner={" + ten + ", …(+1)}")
    assert nested.count("…") == 1 and nested.endswith("F8=8}")
    # arrays and maps: entries past the limit and malformed entries inside it are both counted
    assert R._val(list(range(10))) == "[" + ", ".join(str(i) for i in range(10)) + "]"
    assert R._val(list(range(12))).endswith(", …(+2)]")
    assert R._val(MapValue([{"key": i, "value": i} for i in range(10)])).count("…") == 0
    assert R._val(MapValue([{"key": i, "value": i} for i in range(11)])).endswith(", …(+1)}")
    assert R._val(MapValue([{"key": 1, "value": 1}, "malformed entry"])) == "{1: 1, …(+1)}"
    # compact forms of well known structs are returned before any limit applies
    tag = StructValue("GameplayTag", {"TagName": "A.B", **_pairs(20)})
    assert R._val(tag) == "A.B"


def test_cdo_preview_counts_hidden_values_and_exclusions():
    props = {**{f"Tunable{i}": i for i in range(45)}, "Declared": 1, "UberGraphFrame": 2,
             "AnimGraphNode_Root": 3, "__Internal": 4, "Mesh": {"type": "export"},
             "Native": {"kind": "binary_or_native_property", "struct_type": "FancyNative"},
             "Blob": b"\x00\x01", "Pose": StructValue("AnimNode_Root", {"Pose": 0})}
    lines, info = B._cdo_entries(props, {"Declared"})
    assert info["tunable"] == len(lines) == 45
    # a declared variable is already in the Variables table and an internal key is filtered on purpose:
    # neither is a lost value, so neither may be counted as omitted
    assert info["declared"] == ["Declared"]
    assert sorted(info["internal"]) == ["AnimGraphNode_Root", "UberGraphFrame", "__Internal"]
    assert info["subobjects"] == ["Mesh"] and info["unrenderable"] == ["Native", "Blob", "Pose"]

    out = B._cdo_lines(props, {"Declared"})
    text = "\n".join(out)
    assert len(out) == 43 and out[:40] == lines[:40]
    assert out[40] == ("- …(+5) more stored values not printed (preview shows the first 40); "
                       "the rest were decoded but are unknown from this document, not defaults")
    assert out[41].startswith("- …(+3) stored values have no readable text here "
                              "(native/opaque data or unresolved references): Native, Blob, Pose")
    assert out[41].endswith("unknown here, not defaults")
    assert out[42] == ("- …(+1) default sub-objects are not expanded here (component/instanced defaults): Mesh")
    assert "Declared" not in text and "UberGraphFrame" not in text and "__Internal" not in text
    # full values are not available anywhere else yet, so the notes must not promise them
    assert "json" not in text.lower()

    # exactly at the limit nothing is marked
    exact = {f"Tunable{i}": i for i in range(40)}
    assert B._cdo_lines(exact, set()) == [f"- Tunable{i} = {i}" for i in range(40)]
    # long exclusion lists are themselves bounded with the same convention
    note = B._cdo_lines({f"Blob{i}": b"\x00" for i in range(8)}, set())[0]
    assert note.startswith("- …(+8) stored values have no readable text here")
    assert "Blob0, Blob1, Blob2, Blob3, Blob4, Blob5, …(+2)" in note


def test_cdo_keeps_literal_strings_that_only_look_like_opaque_markers():
    # a String property whose value happens to be "<literal>" or "AnimNode_Root" is a readable value:
    # it must be printed, and must not be counted or described as native/opaque data
    literals = {"Tooltip": "<literal>", "NodeName": "AnimNode_Root", "Empty": "", "Zero": 0, "Flag": False}
    lines, info = B._cdo_entries(literals, set())
    assert lines == ["- Tooltip = <literal>", "- NodeName = AnimNode_Root", "- Empty = ", "- Zero = 0",
                     "- Flag = false"]
    assert info["unrenderable"] == [] and B._cdo_lines(literals, set()) == lines
    assert "unknown" not in "\n".join(lines) and "…" not in "\n".join(lines)
    # the category itself still works for values whose kind really has no readable text
    opaque = {"Text": "<literal>", "Native": {"struct_type": "UnknownStruct", "fields": {}},
              "Anim": StructValue("AnimNode_Root", {"Pose": 0}), "Blob": b"\x00"}
    lines, info = B._cdo_entries(opaque, set())
    assert lines == ["- Text = <literal>"] and info["unrenderable"] == ["Native", "Anim", "Blob"]
    # an object reference we could not name is unresolved, not a value
    with patch.object(B, "_CUR_CTX", None):
        lines, info = B._cdo_entries({"Ref": B.ObjRef(5), "NoRef": B.ObjRef(0)}, set())
    assert lines == ["- NoRef = None"] and info["unrenderable"] == ["Ref"]


def test_cdo_without_any_printable_value_still_reports_what_is_missing():
    out = B._cdo_lines({"Declared": 1, "Mesh": {"type": "export"}, "Blob": b"\x00"}, {"Declared"})
    assert len(out) == 2 and not any(line.startswith("- Mesh") or line.startswith("- Blob") for line in out)
    assert "no readable text here" in out[0] and "not expanded here" in out[1]
    # nothing was lost here: a declared variable plus internal keys leave the section empty as before
    assert B._cdo_lines({"Declared": 1, "__Internal": 2, "UberGraphFrame": 3}, {"Declared"}) == []
    assert B._cdo_lines({}, set()) == []


def _render_blueprint(tmp, cdo_props, var_names=frozenset({"Declared"})):
    path = Path(tmp) / "BP_Thing.uasset"
    path.write_bytes(b"")
    cdo = object()
    result = NS(summary=NS(), blueprint=None, graphs=[])
    ctx = NS(issues=[], obj_name=lambda ref=None: "", full_name=lambda obj: "",
             props=lambda obj: cdo_props if obj is cdo else {},
             export_by_name=lambda name: cdo if name == "Default__BP_Thing_C" else None,
             export_by_ref=lambda *a, **k: None)
    with ExitStack() as stack:
        stack.enter_context(patch.object(B, "ensure_uasset_read"))
        stack.enter_context(patch.object(B, "_install_patches"))
        stack.enter_context(patch.object(B, "newer_format_note", return_value=""))
        for name, value in (("_parse", (result, (0, 0))), ("Ctx", ctx), ("_find_blueprint_object", (None, None)),
                            ("_components", []), ("_widget_tree", []), ("_timelines", []),
                            ("_variables", (["| Declared | int |"], set(var_names))), ("_variable_metadata", {})):
            stack.enter_context(patch.object(B, name, return_value=value))
        return B.read_blueprint(str(path), "/Game/BP_Thing")


def test_cdo_notice_reaches_blueprint_markdown_and_is_not_a_parse_failure():
    with tempfile.TemporaryDirectory() as tmp:
        unknown_only = _render_blueprint(tmp, {"Declared": 1, "Mesh": {"type": "export"}, "Blob": b"\x00\x01"})
        md = unknown_only["markdown"]
        # the section exists even though not one tunable row could be printed
        assert "## Class defaults (values stored in the CDO)" in md
        defaults = md.split("## Class defaults (values stored in the CDO)")[1]
        assert "no readable text here (native/opaque data or unresolved references): Blob" in defaults
        assert "default sub-objects are not expanded here (component/instanced defaults): Mesh" in defaults
        assert "Declared" not in defaults  # listed in the Variables table, not lost
        assert unknown_only["summary"]["parse_status"] == "ok" and not unknown_only["summary"]["issues"]

        capped = _render_blueprint(tmp, {f"Tunable{i}": i for i in range(45)}, var_names=frozenset())
        md = capped["markdown"]
        assert "- Tunable39 = 39" in md and "- Tunable40 = 40" not in md
        assert "…(+5) more stored values not printed" in md
        # a display limit is a preview notice, not a decoding problem
        assert capped["summary"]["parse_status"] == "ok" and not capped["summary"]["issues"]
        assert "Parse warnings" not in md
