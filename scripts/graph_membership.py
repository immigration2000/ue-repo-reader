"""Separate decoded exports from a graph's explicitly saved Nodes membership.

The pinned parser also groups unlisted node exports by their Outer. That is useful
for inspecting package contents, but does not establish that the graph contains
those exports. Reconcile only a fully resolved explicit Nodes array; never infer
an empty array or drop an undecodable saved member.
"""
from __future__ import annotations

from copy import copy
import struct


class SavedNodeArray(list):
    """Validated source array with optional separately saved EntryNode reference."""


class MembershipUnavailable(ValueError):
    """The supported saved field/identity is unavailable, not a proven empty array."""


def decode_node_array(raw):
    """An exact serialized TArray<FPackageIndex>, without tolerant empty defaults."""
    if len(raw) < 4:
        raise ValueError("saved Nodes array count is truncated")
    count = struct.unpack_from("<i", raw)[0]
    if count < 0 or len(raw) != 4 + count * 4:
        raise ValueError("saved Nodes array count does not match its bounded payload")
    return list(struct.unpack_from("<" + "i" * count, raw, 4))


def read_saved_node_array(path, result, ctx, owner):
    """Locate an exact graph export/tag and check its source bytes before filtering."""
    if getattr(getattr(result, "summary", None), "file_version_ue5", 0) <= 0:
        raise MembershipUnavailable("saved Nodes validation is outside the current UE5 package scope; decoded legacy view retained")
    import data_reader as D
    exports = [e for index, e in enumerate(result.export_map, 1) if ctx.obj(index) is owner]
    if len(exports) != 1:
        raise MembershipUnavailable("owning graph export identity missing or ambiguous")
    reader = D.TaggedReader(str(path), result, ctx)
    export = exports[0]
    payloads, terminated = {}, False
    try:
        ar = reader.ar
        ar.seek(export.serial_offset)
        limit = export.serial_offset + export.serial_size
        if reader.fv5 >= 1011:
            control = ar.read_u8()
            if control & 0x02:
                ar.read_u8()
        for _ in range(4000):
            if ar.tell() >= limit:
                break
            tag = reader._read_tag(ar, reader.names, tolerant=True)
            if tag.name == "None":
                terminated = True
                break
            if not str(tag.type).endswith("Property"):
                raise ValueError("invalid top-level graph property header")
            start, end = tag.value_start_offset, tag.value_end_offset
            if (type(start) is not int or type(end) is not int
                    or not export.serial_offset <= ar.tell() <= start <= end <= limit
                    or end - start != tag.size):
                raise ValueError("saved graph property escapes its owning export")
            if tag.name in ("Nodes", "EntryNode"):
                ar.seek(start)
                raw = ar.read(end - start)
                if len(raw) != end - start:
                    raise ValueError("saved graph property payload is truncated")
                payloads.setdefault(tag.name, []).append((tag, raw))
            # Only top-level headers are traversed. Unrelated values (including
            # nested structs named Nodes) never enter a tolerant value parser.
            ar.seek(end)
        if not terminated:
            raise ValueError("saved graph property header stream is incomplete")
    finally:
        reader.close()
    candidates = payloads.get("Nodes", [])
    if not candidates:
        raise MembershipUnavailable("saved Nodes tag absent")
    if len(candidates) != 1:
        raise ValueError("duplicate saved Nodes tags")
    tag, raw = candidates[0]
    tree = getattr(tag, "type_name", None)
    inner = tree.children[0].name if tree is not None and tree.children else getattr(tag, "inner_type", None)
    if tag.type != "ArrayProperty" or inner != "ObjectProperty":
        raise MembershipUnavailable("saved Nodes tag is not an explicit object-index array")
    nodes = SavedNodeArray(decode_node_array(raw))
    entries = payloads.get("EntryNode", [])
    nodes.entry_tag_status = "absent" if not entries else "saved"
    if len(entries) == 1 and entries[0][0].type == "ObjectProperty" and len(entries[0][1]) == 4:
        index = struct.unpack("<i", entries[0][1])[0]
        if index >= 0:
            nodes.entry_export = index
        else:
            nodes.entry_export = {"status": "unknown", "reason": "saved EntryNode is not a local export index", "raw_index": index}
    elif entries:
        nodes.entry_export = {"status": "unknown", "reason": "saved EntryNode tag is duplicated or unreadable"}
    return nodes


