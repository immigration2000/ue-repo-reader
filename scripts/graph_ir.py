"""Versioned, loss-aware projection of decoded graph pins, independent of pseudo-code.

Consumes the public decoded models of the pinned MIT uasset_read dependency; no
upstream implementation is copied. Pin GUIDs below are serialized byte-order hex,
NOT Unreal's four-word display GUIDs; graph/node GUIDs remain raw parser metadata.
This is a comparison foundation, not a
complete execution model: node properties, CDOs and runtime behavior are outside
its scope. A complete projection does not mean independently verified semantics.
"""
from __future__ import annotations

from collections import defaultdict
import math
import re

SCHEMA_VERSION = 1
_PIN_FIELDS = ("pin_name", "direction", "persistent_guid", "hidden", "orphaned_pin",
               "not_connectable", "advanced_view")
_DEFAULT_FIELDS = ("default_value", "auto_default_value", "default_object", "default_text_value")
_TYPE_FIELDS = ("pin_category", "pin_subcategory", "pin_subcategory_object",
                "pin_subcategory_object_name", "container_type", "is_reference",
                "is_weak_pointer", "is_const", "is_uobject_wrapper",
                "b_serialize_as_single_precision_float", "map_key_terminal_category",
                "map_key_terminal_sub_category", "map_key_terminal_sub_category_object",
                "map_key_terminal_sub_category_object_name")


def serialized_guid(value):
    """Normalize only a valid, nonzero serialized GUID. Never guess an identity."""
    if not isinstance(value, str):
        return None
    value = value.replace("-", "").lower()
    return value if re.fullmatch(r"[0-9a-f]{32}", value) and int(value, 16) else None


