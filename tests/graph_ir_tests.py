"""Saved identities and counterexamples that pseudo-code/name matching can hide."""
import copy
import json
from types import SimpleNamespace as NS

from graph_ir import build_graph_ir, serialized_guid

A, B, C = "a" * 32, "b" * 32, "c" * 32


def pin_type(**kw):
    values = dict(pin_category="int", pin_subcategory="", pin_subcategory_object=0,
                  pin_subcategory_object_name=None, container_type=0, is_reference=False,
                  is_weak_pointer=False, is_const=False, is_uobject_wrapper=False,
                  b_serialize_as_single_precision_float=False, map_key_terminal_category="",
                  map_key_terminal_sub_category="", map_key_terminal_sub_category_object=None,
                  map_key_terminal_sub_category_object_name=None)
    values.update(kw)
    return NS(**values)


def pin(guid=A, **kw):
    values = dict(pin_id=guid, pin_name="Value", direction=0,
                  pin_type=pin_type(), linked_to_raw=[], persistent_guid=None,
                  hidden=False, orphaned_pin=False, not_connectable=False, advanced_view=False,
                  default_value=None, auto_default_value=None, default_object=None, default_text_value=None,
                  sub_pins=[], parent_pin=None, ref_pass_through=None)
    values.update(kw)
    return NS(**values)


def node(name, index, pins):
    return NS(_export_object_name=name, _export_index=index,
              node_guid=C, class_name="K2Node_CallFunction", pins=pins)


def project(nodes, extra=()):
    ctx = NS(obj=lambda index: NS(path=f"/Game/BP.BP.EventGraph.N{index}"),
             full_name=lambda obj: obj.path)
    pairs = [("/Game/BP.BP.EventGraph", NS(graph_name="EventGraph", nodes=nodes)), *extra]
    count = sum(len(g.nodes) for _, g in pairs)
    return build_graph_ir(pairs, ctx, "/Game/BP", count, count)


def test_graph_ir_full_pin_literals_and_type_fields():
    literal = '한글 "quote"\n```' + "long " * 500
    p = pin(default_value="", default_text_value=literal, default_object=0, hidden=False,
            auto_default_value=None,
            pin_type=pin_type(pin_category="byte", pin_subcategory_object_name="E_Key",
                        container_type=3, map_key_terminal_category="bool", is_const=False))
    class Ref(int): pass  # bp_reader.ObjRef preserves package indices as int subclasses.
    ir = project([node("N1", Ref(1), [p])]); data = ir["graphs"][0]["nodes"][0]["pins"][0]
    assert ir["graphs"][0]["nodes"][0]["object_path"] == "/Game/BP.BP.EventGraph.N1"
    assert ir["graphs"][0]["nodes"][0]["id"].endswith("/export:1")
    assert data["defaults"] == {"default_value": "", "default_text_value": literal,
                                "default_object": 0, "auto_default_value": None, "default_object_path": None}
    assert data["type"]["map_key_terminal_category"] == "bool" and data["type"]["is_const"] is False
    assert data["hidden"] is False and data["orphaned_pin"] is False
    assert json.loads(json.dumps(ir, ensure_ascii=False, allow_nan=False)) == ir
    assert ir["status"] == "complete" and "excludes node properties" in ir["scope"]
    assert ir["pin_guid_encoding"] == "serialized-byte-order-hex"
    assert "guid_raw" in ir["graphs"][0] and "guid_raw" in ir["graphs"][0]["nodes"][0]
    assert "asset package snapshot" in ir["identity_scope"]
    # A missing decoder attribute must never look like a confirmed absent flag.
    del p.orphaned_pin
    unknown = project([node("N1", 1, [p])])
    assert unknown["status"] == "partial"
    assert unknown["graphs"][0]["nodes"][0]["pins"][0]["orphaned_pin"]["status"] == "unknown"


def test_graph_ir_owner_scopes_shared_guids_and_keeps_observations():
    # Two nodes may have the same pin GUID. A global GUID dictionary misconnects this case.
    out = pin(B, direction=1, linked_to_raw=[{"owning_node": "N1", "pin_guid": A}])
    ir = project([node("N1", 1, [pin()]), node("N2", 2, [pin(), out])])
    n1, n2 = ir["graphs"][0]["nodes"]
    link = n2["pins"][1]["linked_to_raw"][0]
    assert link["target"] == n1["pins"][0]["id"] != n2["pins"][0]["id"]
    assert link["status"] == "resolved" and ir["status"] == "complete"
    # Reciprocal entries remain separately observed, rather than inventing runtime control flow.
    assert n1["pins"][0]["linked_to_raw"] == []


def test_graph_ir_never_guesses_missing_ambiguous_or_cross_graph_targets():
    refs = [{"pin_guid": A}, {"owning_node": "Duplicate", "pin_guid": A},
            {"owning_node": "OtherGraphOnly", "pin_guid": B}, None]
    extra = [("/Game/BP.BP.Other", NS(graph_name="Other", nodes=[node("OtherGraphOnly", 9, [pin(B)])]))]
    ir = project([node("Source", 1, [pin(C, linked_to_raw=refs)]),
                  node("Duplicate", 2, [pin()]), node("Duplicate", 3, [pin()])], extra)
    links = ir["graphs"][0]["nodes"][0]["pins"][0]["linked_to_raw"]
    assert [x["status"] for x in links] == ["unresolved", "ambiguous", "unresolved", "unresolved"]
    assert all(x["target"] is None for x in links) and len(links[1]["candidates"]) == 2
    assert len(ir["issues"]) == 4 and ir["status"] == "partial"
    # A known object path disambiguates duplicate short names without ignoring its owner.
    refs[1]["owning_node_object"] = NS(path="/Game/BP.BP.EventGraph.N2")
    ir2 = project([node("Source", 1, [pin(C, linked_to_raw=refs)]),
                   node("Duplicate", 2, [pin()]), node("Duplicate", 3, [pin()])])
    assert ir2["graphs"][0]["nodes"][0]["pins"][0]["linked_to_raw"][1]["status"] == "resolved"


