"""An Outer export is not proof of saved graph membership."""
from types import SimpleNamespace as NS
import struct
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from graph_membership import reconcile_graph_membership as reconcile, decode_node_array, SavedNodeArray, read_saved_node_array, MembershipUnavailable


def reconcile_graph_membership(graphs, ctx):
    return reconcile(graphs, ctx, lambda owner: ctx.props(owner).get("Nodes"))


def case(refs=(1, 2)):
    owner = NS(object_name="StateGraph")
    objects = {i: NS(outer=owner) for i in (1, 2, 3, 4)}
    nodes = [NS(_export_index=i, class_name="Node", pins=[NS(pin_id=str(i))]) for i in (1, 2, 3)]
    graph = NS(graph_name="StateGraph", nodes=nodes[:], subgraphs=[])
    props = {} if refs is None else {"Nodes": refs}
    ctx = NS(obj=lambda i: objects.get(i), props=lambda o: props,
             full_name=lambda o: "/Game/BP.BP.StateGraph", issues=[])
    return graph, ctx, objects


def test_graph_membership_uses_explicit_nodes_and_preserves_unlisted_pin_objects():
    graph, ctx, _ = case([2, 1])
    removed = graph.nodes[2]
    detached, notes = reconcile_graph_membership([graph], ctx)
    assert [n._export_index for n in graph.nodes] == [1, 2]
    assert detached[0][1].nodes == [removed] and detached[0][1].nodes[0].pins is removed.pins
    assert notes[0]["status"] == "confirmed" and notes[0]["saved_node_exports"] == [2, 1]
    assert notes[0]["unlisted_node_exports"] == [3]


def test_graph_membership_never_drops_unknown_missing_or_ambiguous_saved_members():
    for refs in (None, b"opaque", [True], [0], [-1], [1, 1], [1, 4]):
        graph, ctx, _ = case(refs)
        before = list(graph.nodes)
        detached, notes = reconcile_graph_membership([graph], ctx)
        assert not detached and graph.nodes == before and notes[0]["status"] == "unknown", refs
    graph, ctx, objects = case([1, 2])
    objects[3].outer = NS(object_name="DifferentGraph")
    detached, notes = reconcile_graph_membership([graph], ctx)
    assert not detached and len(graph.nodes) == 3 and notes[0]["status"] == "unknown"
    graph, ctx, _ = case([1, 2])
    def broken_source(owner):
        raise ValueError("saved Nodes array count does not match its bounded payload")
    detached, notes = reconcile([graph], ctx, broken_source)
    assert not detached and len(graph.nodes) == 3 and notes[0]["status"] == "unknown"
    assert ctx.issues[0]["stage"] == "graph_membership"
    graph, ctx, _ = case([1, 2])
    def locked(owner):
        raise OSError("sharing violation")
    detached, notes = reconcile([graph], ctx, locked)
    assert not detached and len(graph.nodes) == 3 and notes[0]["status"] == "unknown"
    assert ctx.issues[0]["stage"] == "graph_membership"
    graph, ctx, _ = case([1, 2])
    refs = SavedNodeArray([1, 2])
    refs.entry_export = {"status": "unknown", "reason": "bad reference"}
    _, notes = reconcile([graph], ctx, lambda owner: refs)
    assert notes[0]["entry_node_export"]["status"] == "unknown"
    assert notes[0]["entry_node_listed"]["status"] == "unknown"


def test_graph_membership_keeps_cross_boundary_links_unresolved_with_raw_identity():
    from graph_ir_tests import node, pin, A, B, C
    from graph_ir import build_graph_ir
    graph, ctx, objects = case([1])
    path = "/Game/BP.BP.StateGraph"
    source = node("N1", 1, [pin(C, linked_to_raw=[{"owning_node": "N3", "pin_guid": A,
                                                 "owning_node_object": objects[3]}])])
    target = node("N3", 3, [pin(A)])
    for index, obj in objects.items():
        obj.path = path + f".N{index}"
    ctx.full_name = lambda obj: path if obj is objects[1].outer else obj.path
    graph.nodes = [source, target]
    detached, _ = reconcile_graph_membership([graph], ctx)
    ir = build_graph_ir([(path, graph)], ctx, "/Game/BP", 1, 1)
    link = ir["graphs"][0]["nodes"][0]["pins"][0]["linked_to_raw"][0]
    assert link["status"] == "unresolved" and link["target"] is None
    assert link["reference"]["pin_guid"] == A
    assert link["reference"]["owning_node_object"]["path"] == path + ".N3"
    assert ir["issues"] and detached[0][1].nodes[0] is target


