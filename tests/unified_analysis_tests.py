"""Independent counterexamples for the additive cross-language analysis IR."""
from __future__ import annotations

import unified_analysis as U


def _span(byte=0, line=1):
    return {"byte_start": byte, "byte_end": byte + 4, "line_start": line, "column_start": 1,
            "line_end": line, "column_end": 5}


def _type(identity, name, *, kind="UCLASS", base=None, file=None):
    return {"id": identity, "symbol_name": name, "qualified_name": name, "kind": kind,
            "source_file": file or f"Source/Game/{name}.h", "source_span": _span(),
            "bases": ([{"name": base, "access": "public", "resolution_status": "unresolved", "issues": []}]
                      if base else []), "parser": "tree-sitter-cpp", "resolution_status": "syntax_observed", "issues": []}


def _function(identity, owner, name, params="()", *, annotation="UFUNCTION(BlueprintCallable)", definition=False,
              signature=None):
    return {"id": identity, "symbol_name": name, "qualified_name": owner + "::" + name, "owner": owner,
            "source_file": f"Source/Game/{owner}.{'cpp' if definition else 'h'}", "source_span": _span(),
            "declaration_kind": "definition" if definition else "declaration", "signature_raw": signature or name + params,
            "parameters_raw": params, "return_prefix_raw": "void", "body_span": _span() if definition else None,
            "annotation": ({"raw": annotation} if annotation else None), "resolution_status": "syntax_observed", "issues": []}


def _field(identity, owner, name):
    return {"id": identity, "symbol_name": name, "qualified_name": owner + "::" + name, "owner": owner,
            "source_file": f"Source/Game/{owner}.h", "source_span": _span(), "declaration_raw": "int " + name + ";",
            "annotation": {"raw": "UPROPERTY(BlueprintReadWrite)"}, "resolution_status": "syntax_observed", "issues": []}


def _reference(kind, parent, name, *, guid="good", status="complete", self_context=False):
    return {"kind": kind, "source_property": kind.title() + "Reference",
            "saved_fields": {"parent": "saved", "name": "saved", "guid": "saved", "self_context": "saved"},
            "parent": {"package_index": -1, "object_path": parent}, "name": name,
            "guid": {"encoding": "decoder-text", "value": guid}, "self_context": self_context, "status": status}


def _blueprint(asset, parent, nodes, *, graph_name="DoThing", graph_status="complete", declaration_status="complete",
               variables=None):
    graph_id = asset + "." + asset.rsplit("/", 1)[-1] + "." + graph_name
    return {"kind": "Blueprint", "parent": parent.rsplit(".", 1)[-1], "interfaces": [], "issues": [],
            "graph_ir": {"schema_version": 1, "status": graph_status, "graphs": [
                {"id": graph_id, "name": graph_name, "guid_raw": "graph-guid", "nodes": nodes}]},
            "declaration_ir": {"schema_version": 1, "status": declaration_status,
                               "parent_class": parent, "variables": variables or [], "issues": []}}


def _node(identity, references=None, pins=None, cls="K2Node_CallFunction"):
    return {"id": identity, "object_name": identity.rsplit("/", 1)[-1], "object_path": identity,
            "class": cls, "pins": pins or [], "semantic_references": references or []}


def _cpp(types=None, functions=None, fields=None, calls=None, status="ok", links=None, accesses=None):
    return {"precision": {"schema_version": 1, "status": status, "types": types or [],
                          "functions": functions or [], "fields": fields or [], "calls": calls or [],
                          "data_accesses": accesses or [], "unreal_function_links": links or []}}


def _relations(index, kind):
    return [item for item in index["relations"] if item["reference_kind"] == kind]