def test_graph_ir_duplicate_pin_and_invalid_values_remain_unknown():
    ir = project([node("N1", 1, [pin(), pin(), pin("bad", default_value=float("nan"))]),
                  node("Source", 2, [pin(B, linked_to_raw=[{"owning_node": "N1", "pin_guid": A}])])])
    nodes = ir["graphs"][0]["nodes"]
    pins = nodes[0]["pins"]
    assert len({p["id"] for p in pins}) == 3, "duplicate pins were overwritten"
    assert nodes[1]["pins"][0]["linked_to_raw"][0]["status"] == "ambiguous"
    assert pins[2]["defaults"]["default_value"]["status"] == "unknown"
    json.dumps(ir, allow_nan=False)
    assert ir["status"] == "partial" and len(ir["issues"]) >= 3
    assert serialized_guid("00000000-0000-0000-0000-000000000000") is None
    assert serialized_guid("x" + A) is None and serialized_guid(A.upper()) == A


def test_graph_ir_semantic_mutations_visible_without_rendering():
    target = node("Target", 1, [pin()])
    source = node("Source", 2, [pin(B, default_value="0", linked_to_raw=[{"owning_node": "Target", "pin_guid": A}])])
    original = project([target, source])
    for mutation in ("value", "type", "link"):
        changed = copy.deepcopy(source)
        if mutation == "value": changed.pins[0].default_value = "1"
        if mutation == "type": changed.pins[0].pin_type.pin_category = "bool"
        if mutation == "link": changed.pins[0].linked_to_raw[0]["owning_node"] = "Missing"
        actual = project([target, changed])
        assert actual != original, mutation + " was hidden by normalization"
        assert actual["graphs"][0]["nodes"][0] == original["graphs"][0]["nodes"][0]
    source.node_pos_x = 1000
    assert project([target, source]) == original, "editor layout became a semantic change"


def test_graph_ir_partial_decode_and_structural_pin_references():
    p1 = pin(A, sub_pins=[{"pin_guid": B}])
    p2 = pin(B, parent_pin={"owning_node": None, "pin_guid": A},
             ref_pass_through={"pin_guid": A})
    ir = project([node("N1", 1, [p1, p2])]); pins = ir["graphs"][0]["nodes"][0]["pins"]
    assert pins[0]["sub_pins"][0]["target"] == pins[1]["id"]
    assert pins[1]["parent_pin"]["target"] == pins[0]["id"]
    assert pins[1]["ref_pass_through"]["target"] == pins[0]["id"]
    assert pins[1]["parent_pin"]["basis"] == "same_node_structural"
    assert ir["status"] == "complete"
    assert build_graph_ir([], NS(), "/Game/BP", 0, 2)["status"] == "partial"
    # The caller's graph collection must not hide a lost graph even at parser N/N.
    missing = build_graph_ir([], NS(), "/Game/BP", 2, 2)
    assert missing["status"] == "partial" and missing["nodes_represented"] == 0
    assert "0/2 parser nodes represented" in missing["issues"][0]["message"]


def test_graph_ir_object_defaults_and_unknown_reference_fields_are_not_lost():
    p = pin(default_object=-1, default_object_ref=NS(path="/Script/Engine.Actor"),
            linked_to_raw=[{"owning_node": "N1", "pin_guid": B, "extra_flag": False}])
    ir = project([node("N1", 1, [p, pin(B)])])
    data = ir["graphs"][0]["nodes"][0]["pins"][0]
    assert data["defaults"]["default_object_path"] == "/Script/Engine.Actor"
    assert data["linked_to_raw"][0]["reference"]["extra_flag"] is False
    assert ir["status"] == "complete"
    p.linked_to_raw[0]["extra_flag"] = object()
    assert project([node("N1", 1, [p, pin(B)])])["status"] == "partial"
    for variant in ("missing", "invalid_index", "unavailable_object"):
        default = pin()
        if variant == "missing": del default.default_object
        if variant == "invalid_index": default.default_object = "not an object index"
        if variant == "unavailable_object": default.default_object_ref = NS(path="")
        actual = project([node("N1", 1, [default])])
        assert actual["status"] == "partial", variant
        assert actual["graphs"][0]["nodes"][0]["pins"][0]["defaults"]["default_object_path"]["status"] == "unknown", variant
    # Saved keys cannot collide with fields derived from the linker's object.
    ref = {"owning_node": "N1", "pin_guid": B, "owning_node_path": "literal saved key",
           "owning_node_object": NS(path="/Game/BP.BP.EventGraph.N1")}
    actual = project([node("N1", 1, [pin(A, linked_to_raw=[ref]), pin(B)])])
    link = actual["graphs"][0]["nodes"][0]["pins"][0]["linked_to_raw"][0]
    assert link["reference"]["owning_node_path"] == "literal saved key"
    assert link["reference"]["owning_node_object"]["path"] == link["owner_path"] == "/Game/BP.BP.EventGraph.N1"
    # A malformed explicit owner is not an absent owner eligible for local fallback.
    actual = project([node("N1", 1, [pin(A), pin(B, parent_pin={"owning_node": 5, "pin_guid": A})])])
    assert actual["graphs"][0]["nodes"][0]["pins"][1]["parent_pin"]["status"] == "unresolved"