def build_graph_ir(graphs, ctx, asset_path, nodes_ok, nodes_total):
    """Project (exact graph path, graph) pairs from the Blueprint reader.

    Retain every saved link observation, including unresolved/ambiguous ones.
    Resolve only within its graph using the owning object and serialized pin ID;
    a unique GUID alone is insufficient. Do not shortcut reroutes or collapse
    reciprocal observations. Pin indices retain serialization order for oracles.
    """
    issues, issue_keys, output, graph_ids, represented = [], set(), [], set(), set()

    def issue(context, message):
        item = {"context": context, "message": message}
        key = (context, message)
        if key not in issue_keys:
            issues.append(item)
            issue_keys.add(key)

    def scalar(value, context):
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
        issue(context, "decoded field is not a finite JSON scalar; value is unknown")
        return {"status": "unknown", "type": type(value).__name__}

    def fields(obj, names, context):
        result = {}
        for name in names:
            if hasattr(obj, name):
                result[name] = scalar(getattr(obj, name), context + "." + name)
            else:
                issue(context + "." + name, "field not exposed by decoder; value is unknown")
                result[name] = {"status": "unknown", "reason": "not_exposed_by_decoder"}
        return result

    def object_path(obj):
        if obj is None:
            return None
        try:
            value = ctx.full_name(obj)
            return value if isinstance(value, str) and value else None
        except (AttributeError, TypeError):
            return None

    for graph_index, (key, graph) in enumerate(graphs):
        gid = str(key)
        if not gid or gid.startswith("?"):
            issue(gid, "graph object path unavailable; identity is local to this projection")
        if gid in graph_ids:
            issue(gid, "duplicate graph identity; graphs retained separately")
            gid += f"/duplicate-graph:{graph_index}"
        graph_ids.add(gid)
        item = {"id": gid, "name": getattr(graph, "graph_name", None),
                "guid_raw": getattr(graph, "graph_guid", None), "nodes": []}
        output.append(item)
        lookup, paths, local = defaultdict(list), defaultdict(list), defaultdict(list)
        pending, node_ids = [], set()
        for node_index, node in enumerate(graph.nodes):
            export = getattr(node, "_export_index", None)
            export = int(export) if isinstance(export, int) and not isinstance(export, bool) and export > 0 else None
            name = getattr(node, "_export_object_name", None)
            nid = f"{gid}/export:{export}" if export is not None else f"{gid}/ordinal:{node_index}"
            if export is None:
                issue(nid, "node export identity unavailable; ordinal is local to this projection")
            if nid in node_ids:
                issue(nid, "duplicate node export identity; nodes retained separately")
                nid += f"/duplicate:{node_index}"
            node_ids.add(nid)
            if getattr(node, "class_name", None) != "EdGraphNode_Comment":
                represented.add(("export", export) if export is not None else ("local_object", id(node)))
            try:
                path = object_path(ctx.obj(export)) if export is not None else None
            except (AttributeError, TypeError):
                path = None
            pins = list(getattr(node, "pins", ()) or ())
            record = {"id": nid, "object_name": name, "object_path": path,
                      "export_index": export, "guid_raw": getattr(node, "node_guid", None),
                      "class": getattr(node, "class_name", None), "pins": []}
            item["nodes"].append(record)
            seen = set()
            for pin_index, pin in enumerate(pins):
                raw_guid = getattr(pin, "pin_id", None)
                guid = serialized_guid(raw_guid)
                pid = f"{nid}/pin:{guid}" if guid else f"{nid}/pin-ordinal:{pin_index}"
                if not guid:
                    issue(pid, "missing or invalid serialized pin GUID")
                if pid in seen:
                    issue(pid, "duplicate pin GUID within owning node; pins retained separately")
                    pid += f"/duplicate:{pin_index}"
                seen.add(pid)
                pt = getattr(pin, "pin_type", None)
                prec = {"id": pid, "index": pin_index, "guid": scalar(raw_guid, pid),
                        **fields(pin, _PIN_FIELDS, pid),
                        "type": fields(pt, _TYPE_FIELDS, pid + ".type") if pt is not None else None,
                        "defaults": fields(pin, _DEFAULT_FIELDS, pid + ".defaults")}
                if pt is None:
                    issue(pid, "pin type unavailable")
                if getattr(pin, "direction", None) not in (0, 1):
                    issue(pid, "pin direction unavailable or invalid")
                record["pins"].append(prec)
                if guid:
                    local[(nid, guid)].append(pid)
                if name and guid:
                    lookup[(name, guid)].append(pid)
                if path and guid:
                    paths[(path, guid)].append(pid)
                default = getattr(pin, "default_object", None)
                obj = getattr(pin, "default_object_ref", None)
                is_index = isinstance(default, int) and not isinstance(default, bool)
                if obj is None and is_index and default:
                    try:
                        obj = ctx.obj(default)
                    except (AttributeError, TypeError):
                        obj = None
                default_path = object_path(obj)
                unknown_index = isinstance(prec["defaults"]["default_object"], dict) or (default is not None and not is_index)
                if default_path is None and (obj is not None or unknown_index or is_index and default):
                    issue(pid + ".defaults.default_object_path", "default object path unavailable; object identity is unknown")
                    default_path = {"status": "unknown"}
                prec["defaults"]["default_object_path"] = default_path
                pending.append((pin, prec, nid))

        def reference(ref, context, node_id, structural=False):
            raw = {}
            basis = "unavailable"
            owner_path_record = None
            if isinstance(ref, dict):
                raw = {k: scalar(ref[k], context + "." + k)
                       for k in ref if k != "owning_node_object"}
                owner_path = object_path(ref.get("owning_node_object"))
                if owner_path:
                    owner_path_record = owner_path
                    raw["owning_node_object"] = {"kind": "object_reference", "path": owner_path}
                elif ref.get("owning_node_object") is not None:
                    owner_path_record = {"status": "unknown"}
                    raw["owning_node_object"] = {"kind": "object_reference", "path": {"status": "unknown"}}
                    issue(context, "owning object path unavailable; object identity is unknown")
                elif "owning_node_object" in ref:
                    raw["owning_node_object"] = None
                guid = serialized_guid(ref.get("pin_guid"))
                owner = ref.get("owning_node")
                if owner_path:
                    candidates, basis = paths.get((owner_path, guid), []), "saved_owner_path"
                elif ref.get("owning_node_object") is not None:
                    candidates, basis = [], "unavailable_owner_path"
                elif isinstance(owner, str) and owner and guid:
                    candidates, basis = lookup.get((owner, guid), []), "saved_owner_name"
                elif structural and guid and (owner is None or owner == ""):
                    # Parent/subpin/pass-through references may be node-local.
                    # This convention never applies to arbitrary linked_to edges.
                    candidates, basis = local.get((node_id, guid), []), "same_node_structural"
                else:
                    candidates = []
            else:
                raw = {"value": scalar(ref, context)}
                candidates = []
            status = "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unresolved"
            if status != "resolved":
                issue(context, f"{status} saved pin reference; no target inferred")
            return {"reference": raw, "status": status, "basis": basis,
                    "owner_path": owner_path_record,
                    "target": candidates[0] if status == "resolved" else None,
                    "candidates": list(candidates) if status == "ambiguous" else []}

        for pin, prec, node_id in pending:
            # These are structural saved references, not proven execution edges.
            for field in ("linked_to_raw", "sub_pins"):
                prec[field] = [reference(ref, f"{prec['id']}.{field}[{i}]", node_id, field != "linked_to_raw")
                               for i, ref in enumerate(getattr(pin, field, ()) or ())]
            for field in ("parent_pin", "ref_pass_through"):
                ref = getattr(pin, field, None)
                prec[field] = reference(ref, prec["id"] + "." + field, node_id, True) if ref is not None else None

    if len(represented) != nodes_total:
        issue(asset_path, f"{len(represented)}/{nodes_total} parser nodes represented; projection coverage is incomplete or inconsistent")
    return {"schema_version": SCHEMA_VERSION, "asset_path": asset_path,
            "scope": "nonempty parsed graphs: node identity/class, pin types/defaults and saved pin references; "
                     "excludes node properties, class defaults and runtime semantics",
            "pin_guid_encoding": "serialized-byte-order-hex",
            "identity_scope": "IDs identify this asset package snapshot; export indices may change across revisions",
            "coverage_basis": "decoder-exposed pins only; node N/N means at least one decoded pin per non-comment node, not full pin coverage",
            "status": "partial" if issues or nodes_ok < nodes_total else "complete",
            "nodes_decoded": nodes_ok, "nodes_total": nodes_total, "nodes_represented": len(represented),
            "graphs": output, "issues": issues}