def test_unified_exact_native_path_stays_candidate_and_overloads_are_ambiguous():
    types = [_type("type:actor", "AActor")]
    functions = [_function("fn:int", "AActor", "Run", "(int Value)"),
                 _function("fn:float", "AActor", "Run", "(float Value)")]
    reference = _reference("function", "/Script/Game.Actor", "Run", guid="wrong-but-well-formed")
    entry = _node("/Game/BP_Actor:Entry", pins=[
        {"id": "entry:input", "pin_name": "Input", "direction": 1, "type": {"pin_category": "int"}}],
        cls="K2Node_FunctionEntry")
    result_node = _node("/Game/BP_Actor:Result", pins=[
        {"id": "result:out", "pin_name": "OutValue", "direction": 0, "type": {"pin_category": "int"}},
        {"id": "result:return", "pin_name": "ReturnValue", "direction": 0, "type": {"pin_category": "bool"}}],
        cls="K2Node_FunctionResult")
    macro = {"kind": "macro_graph", "source_property": "MacroGraphReference", "status": "complete",
             "value": {"package_index": -1,
                       "object_path": "/Engine/EditorBlueprintResources/StandardMacros.StandardMacros.IsValid"}}
    bp = _blueprint("/Game/BP_Actor", "/Script/Game.Actor",
                    [entry, _node("/Game/BP_Actor:Call", [reference, macro]), result_node])
    result = U.build_unified_analysis(_cpp(types, functions), {"/Game/BP_Actor": bp})
    parent = _relations(result, "blueprint_parent_cpp_type")[0]
    call = _relations(result, "blueprint_cpp_function")[0]
    assert parent["resolution_status"] == "candidate"
    assert call["resolution_status"] == "ambiguous" and len(call["target_candidates"]) == 2
    assert call["id"] in result["relation_index"]["by_target_or_candidate"]["fn:int"]
    assert call["id"] in result["relation_index"]["by_source"]["/Game/BP_Actor:Call"]
    bp_function = result["entities"]["blueprint_functions"][0]
    assert [pin["name"] for pin in bp_function["inputs"]] == ["Input"]
    assert [pin["name"] for pin in bp_function["outputs"]] == ["OutValue", "ReturnValue"]
    assert bp_function["returns"][0]["resolution_status"] == "candidate"
    assert [pin["name"] for pin in bp_function["returns"][0]["target_candidates"]] == ["ReturnValue"]
    macro_link = _relations(result, "blueprint_macro_graph_reference")[0]
    assert macro_link["resolution_status"] == "verified"
    assert macro_link["target_identity"]["id"].endswith("StandardMacros.IsValid")
    assert result["accuracy_contract"]["cross_language_verified_count"] == 0
    assert not any(r["resolution_status"] == "verified" and r["reference_kind"].startswith("blueprint_cpp")
                   for r in result["relations"])


def test_unified_duplicate_cpp_classes_and_blueprint_function_names_never_collapse():
    types = [_type("type:first", "AActor", file="Source/Game/One/Actor.h"),
             _type("type:second", "AActor", file="Source/Game/Two/Actor.h")]
    one = _blueprint("/Game/One/BP", "/Script/Game.Actor", [_node("/Game/One/BP:Missing", [
        _reference("function", "/Script/Game.Actor", "Missing", status="partial")])])
    one["graph_ir"]["graphs"].append({"id": "/Game/One/BP.BP.DoThingDuplicate", "name": "DoThing",
                                        "guid_raw": "duplicate-guid", "nodes": []})
    one["graph_ir"]["graphs"][0]["nodes"].append(_node("/Game/One/BP:SameName", [
        _reference("function", "/Game/One/BP.BP_C", "DoThing")]))
    two = _blueprint("/Game/Two/BP", "/Script/Game.Actor", [_node("/Game/Two/BP:Missing")])
    result = U.build_unified_analysis(_cpp(types), {"/Game/One/BP": one, "/Game/Two/BP": two})
    parents = _relations(result, "blueprint_parent_cpp_type")
    assert all(r["resolution_status"] == "ambiguous" for r in parents)
    same_name = result["lookup_by_name"]["dothing"]
    assert len(same_name) == 3 and len(set(same_name)) == 3
    missing = _relations(result, "blueprint_cpp_function")[0]
    assert missing["resolution_status"] == "unavailable" and not missing["target_candidates"]
    bp_call = _relations(result, "blueprint_function_reference")[0]
    assert bp_call["resolution_status"] == "ambiguous" and len(bp_call["target_candidates"]) == 2


