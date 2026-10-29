"""Saved native type bytes and declaration presence tested independently of display."""
import struct
from types import SimpleNamespace as NS
from unittest.mock import patch

import declaration_ir as I
import data_reader as D


class Context:
    name_map = ["None", "object", "real", "double", "string", "Field", "bool"]
    issues = []
    r = NS(all_objects=[])

    def __init__(self):
        self.issues = []

    def fname(self, i, n):
        return self.name_map[i] + (f"_{n - 1}" if n else "")

    def obj(self, i):
        return NS(path="/Script/Engine.Actor") if i == -1 else None

    def full_name(self, obj):
        return obj.path


def summary():
    return NS(file_version_ue4=522, file_version_ue5=1018, custom_versions=[NS(guid=I._FRAMEWORK, version=37),
              NS(guid=I._RELEASE, version=44), NS(guid=I._UE5, version=68)])


def raw_type(container=0):
    value = struct.pack("<iiiiiB", 1, 0, 0, 0, -1, container)
    if container == 3:
        value += struct.pack("<iiiiiiii", 2, 0, 3, 0, 0, 1, 0, 0)
    # Main flags, member parent/name/GUID, const, wrapper, single precision.
    return value + struct.pack("<iii", 1, 0, 0) + struct.pack("<ii", 5, 1) + bytes(16) + struct.pack("<iii", 1, 0, 1)


def test_declaration_native_type_decodes_map_object_flags_and_exact_bytes():
    for container in (0, 1, 2, 3):
        raw = raw_type(container)
        result = I.decode_pin_type(Context(), raw, summary())
        assert result["category"] == "object" and result["object_index"] == -1
        assert result["object_path"] == "/Script/Engine.Actor" and result["container"] == container
        assert result["is_reference"] is True and result["is_const"] is True
        assert result["is_weak_pointer"] is False and result["serialize_single_precision"] is True
        assert result["member_reference"]["name"] == "Field_0"
        assert result["raw_hex"] == raw.hex()
        if container == 3:
            assert result["terminal"]["category"] == "real" and result["terminal"]["subcategory"] == "double"
            assert result["terminal"]["is_const"] is True and result["terminal"]["object_path"] is None
        else:
            assert result["terminal"]["status"] == "unknown", "non-map native defaults inferred"


def test_declaration_native_type_rejects_truncation_bad_names_flags_and_extra_bytes():
    raw = raw_type(3)
    for size in range(len(raw)):
        assert I.decode_pin_type(Context(), raw[:size], summary())["status"] == "unknown"
    corruptions = [raw + b"\0", struct.pack("<i", 1000) + raw[4:], raw[:20] + b"\x04" + raw[21:],
                   raw[:53] + struct.pack("<i", 2) + raw[57:]]
    for value in corruptions:
        result = I.decode_pin_type(Context(), value, summary())
        assert result["status"] == "unknown" and result["raw_hex"] == value.hex()
    result = I.decode_pin_type(Context(), raw_type(), NS(file_version_ue4=522, custom_versions=[]))
    assert result["status"] == "unknown" and "gates" in result["reason"]
    assert I.reference(Context(), -999)["status"] == "unknown"
    assert I.reference(Context(), True)["status"] == "unknown"
    assert I.reference(Context(), 0) is None
    class ObjectIndex(int):
        pass
    assert I.reference(Context(), ObjectIndex(-1)) == "/Script/Engine.Actor"
    unresolved = raw_type()[:16] + struct.pack("<i", -999) + raw_type()[20:]
    assert I.decode_pin_type(Context(), unresolved, summary())["object_path"]["status"] == "unknown"
    context = Context()
    ambiguous = NS(object_name="Actor", path="/Script/Engine.Actor", get_full_name=lambda: "/Script/Engine.Actor")
    context.r = NS(all_objects=[ambiguous, ambiguous])
    assert I.reference(context, {"object_name": "Actor", "full_name": "/Script/Engine.Actor"})["status"] == "unknown"