def test_graph_membership_explicit_empty_is_distinct_and_duplicate_views_count_once():
    assert decode_node_array(struct.pack("<i", 0)) == []
    assert decode_node_array(struct.pack("<iii", 2, 1, 3)) == [1, 3]
    for raw in (b"", struct.pack("<i", -1), struct.pack("<i", 3), struct.pack("<ii", 0, 1)):
        try:
            decode_node_array(raw)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid saved array became a confirmed empty/default value")
    graph, ctx, _ = case([])
    detached, notes = reconcile_graph_membership([graph], ctx)
    assert graph.nodes == [] and len(detached[0][1].nodes) == 3 and notes[0]["status"] == "confirmed"
    graph, ctx, _ = case([1, 2])
    alias = NS(graph_name=graph.graph_name, nodes=graph.nodes[:], subgraphs=[])
    graph.subgraphs = [alias]
    detached, _ = reconcile_graph_membership([graph, alias], ctx)
    assert len(detached) == 1 and len(detached[0][1].nodes) == 1
    assert [n._export_index for n in graph.nodes] == [1, 2]
    assert [n._export_index for n in alias.nodes] == [1, 2]


def test_graph_membership_source_tag_is_top_level_and_entry_unknown_is_preserved():
    import data_reader as D
    raw = struct.pack("<i", 0) + struct.pack("<iii", 2, 1, 3) + bytes(8)
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "BP.uasset"
        path.write_bytes(raw)
        owner = NS()
        export = NS(serial_offset=0, serial_size=len(raw))
        result = NS(export_map=[export], summary=NS(file_version_ue5=1018))
        ctx = NS(obj=lambda index: owner if index == 1 else None)
        class Reader:
            top = True
            closed = False
            duplicate = False
            def __init__(self, *args):
                self.ar, self.fv5, self.names = io.BytesIO(raw), 0, []
                def tag(start, size):
                    return NS(name="Nodes", type="ArrayProperty", size=size, value_start_offset=start,
                              value_end_offset=start + size, type_name=NS(children=[NS(name="ObjectProperty")]))
                meta = NS(name="Meta", type="StructProperty", size=4, value_start_offset=0, value_end_offset=4)
                tags = [meta]
                if self.top:
                    tags.append(tag(4, 12))
                if self.duplicate:
                    tags.append(tag(16, 4))
                else:
                    tags.append(NS(name="EntryNode", type="StructProperty", size=4,
                                   value_start_offset=16, value_end_offset=20))
                tags.append(NS(name="None"))
                self.tags = iter(tags)
            def _read_tag(self, *args, **kwargs):
                return next(self.tags)
            def close(self):
                Reader.closed = True
        with patch.object(D, "TaggedReader", Reader):
            saved = read_saved_node_array(path, result, ctx, owner)
            assert saved == [1, 3] and saved.entry_export["status"] == "unknown"
            assert Reader.closed
            Reader.top = False
            try:
                read_saved_node_array(path, result, ctx, owner)
            except MembershipUnavailable:
                pass
            else:
                raise AssertionError("nested Nodes field was accepted as the graph's own array")
            Reader.top, Reader.duplicate = True, True
            try:
                read_saved_node_array(path, result, ctx, owner)
            except ValueError as error:
                assert "duplicate" in str(error)
            else:
                raise AssertionError("duplicate top-level Nodes tag was silently accepted")
            result.summary.file_version_ue5 = 0
            try:
                read_saved_node_array(path, result, ctx, owner)
            except MembershipUnavailable as error:
                assert "legacy" in str(error)
            else:
                raise AssertionError("legacy layout was silently promoted to verified membership")