def test_unified_pin_flow_variable_use_and_partial_inputs_preserve_boundaries():
    types = [_type("type:actor", "AActor")]
    fields = [_field("field:value", "AActor", "Value")]
    target_pin = "/Game/BP.BP.Graph/export:2/pin:target"
    source_pin = {"id": "/Game/BP.BP.Graph/export:1/pin:source", "pin_name": "Value", "direction": 1,
                  "type": {"pin_category": "int"}, "linked_to_raw": [
                      {"status": "resolved", "basis": "saved_owner_path", "owner_path": "/Game/BP:Target",
                       "target": target_pin, "candidates": [], "reference": {"pin_guid": "target"}}]}
    variable = _reference("variable", "/Script/Game.Actor", "Value", guid="bad-guid", status="partial")
    nodes = [_node("/Game/BP:Source", [variable], [source_pin], "K2Node_VariableGet"),
             _node("/Game/BP:Target", [], [{"id": target_pin, "pin_name": "Input", "direction": 0,
                                             "type": {"pin_category": "int"}, "linked_to_raw": []}])]
    bp = _blueprint("/Game/BP", "/Script/Game.Actor", nodes, graph_status="partial", declaration_status="partial")
    result = U.build_unified_analysis(_cpp(types, fields=fields, status="partial"), {"/Game/BP": bp},
                                      native_reference_validation={"status": "mismatch", "differences": ["saved != loaded"]})
    flow = _relations(result, "blueprint_data_pin_link")[0]
    use = _relations(result, "blueprint_cpp_variable")[0]
    assert flow["resolution_status"] == "verified" and flow["target_identity"]["id"] == target_pin
    assert flow["provenance"] == ["graph_ir:saved-package", "saved-pin-reference"]
    assert use["resolution_status"] == "candidate" and use["target_candidates"][0]["id"] == "field:value"
    assert result["status"] == "partial" and result["input_status"]["cpp_precision"] == "partial"
    assert result["issues"][0]["status"] == "mismatch"


def test_unified_inheritance_native_event_interface_and_implementation_are_candidates():
    types = [_type("type:base", "ABase"), _type("type:child", "AChild", base="ABase"),
             _type("type:ui", "UInteractable", kind="UINTERFACE"),
             _type("type:ii", "IInteractable", kind="class")]
    functions = [_function("fn:event", "ABase", "Activate", annotation="UFUNCTION(BlueprintNativeEvent)"),
                 _function("fn:base-tick", "ABase", "Tick", annotation=None),
                 _function("fn:child-tick", "AChild", "Tick", annotation=None, signature="Tick() override"),
                 _function("fn:impl", "ABase", "Activate_Implementation", annotation=None, definition=True),
                 _function("fn:interface", "IInteractable", "Interact", annotation="UFUNCTION(BlueprintCallable)")]
    links = [{"implementation_id": "fn:impl", "kind": "implementation_candidate",
              "declaration_candidates": ["fn:event"], "resolution_status": "syntax_observed", "issues": []}]
    interface_ref = _reference("interface_function", "/Script/Game.Interactable", "Interact")
    bp = _blueprint("/Game/BP_Child", "/Script/Game.Child", [_node("/Game/BP_Child:Message", [interface_ref], cls="K2Node_Message")])
    result = U.build_unified_analysis(_cpp(types, functions, links=links), {"/Game/BP_Child": bp})
    assert _relations(result, "cpp_inherits")[0]["resolution_status"] == "candidate"
    override = _relations(result, "cpp_override_candidate")[0]
    assert override["resolution_status"] == "candidate" and override["target_candidates"][0]["id"] == "fn:base-tick"
    assert _relations(result, "cpp_unreal_implementation")[0]["resolution_status"] == "candidate"
    interface = _relations(result, "blueprint_cpp_interface_function")[0]
    assert interface["resolution_status"] == "candidate"
    assert any("runtime-dependent" in issue for issue in interface["issues"])
    assert all(r["resolution_status"] != "verified" for r in
               _relations(result, "cpp_unreal_implementation") + [interface])