def reconcile_graph_membership(graphs, ctx, read_nodes):
    detached, observations, seen, groups = [], [], set(), {}

    def visit(items):
        for graph in items or []:
            if id(graph) in seen:
                continue
            seen.add(id(graph))
            visit(getattr(graph, "subgraphs", []))
            nodes = list(getattr(graph, "nodes", []) or [])
            if not nodes:
                continue
            graph_name = getattr(graph, "graph_name", None)
            record = {"graph": graph_name if isinstance(graph_name, str) else None, "status": "unknown"}
            observations.append(record)
            try:
                objects = [ctx.obj(getattr(n, "_export_index", None)) for n in nodes]
                owner = getattr(objects[0], "outer", None)
                if (owner is None or any(o is None or getattr(o, "outer", None) is not owner for o in objects)
                        or getattr(owner, "object_name", None) != graph.graph_name):
                    record["reason"] = "decoded nodes do not establish one exact owning graph"
                    continue
                path = ctx.full_name(owner)
                if not isinstance(path, str) or not path.startswith("/"):
                    record["reason"] = "owning graph object path unavailable"
                    continue
                record["graph"] = path
                refs = read_nodes(owner)
                if not isinstance(refs, list):
                    record["reason"] = "saved Nodes tag absent or not a decoded array"
                    continue
                indices = [getattr(n, "_export_index", None) for n in nodes]
                if (any(not isinstance(i, int) or isinstance(i, bool) or i <= 0 for i in refs + indices)
                        or len(set(refs)) != len(refs) or len(set(indices)) != len(indices)):
                    record["reason"] = "saved or decoded node identity invalid or duplicated"
                    continue
                if any(ctx.obj(i) is None for i in refs) or not set(refs).issubset(indices):
                    record["reason"] = "saved node member unresolved or missing from decoded graph; no exports removed"
                    continue
                allowed = set(refs)
                if hasattr(refs, "entry_tag_status"):
                    record["entry_node_tag_status"] = refs.entry_tag_status
                if hasattr(refs, "entry_export"):
                    record["entry_node_export"] = refs.entry_export
                    record["entry_node_listed"] = (refs.entry_export in allowed if refs.entry_export else None) if isinstance(refs.entry_export, int) else {"status": "unknown", "reason": "EntryNode reference is unknown"}
                unlisted = [n for n in nodes if n._export_index not in allowed]
                record.update(status="confirmed", saved_node_exports=list(refs),
                              unlisted_node_exports=[n._export_index for n in unlisted])
                if unlisted:
                    if path not in groups:
                        group = copy(graph)
                        group.nodes = []
                        group.subgraphs = []
                        groups[path] = group
                        detached.append((path, group))
                    # Nested/top-level model views repeat the same saved exports.
                    group = groups[path]
                    known = {n._export_index for n in group.nodes}
                    group.nodes.extend(n for n in unlisted if n._export_index not in known)
                    graph.nodes = [n for n in nodes if n._export_index in allowed]
            except (AttributeError, TypeError, ValueError, KeyError, OSError) as error:
                record["reason"] = f"saved graph membership unavailable: {type(error).__name__}: {error}"
                if isinstance(error, OSError) or isinstance(error, ValueError) and not isinstance(error, MembershipUnavailable):
                    issue = {"stage": "graph_membership", "context": str(record["graph"]),
                             "message": f"{type(error).__name__}: {error}"}
                    if issue not in ctx.issues:
                        ctx.issues.append(issue)

    visit(graphs)
    return detached, observations