def build(props, kind="WidgetBlueprint", fail=False):
    class Reader:
        closed = False
        def __init__(self, *args):
            pass
        def export_stream(self, exp):
            if fail:
                raise ValueError("damaged tagged stream")
            return list(props.items()) if isinstance(props, dict) else props, 0
        def close(self):
            Reader.closed = True
    result = NS(summary=summary(), export_map=[NS(object_name="BP")])
    with patch.object(D, "TaggedReader", Reader):
        value = I.build_declaration_ir("unused", result, Context(), NS(object_name="BP"), kind)
    assert Reader.closed
    return value


def test_declaration_presence_never_infers_empty_defaults_flags_or_binding_kind():
    absent = build({})
    for key in ("variables", "function_graphs", "widget_bindings", "parent_class"):
        assert absent[key]["status"] == "unknown"
        assert absent["saved_fields"][key] == "absent"
    explicit = build({"NewVariables": [], "FunctionGraphs": [], "Bindings": [], "ParentClass": 0})
    assert explicit["status"] == "complete"
    assert explicit["variables"] == explicit["function_graphs"] == explicit["widget_bindings"] == []
    assert explicit["parent_class"] is None
    var = {"VarName": "Saved", "VarType": {"raw_data": raw_type()}, "PropertyFlags": 0, "Category": "", "DefaultValue": ""}
    props = {"NewVariables": [{"fields": var}], "Bindings": [{"fields": {"ObjectName": "Text_0", "PropertyName": "Text",
             "FunctionName": "GetText", "Kind": 0}}]}
    value = build(props)
    assert value["variables"][0]["flags"] == "0" and value["variables"][0]["default_value"] == ""
    assert value["widget_bindings"][0]["kind"] == 0
    del var["PropertyFlags"]; del var["DefaultValue"]
    value = build(props)["variables"][0]
    assert value["flags"]["status"] == value["default_value"]["status"] == "unknown"
    assert value["saved_fields"]["default_value"] == "absent"
    assert build({}, "Blueprint")["widget_bindings"] is None
    assert build({}, "EditorUtilityWidgetBlueprint")["widget_bindings"]["status"] == "unknown"


def test_declaration_malformed_and_duplicate_records_preserve_unknown_and_stream_errors():
    context = Context()
    missing = I.build_declaration_ir("Map.umap", NS(), context, None, None)
    assert missing["status"] == "partial" and missing["variables"]["status"] == "unknown"
    assert not missing["issues"] and not context.issues, "an absent optional map Blueprint export became a parse failure"
    present_map = I.build_declaration_ir("Map.umap", NS(), context, NS(object_name="LevelScriptBlueprint"), "Blueprint")
    assert not present_map["issues"] and "outside" in present_map["variables"]["reason"]
    for value in ({"NewVariables": [{"fields": {"VarName": "A"}}] * 2}, {"NewVariables": [{}]},
                  {"NewVariables": b"opaque"}, {"Bindings": [{"fields": {"ObjectName": "A"}}]}):
        result = build(value)
        target = "widget_bindings" if "Bindings" in value else "variables"
        assert result[target]["status"] == "unknown" and result["status"] == "partial"
    assert build([("NewVariables", []), ("NewVariables", [])])["issues"]
    damaged = build({}, fail=True)
    assert damaged["issues"] and damaged["variables"]["status"] == "unknown"
    malformed = build({"NewVariables": [{"fields": {"VarName": "A", "VarType": {"raw_data": raw_type()[:-1]}}}]})
    assert malformed["issues"][0]["stage"] == "declaration_ir"
    fields = {"VarName": "A", "PropertyFlags": True}
    value = build({"NewVariables": [{"fields": fields}]})
    assert value["variables"][0]["flags"]["status"] == "unknown"


def test_declaration_reader_keeps_indices_and_rejects_duplicate_nested_fields():
    reader = object.__new__(D.TaggedReader)
    reader.ctx = NS(obj_name=lambda index: "ShortName")
    tag = NS(type="ObjectProperty")
    assert reader._resolve(tag, -1) == "ShortName"
    reader.preserve_object_indices = True
    assert reader._resolve(tag, -1) == -1
    assert reader._resolve(NS(type="ArrayProperty"), [1, 2]) == [1, 2]
    try:
        reader._field_dict([("VarName", "A"), ("VarName", "B")])
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate saved declaration field was overwritten")
