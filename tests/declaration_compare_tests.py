"""Hand-authored declaration observations against the real read_snapshot adapter.

Nothing here reads a package: the parser is replaced so that the public
``summary["declaration_ir"]`` contract itself is what the adapter is held to. The
native side is written out by hand in the editor bridge's shape, never generated
from the reader, so an agreeing comparison is not a comparison with itself.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "scripts"))
import compare_editor_oracle as C


# --------------------------------------------------------------- native (expected) observations

def native_terminal(category="None", subcategory="None", object_path=None, is_const=False, is_weak_pointer=False):
    return {"category": category, "subcategory": subcategory, "object_path": object_path,
            "is_const": is_const, "is_weak_pointer": is_weak_pointer}


def native_type(category="bool", subcategory="None", object_path=None, container=0,
                is_reference=False, is_const=False, is_weak_pointer=False, terminal=None):
    return {"category": category, "subcategory": subcategory, "object_path": object_path,
            "container": container, "is_reference": is_reference, "is_const": is_const,
            "is_weak_pointer": is_weak_pointer,
            "terminal": native_terminal() if terminal is None else terminal}


def native_variable(name="Health", var_type=None, flags="70385195482112", category="Default", default_value="100.0"):
    # 'guid' is written by the bridge and is excluded from the comparison; it must not leak into it.
    return {"name": name, "guid": "d0a1b2c3d4e5f60718293a4b5c6d7e8f",
            "type": native_type(category="real", subcategory="double") if var_type is None else var_type,
            "flags": flags, "category": category, "default_value": default_value}


def native_binding(object_name="Text_0", property_name="TextDelegate", function_name="GetTitleText", kind=0):
    return {"object_name": object_name, "property_name": property_name,
            "function_name": function_name, "kind": kind}


def native(**overrides):
    snapshot = {"asset_class": "Blueprint", "text_values": "source", "package_dirty": False,
                "parent_class": "/Script/Engine.Actor", "variables": [native_variable()],
                "function_graphs": ["/Game/한국어/BP.BP:Func_Heal"], "graphs": [],
                "widget_bindings": None, "issues": []}
    snapshot.update(overrides)
    return copy.deepcopy(snapshot)


# ------------------------------------------------------------------ reader declaration IR shape

def ir_terminal(**overrides):
    record = {"category": "None", "subcategory": "None", "object_path": None,
              "is_const": False, "is_weak_pointer": False,
              # Reader-only fields again: the terminal is compared on native names only.
              "object_index": 0, "is_uobject_wrapper": False}
    record.update(overrides)
    return record


def ir_type(**overrides):
    record = {"category": "real", "subcategory": "double", "object_path": None, "container": 0,
              "is_reference": False, "is_const": False, "is_weak_pointer": False,
              "terminal": ir_terminal(),
              # Reader-only fields the comparator has to drop rather than report as extra.
              "object_index": -7, "is_uobject_wrapper": False, "serialize_single_precision": False,
              "member_reference": {"parent_index": 0, "parent_path": None, "name": "None", "guid_raw": "00" * 16},
              "raw_hex": "0a0b0c", "saved_fields": {key: "saved" for key in C._TYPE_FIELDS}}
    record.update(overrides)
    return record


def ir_variable(**overrides):
    record = {"name": "Health", "type": ir_type(), "flags": "70385195482112",
              "category": "Default", "default_value": "100.0", "var_guid": "unused-by-the-comparison",
              "saved_fields": {key: "saved" for key in C._VARIABLE_FIELDS}}
    record.update(overrides)
    return record


def ir_binding(**overrides):
    record = {"object_name": "Text_0", "property_name": "TextDelegate",
              "function_name": "GetTitleText", "kind": 0,
              "saved_fields": {key: "saved" for key in C._BINDING_FIELDS}}
    record.update(overrides)
    return record


def declaration_ir(**overrides):
    ir = {"schema_version": 1, "basis": "saved-tagged-properties", "asset_path": "/Game/한국어/BP",
          "parent_class": "/Script/Engine.Actor", "variables": [ir_variable()],
          "function_graphs": ["/Game/한국어/BP.BP:Func_Heal"], "widget_bindings": None, "issues": []}
    ir.update(overrides)
    return ir


def unknown(reason="the saved property is absent"):
    """The reader IR's own unknown marker, which is not this adapter's marker."""
    return {"status": "unknown", "reason": reason}


# ------------------------------------------------------------------------------- the real adapter

def read(ir, *, asset_class="Blueprint", summary_issues=(), summary=None, tripwire=True):
    """C.read_snapshot with only the raw parser mocked, so the IR contract is what is exercised."""
    import bp_reader as B
    if summary is None:
        summary = {"graph_ir": {"schema_version": 1, "graphs": [], "issues": []},
                   "declaration_ir": ir, "issues": list(summary_issues)}
    ctx = SimpleNamespace(issues=[], obj=lambda index: None, full_name=lambda obj: "",
                          props=lambda obj: {})
    parsed = SimpleNamespace(graphs=[], all_objects=[], export_map=[])
    def refuse(*args, **kwargs):
        raise AssertionError("declarations must come from the public IR, not a second property read")
    with patch.object(B, "read_blueprint", lambda path, game_path: {"summary": summary}), \
            patch.object(B, "_parse", lambda path: (parsed, (0, 0))), \
            patch.object(B, "Ctx", lambda result: ctx), \
            patch.object(B, "_find_blueprint_object", lambda context, name: (object(), asset_class)), \
            patch.object(B, "_walk_graphs", lambda graphs, depth=0: []):
        if not tripwire:
            return C.read_snapshot("/nonexistent/한국어/BP.uasset", "/Game/한국어/BP")
        import data_reader as R
        with patch.object(R, "TaggedReader", refuse):
            return C.read_snapshot("/nonexistent/한국어/BP.uasset", "/Game/한국어/BP")


def compare(expected, ir, *, asset_class="Blueprint"):
    return C.compare_snapshots(expected, read(ir, asset_class=asset_class))


def paths(result, key="unavailable"):
    return [item["path"] for item in result[key]]


def refused(expected, actual_ir=None, *, asset_class="Blueprint"):
    """A comparison that cannot be trusted must raise, never return a clean result."""
    try:
        compare(expected, declaration_ir() if actual_ir is None else actual_ir, asset_class=asset_class)
    except C.OracleError:
        return True
    raise AssertionError("a malformed or ambiguous observation was compared anyway")


# ------------------------------------------------------------------------------------- the tests

def test_declaration_compare_consumes_the_public_api_without_reparsing():
    ir = declaration_ir()
    before = copy.deepcopy(ir)
    decoded = read(ir)
    assert ir == before, "the adapter mutated the reader's declaration IR"
    assert set(decoded) >= {"asset_class", "parent_class", "variables", "function_graphs",
                            "widget_bindings", "graphs", "issues"}
    assert decoded["variables"][0]["name"] == "Health" and "saved_fields" not in decoded["variables"][0]
    assert "saved_fields" not in decoded["variables"][0]["type"]
    assert set(decoded["variables"][0]["type"]) == set(C._TYPE_FIELDS) | {"terminal"}
    result = C.compare_snapshots(native(), decoded)
    assert result["checked"] >= 15 and not result["mismatches"] and not result["unavailable"], result
    # The same observations must still fail when a value really differs.
    for mutate in (lambda i: i.__setitem__("parent_class", "/Script/Engine.Pawn"),
                   lambda i: i["variables"][0].__setitem__("category", "Stats"),
                   lambda i: i["variables"][0].__setitem__("default_value", "1.0"),
                   lambda i: i["variables"][0].__setitem__("flags", "70385195482113"),
                   lambda i: i["variables"][0].__setitem__("name", "Mana"),
                   lambda i: i["variables"][0]["type"].__setitem__("subcategory", "float")):
        changed = declaration_ir()
        mutate(changed)
        assert compare(native(), changed)["mismatches"], mutate


def test_declaration_compare_missing_is_never_empty_or_default():
    # A whole collection the reader could not read stays unknown; '[]' is a different claim.
    for key, expected in (("variables", native(variables=[])),
                          ("function_graphs", native(function_graphs=[])),
                          ("widget_bindings", native(asset_class="WidgetBlueprint", widget_bindings=[]))):
        ir = declaration_ir(**{key: unknown(f"{key} was not saved")})
        result = compare(expected, ir, asset_class=expected["asset_class"])
        assert paths(result) == ["snapshot/" + key] and not result["mismatches"], (key, result)
        assert "not saved" in result["unavailable"][0]["reason"], result
    # An explicitly empty saved collection does compare, and disagrees with a populated one.
    empty = declaration_ir(variables=[], function_graphs=[])
    agreed = compare(native(variables=[], function_graphs=[]), empty)
    assert not agreed["mismatches"] and not agreed["unavailable"], agreed
    assert compare(native(), empty)["mismatches"], "an empty collection passed against declared members"
    # Individual absent fields stay unknown while the rest of the record is still compared.
    for field in ("default_value", "flags", "category", "type"):
        record = ir_variable(saved_fields={key: ("absent" if key == field else "saved")
                                           for key in C._VARIABLE_FIELDS})
        record.pop(field)
        result = compare(native(), declaration_ir(variables=[record]))
        assert paths(result) == [f"snapshot/variables/Health/{field}"], (field, result)
        assert not result["mismatches"] and result["checked"] > 0, (field, result)
    # Provenance alone decides: a value carried with 'absent' provenance is not a saved value.
    record = ir_variable(default_value="", saved_fields=dict({k: "saved" for k in C._VARIABLE_FIELDS},
                                                            default_value="absent"))
    result = compare(native(variables=[native_variable(default_value="")]), declaration_ir(variables=[record]))
    assert paths(result) == ["snapshot/variables/Health/default_value"] and not result["mismatches"], result
    # Collection-level provenance too: a concrete value the IR says was not saved cannot pass as saved,
    # and that includes a null parent class, which is otherwise a real observation.
    widget_native = native(asset_class="WidgetBlueprint", widget_bindings=[native_binding()])
    for name, value, expected, asset_class in (
            ("variables", [ir_variable()], native(), "Blueprint"),
            ("variables", [], native(variables=[]), "Blueprint"),
            ("function_graphs", ["/Game/한국어/BP.BP:Func_Heal"], native(), "Blueprint"),
            ("function_graphs", [], native(function_graphs=[]), "Blueprint"),
            ("parent_class", "/Script/Engine.Actor", native(), "Blueprint"),
            ("parent_class", None, native(parent_class=None), "Blueprint"),
            ("widget_bindings", [ir_binding()], widget_native, "WidgetBlueprint"),
            ("widget_bindings", None, widget_native, "WidgetBlueprint")):
        for state in ("absent", "unknown", "guessed"):
            ir = declaration_ir(**{name: value}, saved_fields={name: state})
            result = compare(expected, ir, asset_class=asset_class)
            assert paths(result) == ["snapshot/" + name], (name, value, state, result)
            assert not result["mismatches"], (name, value, state, result)
    # The one exemption: a non-widget Blueprint has no binding list to save, so null is applicability.
    ir = declaration_ir(saved_fields={"variables": "saved", "parent_class": "saved",
                                      "function_graphs": "saved", "widget_bindings": "absent"})
    result = compare(native(), ir)
    assert not result["unavailable"] and not result["mismatches"], result
    # The saved bytes carry no terminal type for a non-map declaration; the native default is not assumed.
    non_map = ir_type(terminal=unknown("terminal type not serialized for a non-map declaration"))
    result = compare(native(), declaration_ir(variables=[ir_variable(type=non_map)]))
    assert paths(result) == ["snapshot/variables/Health/type/terminal"] and not result["mismatches"], result


def test_declaration_compare_duplicate_or_malformed_identity_is_not_a_partial_list():
    # Our side: no record is dropped, so the collection as a whole becomes unknown.
    for variables in ([ir_variable(), ir_variable()],
                      [ir_variable(name=unknown("variable name not decoded"))],
                      [ir_variable(name="")],
                      [ir_variable(name=None)],
                      [{"type": ir_type()}],
                      ["not a record"],
                      {"Health": ir_variable()}):
        result = compare(native(), declaration_ir(variables=variables))
        assert paths(result) == ["snapshot/variables"] and not result["mismatches"], variables
    bindings = [ir_binding(), ir_binding(function_name="GetOtherText")]
    result = compare(native(asset_class="WidgetBlueprint", widget_bindings=[native_binding()]),
                     declaration_ir(widget_bindings=bindings), asset_class="WidgetBlueprint")
    assert paths(result) == ["snapshot/widget_bindings"] and not result["mismatches"], result
    # The native side is refused outright rather than silently deduplicated or coerced.
    refused(native(variables=[native_variable(), native_variable()]))
    refused(native(variables=[native_variable(name=5)]))
    refused(native(variables=[native_variable(name="")]))
    refused(native(variables=[native_variable(flags="0x10")]))
    refused(native(variables=[native_variable(flags=0)]))
    refused(native(variables=[{"name": "Health"}]))
    refused(native(variables={"Health": native_variable()}))
    refused(native(function_graphs=["Func_Heal"]))
    refused(native(function_graphs="/Game/한국어/BP.BP:Func_Heal"))
    refused(native(asset_class="WidgetBlueprint", widget_bindings=[native_binding(), native_binding()]),
            asset_class="WidgetBlueprint")
    refused(native(asset_class="WidgetBlueprint", widget_bindings=[native_binding(kind=True)]),
            asset_class="WidgetBlueprint")
    refused(native(asset_class="WidgetBlueprint", widget_bindings=[native_binding(kind="Function")]),
            asset_class="WidgetBlueprint")


def test_declaration_compare_structured_types_and_unknown_leaves():
    key = native_terminal(category="struct", subcategory="None", object_path="/Script/CoreUObject.Vector")
    map_native = native_type(category="struct", subcategory="None",
                             object_path="/Script/Engine.LinearColor", container=2, terminal=key)
    map_ir = ir_type(category="struct", subcategory="", object_path="/Script/Engine.LinearColor",
                     container=2, terminal=ir_terminal(category="struct", object_path="/Script/CoreUObject.Vector"))
    expected = native(variables=[native_variable(name="Colors", var_type=map_native)])
    agreed = compare(expected, declaration_ir(variables=[ir_variable(name="Colors", type=map_ir)]))
    assert not agreed["mismatches"] and not agreed["unavailable"], agreed
    # Every structured leaf is compared, including the terminal (map key) flags.
    for mutate in (lambda t: t.__setitem__("container", 1),
                   lambda t: t.__setitem__("container", True),
                   lambda t: t.__setitem__("object_path", "/Script/Engine.Color"),
                   lambda t: t.__setitem__("is_reference", True),
                   lambda t: t.__setitem__("is_const", 0),
                   lambda t: t["terminal"].__setitem__("object_path", "/Script/CoreUObject.Rotator"),
                   lambda t: t["terminal"].__setitem__("is_const", True),
                   lambda t: t["terminal"].__setitem__("is_weak_pointer", True)):
        changed = copy.deepcopy(map_ir)
        mutate(changed)
        result = compare(expected, declaration_ir(variables=[ir_variable(name="Colors", type=changed)]))
        assert result["mismatches"], mutate
    # Unknown leaves stay unknown: no empty terminal, no fabricated object path, no pass.
    for override, where in (({"object_path": unknown("object index unresolved")}, "type/object_path"),
                            ({"container": unknown("container type absent")}, "type/container"),
                            ({"terminal": unknown("terminal not decoded")}, "type/terminal"),
                            ({"terminal": None}, "type/terminal")):
        type_record = copy.deepcopy(map_ir)
        type_record.update(override)
        result = compare(expected, declaration_ir(variables=[ir_variable(name="Colors", type=type_record)]))
        assert not result["mismatches"], (where, result)
        assert paths(result) == [f"snapshot/variables/Colors/{where}"], (where, result)
    # A half-projected terminal keeps its decoded leaf and reports the rest as unknown.
    type_record = copy.deepcopy(map_ir)
    type_record["terminal"] = {"category": "struct"}
    result = compare(expected, declaration_ir(variables=[ir_variable(name="Colors", type=type_record)]))
    assert not result["mismatches"], result
    assert paths(result) == [f"snapshot/variables/Colors/type/terminal/{leaf}" for leaf in
                             ("is_const", "is_weak_pointer", "object_path", "subcategory")], result
    # A type that is not a decoded record is unknown as a whole, not an empty type.
    for opaque in (unknown("variable type is an opaque blob"), "float", 7, None, []):
        result = compare(expected, declaration_ir(variables=[ir_variable(name="Colors", type=opaque)]))
        assert paths(result) == ["snapshot/variables/Colors/type"] and not result["mismatches"], opaque
    # An unknown terminal must not hide the rest of the record from comparison.
    type_record = copy.deepcopy(map_ir)
    type_record["terminal"] = unknown("terminal not decoded")
    result = compare(expected, declaration_ir(variables=[ir_variable(
        name="Colors", default_value="wrong", type=type_record)]))
    assert paths(result) == ["snapshot/variables/Colors/type/terminal"], result
    assert paths(result, "mismatches") == ["snapshot/variables/Colors/default_value"], result


def test_declaration_compare_binding_kind_and_function_graph_changes():
    widget = native(asset_class="WidgetBlueprint", widget_bindings=[native_binding()])
    ir = declaration_ir(widget_bindings=[ir_binding()])
    agreed = compare(widget, ir, asset_class="WidgetBlueprint")
    assert agreed["checked"] >= 4 and not agreed["mismatches"] and not agreed["unavailable"], agreed
    for mutate in (lambda i: i["widget_bindings"][0].__setitem__("kind", 1),
                   lambda i: i["widget_bindings"][0].__setitem__("kind", "0"),
                   lambda i: i["widget_bindings"][0].__setitem__("function_name", "GetOther"),
                   lambda i: i["widget_bindings"][0].__setitem__("property_name", "ToolTipDelegate"),
                   lambda i: i["widget_bindings"][0].__setitem__("object_name", "Text_1"),
                   lambda i: i["widget_bindings"].append(ir_binding(property_name="ColorDelegate")),
                   lambda i: i["widget_bindings"].clear()):
        changed = declaration_ir(widget_bindings=[ir_binding()])
        mutate(changed)
        assert compare(widget, changed, asset_class="WidgetBlueprint")["mismatches"], mutate
    # A widget that reports no binding list at all is unknown, not an agreement with null.
    result = compare(widget, declaration_ir(widget_bindings=None), asset_class="WidgetBlueprint")
    assert paths(result) == ["snapshot/widget_bindings"] and not result["mismatches"], result
    # A non-widget Blueprint has no binding list; an empty list is a different answer.
    assert not compare(native(), declaration_ir())["mismatches"]
    assert compare(native(), declaration_ir(widget_bindings=[]))["mismatches"], "[] passed as native null"
    # Function graph declarations: separator normalization agrees, membership changes do not.
    assert not compare(native(), declaration_ir(function_graphs=["/Game/한국어/BP.BP.Func_Heal"]))["mismatches"]
    for declared in ([], ["/Game/한국어/BP.BP:Func_Hurt"],
                     ["/Game/한국어/BP.BP:Func_Heal", "/Game/한국어/BP.BP:Func_Hurt"]):
        assert compare(native(), declaration_ir(function_graphs=declared))["mismatches"], declared
    for declared in (["Func_Heal"], ["/Game/한국어/BP.BP:Func_Heal", "/Game/한국어/BP.BP.Func_Heal"],
                     [unknown("graph reference unresolved")], "not a list"):
        result = compare(native(), declaration_ir(function_graphs=declared))
        assert paths(result) == ["snapshot/function_graphs"] and not result["mismatches"], declared
    for parent in (unknown("ParentClass unresolved"), "Actor", 7):
        result = compare(native(), declaration_ir(parent_class=parent))
        assert paths(result) == ["snapshot/parent_class"] and not result["mismatches"], parent
    assert compare(native(parent_class=None), declaration_ir(parent_class=None))["checked"] > 0


def test_declaration_compare_editor_utility_widget_bindings_are_not_optional():
    # The native bridge casts to UWidgetBlueprint, which this subclass is: it always reports a list.
    kind = "EditorUtilityWidgetBlueprint"
    expected = native(asset_class=kind, widget_bindings=[native_binding()])
    for overrides in ({"widget_bindings": None},
                      {"widget_bindings": None, "saved_fields": {"widget_bindings": "absent"}},
                      {"widget_bindings": None, "saved_fields": {"widget_bindings": "saved"}},
                      {"widget_bindings": unknown("saved field Bindings absent")}):
        result = compare(expected, declaration_ir(**overrides), asset_class=kind)
        assert paths(result) == ["snapshot/widget_bindings"], (overrides, result)
        assert not result["mismatches"], (overrides, result)
    agreed = compare(expected, declaration_ir(widget_bindings=[ir_binding()]), asset_class=kind)
    assert not agreed["mismatches"] and not agreed["unavailable"], agreed
    assert compare(expected, declaration_ir(widget_bindings=[]), asset_class=kind)["mismatches"]


def test_declaration_compare_native_declaration_shapes_are_validated_not_trusted():
    widget = lambda bindings: native(asset_class="WidgetBlueprint", widget_bindings=bindings)
    bad_terminal = native_terminal()
    del bad_terminal["is_weak_pointer"]
    # native_type() substitutes a valid terminal for None, so these two are built then broken,
    # and asserted broken: a 'malformed' case that quietly becomes valid tests nothing.
    null_terminal, no_terminal = native_type(), native_type()
    null_terminal["terminal"] = None
    del no_terminal["terminal"]
    assert null_terminal["terminal"] is None and "terminal" not in no_terminal
    for snapshot in (
            # Malformed collections and records.
            native(variables={"Health": native_variable()}),
            native(variables=[["Health"]]),
            native(variables=[{"name": "Health"}]),
            native(function_graphs=None),
            native(function_graphs=[7]),
            native(function_graphs=["Func_Heal"]),
            widget({"Text_0": native_binding()}),
            widget([None]),
            widget([{"object_name": "Text_0"}]),
            # Missing or duplicated identities.
            native(variables=[native_variable(), native_variable()]),
            native(variables=[native_variable(name="")]),
            native(variables=[native_variable(name=None)]),
            native(variables=[native_variable(name=5)]),
            widget([native_binding(), native_binding()]),
            widget([native_binding(object_name="")]),
            widget([native_binding(property_name=None)]),
            # Binding kinds outside EBindingKind, including a bool masquerading as one.
            widget([native_binding(kind=2)]),
            widget([native_binding(kind=-1)]),
            widget([native_binding(kind=True)]),
            widget([native_binding(kind=1.0)]),
            widget([native_binding(kind="Function")]),
            widget([native_binding(kind=None)]),
            # Flags that are not the bridge's canonical uint64 decimal string.
            native(variables=[native_variable(flags="18446744073709551616")]),
            native(variables=[native_variable(flags="007")]),
            native(variables=[native_variable(flags="-1")]),
            native(variables=[native_variable(flags="")]),
            native(variables=[native_variable(flags="0x10")]),
            native(variables=[native_variable(flags=True)]),
            native(variables=[native_variable(flags=70385195482112)]),
            # Declaration types: wrong kinds, impossible containers, half-written terminals.
            native(variables=[native_variable(var_type="float")]),
            native(variables=[native_variable(var_type=native_type(container=4))]),
            native(variables=[native_variable(var_type=native_type(container=True))]),
            native(variables=[native_variable(var_type=native_type(is_const=1))]),
            native(variables=[native_variable(var_type=native_type(object_path=7))]),
            native(variables=[native_variable(var_type=null_terminal)]),
            native(variables=[native_variable(var_type=no_terminal)]),
            native(variables=[native_variable(var_type=native_type(terminal=bad_terminal))]),
            native(variables=[native_variable(var_type=native_type(
                terminal=native_terminal(is_const=1)))])):
        refused(snapshot)
    # The canonical boundary values themselves are accepted.
    for flags in ("0", "18446744073709551615"):
        agreed = compare(native(variables=[native_variable(flags=flags)]),
                         declaration_ir(variables=[ir_variable(flags=flags)]))
        assert not agreed["mismatches"] and not agreed["unavailable"], flags
    for kind in (0, 1):
        agreed = compare(widget([native_binding(kind=kind)]),
                         declaration_ir(widget_bindings=[ir_binding(kind=kind)]),
                         asset_class="WidgetBlueprint")
        assert not agreed["mismatches"] and not agreed["unavailable"], kind


def test_declaration_compare_unsupported_or_missing_ir_fails_closed():
    for overrides in ({"schema_version": 2}, {"schema_version": True}, {"schema_version": "1"},
                      {"basis": "rendered-markdown"}, {"basis": None}):
        ir = declaration_ir(**overrides)
        try:
            read(ir)
        except C.OracleError:
            continue
        raise AssertionError(f"an unsupported declaration IR was consumed anyway: {overrides}")
    for summary in ({"graph_ir": {"graphs": [], "issues": []}, "issues": []},
                    {"graph_ir": {"graphs": [], "issues": []}, "declaration_ir": None, "issues": []},
                    {"graph_ir": {"graphs": [], "issues": []}, "declaration_ir": [], "issues": []}):
        try:
            read(declaration_ir(), summary=summary)
        except C.OracleError:
            continue
        raise AssertionError("a reader without the declaration API was treated as comparable")
    # Projection problems the IR reports itself must reach the report as decoder gaps.
    decoded = read(declaration_ir(issues=[{"stage": "declaration_ir", "message": "variables not decoded"}]))
    assert decoded["issues"], "declaration IR issues were dropped"
    assert read(declaration_ir(issues="broken"))["issues"], "a malformed issues field was ignored"
    assert not read(declaration_ir())["issues"]


def test_declaration_compare_report_is_incomplete_rather_than_passed():
    with tempfile.TemporaryDirectory(prefix="declaration-한글 ") as tmp:
        root = Path(tmp)
        package = root / "Content/한국어/BP.uasset"
        package.parent.mkdir(parents=True)
        package.write_bytes(b"independent bytes; not a real Unreal package")
        sha = hashlib.sha256(package.read_bytes()).hexdigest()
        oracle = {"schema_version": 1, "producer": "unreal-editor-native", "engine_version": "5.8.4-test",
                  "project_file": "D:/another machine/Project.uproject", "issues": [],
                  "assets": [{"asset_path": "/Game/한국어/BP", "package_file": "Content/한국어/BP.uasset",
                              "sha256_before": sha, "sha256_after": sha, "snapshot": native(), "issues": []}]}
        agreed = read(declaration_ir())
        report = C.compare_oracle(oracle, root, reader=lambda *_: agreed)
        assert report["status"] == "passed" and report["checked"] >= 15, report
        for ir in (declaration_ir(variables=unknown("NewVariables was not saved")),
                   declaration_ir(variables=[ir_variable(), ir_variable()]),
                   declaration_ir(function_graphs=[unknown("unresolved")])):
            decoded = read(ir)
            report = C.compare_oracle(oracle, root, reader=lambda *_: decoded)
            assert report["status"] == "incomplete", (ir, report)
        decoded = read(declaration_ir(variables=[ir_variable(category="Stats")]))
        report = C.compare_oracle(oracle, root, reader=lambda *_: decoded)
        assert report["status"] == "mismatch", report
        # A refused native observation is a reported gap for that asset, never a pass.
        for variables, bindings in (([native_variable(), native_variable()], None),
                                    ([native_variable(flags="18446744073709551616")], None),
                                    ([native_variable(name="")], None),
                                    ([native_variable(var_type=native_type(container=4))], None),
                                    ([], [native_binding(kind=2)]),
                                    ([], [native_binding(kind=True)]),
                                    ([], {"Text_0": native_binding()})):
            broken = copy.deepcopy(oracle)
            broken["assets"][0]["snapshot"].update(variables=variables, widget_bindings=bindings)
            report = C.compare_oracle(broken, root, reader=lambda *_: agreed)
            assert report["status"] == "incomplete", (variables, bindings, report)
            assert report["assets"][0]["unavailable"] and not report["assets"][0]["mismatches"], report
            assert report["checked"] == 0, report
        assert json.dumps(report, ensure_ascii=False, allow_nan=False)
        assert any("declaration" in text.casefold() for text in report["exclusions"]), report["exclusions"]
