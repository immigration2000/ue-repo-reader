#!/usr/bin/env python3
"""Loss-aware synthesis of Blueprint IR and C++ syntax observations.

This module never changes graph_ir, declaration_ir, or cpp.precision.  It builds
references between their identities and keeps cross-language links below
``verified`` unless a future compiler/UHT identity provider proves them.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

SCHEMA_VERSION = 1
STATUSES = ("verified", "candidate", "ambiguous", "unavailable")
_REFLECTED_TYPES = {"UCLASS", "USTRUCT", "UENUM", "UINTERFACE"}


def _unknown(value: Any) -> bool:
    return isinstance(value, dict) and value.get("status") == "unknown"


def _module_from_file(path: str | None) -> str | None:
    parts = (path or "").split("/")
    positions = [i for i, part in enumerate(parts[:-1]) if part == "Source"]
    return parts[positions[-1] + 1] if positions else None


def _unreal_name(cpp_name: str | None) -> str | None:
    if not isinstance(cpp_name, str) or not cpp_name:
        return None
    tail = cpp_name.rsplit("::", 1)[-1]
    return re.sub(r"^[AUFIE](?=[A-Z])", "", tail)


def _script_identity(path: Any) -> tuple[str, str] | None:
    if not isinstance(path, str):
        return None
    match = re.fullmatch(r"/Script/([^./]+)\.([^.:]+)", path)
    return (match.group(1), match.group(2)) if match else None


def _asset_from_object(path: Any, assets: set[str]) -> str | None:
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    package = path.split(".", 1)[0].split(":", 1)[0]
    return package if package in assets else None


def _normalized_parameters(function: dict) -> str:
    return re.sub(r"\s+", "", function.get("parameters_raw") or "")


def _function_key(function: dict) -> tuple[Any, ...]:
    return (function.get("qualified_name"), _normalized_parameters(function))


def _identity(kind: str, entity_id: str, name: str | None = None, qualified_name: str | None = None) -> dict:
    return {"kind": kind, "id": entity_id, "name": name, "qualified_name": qualified_name}


class _Builder:
    def __init__(self):
        self.entities: dict[str, list[dict]] = {
            "cpp_types": [], "cpp_functions": [], "cpp_fields": [],
            "blueprint_assets": [], "blueprint_functions": [], "blueprint_variables": [],
        }
        self.relations: list[dict] = []
        self.issues: list[dict] = []
        self.lookup: dict[str, set[str]] = defaultdict(set)
        self._relation_keys: Counter = Counter()

    def entity(self, group: str, record: dict, *terms: Any) -> None:
        self.entities[group].append(record)
        for term in terms:
            if isinstance(term, str) and term:
                self.lookup[term.casefold()].add(record["id"])

    def relation(self, *, kind: str, source: dict, status: str, target: dict | None = None,
                 candidates: list[dict] | None = None, source_file: str | None = None,
                 asset_path: str | None = None, graph_id: str | None = None,
                 node_id: str | None = None, pin_id: str | None = None,
                 source_span: dict | None = None, provenance: list[str] | None = None,
                 evidence: list[dict] | None = None, issues: list[str] | None = None) -> dict:
        if status not in STATUSES:
            raise ValueError("invalid unified resolution status: " + str(status))
        candidates = list(candidates or [])
        issues = list(issues or [])
        if status == "verified" and (target is None or candidates):
            raise ValueError("verified relation requires one exact target and no candidates")
        if status == "candidate" and not candidates:
            raise ValueError("candidate relation requires target candidates")
        if status == "ambiguous" and len(candidates) < 2:
            raise ValueError("ambiguous relation requires at least two candidates")
        if status == "unavailable" and (target is not None or candidates):
            raise ValueError("unavailable relation cannot carry a selected target")
        base = f"{kind}:{source.get('id')}"
        ordinal = self._relation_keys[base]
        self._relation_keys[base] += 1
        record = {
            "id": f"relation:{base}:{ordinal}", "reference_kind": kind,
            "source_identity": source, "target_identity": target,
            "target_candidates": candidates, "source_file": source_file,
            "asset_path": asset_path, "graph_id": graph_id, "node_id": node_id,
            "pin_id": pin_id, "source_span": source_span,
            "provenance": list(provenance or []), "resolution_status": status,
            "evidence": list(evidence or []), "issues": issues,
        }
        self.relations.append(record)
        return record


def _pin_projection(pin: dict) -> dict:
    ptype = pin.get("type") if isinstance(pin.get("type"), dict) else None
    return {"id": pin.get("id"), "name": pin.get("pin_name"), "direction": pin.get("direction"),
            "type": ptype, "hidden": pin.get("hidden"), "orphaned": pin.get("orphaned_pin")}


def _bp_inputs_outputs(graph: dict) -> tuple[list[dict], list[dict], list[dict]]:
    entries, results, returns = [], [], []
    for node in graph.get("nodes") or []:
        pins = [_pin_projection(pin) for pin in node.get("pins") or []]
        if node.get("class") in {"K2Node_FunctionEntry", "K2Node_CustomEvent", "K2Node_Event"}:
            entries.extend(pin for pin in pins if (pin.get("type") or {}).get("pin_category") != "exec")
        if node.get("class") == "K2Node_FunctionResult":
            values = [pin for pin in pins if (pin.get("type") or {}).get("pin_category") != "exec"]
            results.extend(values)
            named = [pin for pin in values if str(pin.get("name") or "").casefold().replace("_", "")
                     in {"returnvalue", "result"}]
            returns.append({
                "node_id": node.get("id"),
                "resolution_status": "candidate" if len(named) == 1 else
                                     ("ambiguous" if len(named) > 1 else "unavailable"),
                "target_candidates": named,
                "evidence": "saved result-pin name only",
                "issues": ["pin role was not verified by UHT/editor declaration metadata"],
            })
    return entries, results, returns


def build_unified_analysis(cpp: dict, blueprints: dict, maps: dict | None = None,
                           native_reference_validation: dict | None = None) -> dict:
    """Combine existing public IRs without upgrading their confidence.

    ``blueprints`` and ``maps`` are summary dictionaries as written to digest.json.
    Optional native validation is a separately produced comparison summary; its
    absence is explicit and never inferred from the graph reader.
    """
    builder = _Builder()
    maps = maps or {}
    precision = (cpp or {}).get("precision") or {}
    types = list(precision.get("types") or [])
    functions = list(precision.get("functions") or [])
    fields = list(precision.get("fields") or [])
    calls = list(precision.get("calls") or [])
    function_by_id = {item.get("id"): item for item in functions if item.get("id")}
    field_by_id = {item.get("id"): item for item in fields if item.get("id")}

    reflected_by_script: dict[tuple[str, str], list[dict]] = defaultdict(list)
    cpp_functions_by_member: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    cpp_fields_by_member: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    functions_by_owner_member: dict[tuple[str, str], list[dict]] = defaultdict(list)
    fields_by_owner_member: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for item in types:
        module = _module_from_file(item.get("source_file"))
        entity = {
            "id": item.get("id"), "kind": item.get("kind"), "symbol_name": item.get("symbol_name"),
            "qualified_name": item.get("qualified_name"), "module_candidate": module,
            "source_file": item.get("source_file"), "source_span": item.get("source_span"),
            "bases": item.get("bases") or [], "parser": item.get("parser"),
            "resolution_status": item.get("resolution_status"), "issues": item.get("issues") or [],
        }
        builder.entity("cpp_types", entity, item.get("symbol_name"), item.get("qualified_name"))
        if item.get("kind") in _REFLECTED_TYPES and module and _unreal_name(item.get("symbol_name")):
            reflected_by_script[(module, _unreal_name(item.get("symbol_name")))].append(item)

    for item in functions:
        module = _module_from_file(item.get("source_file"))
        annotation = item.get("annotation") if isinstance(item.get("annotation"), dict) else None
        entity = {
            "id": item.get("id"), "symbol_name": item.get("symbol_name"),
            "qualified_name": item.get("qualified_name"), "owner": item.get("owner"),
            "module_candidate": module, "declaration_kind": item.get("declaration_kind"),
            "signature_raw": item.get("signature_raw"), "parameters_raw": item.get("parameters_raw"),
            "return_prefix_raw": item.get("return_prefix_raw"), "body_span": item.get("body_span"),
            "source_file": item.get("source_file"), "source_span": item.get("source_span"),
            "unreal_annotation_raw": annotation.get("raw") if annotation else None,
            "resolution_status": item.get("resolution_status"), "issues": item.get("issues") or [],
        }
        builder.entity("cpp_functions", entity, item.get("symbol_name"), item.get("qualified_name"))
        owner = item.get("owner")
        if module and owner and item.get("symbol_name"):
            cpp_functions_by_member[(module, _unreal_name(owner), item["symbol_name"])].append(item)
        if owner and item.get("symbol_name"):
            functions_by_owner_member[(owner, item["symbol_name"])].append(item)

    for item in fields:
        module = _module_from_file(item.get("source_file"))
        annotation = item.get("annotation") if isinstance(item.get("annotation"), dict) else None
        entity = {
            "id": item.get("id"), "symbol_name": item.get("symbol_name"),
            "qualified_name": item.get("qualified_name"), "owner": item.get("owner"),
            "module_candidate": module, "declaration_raw": item.get("declaration_raw"),
            "source_file": item.get("source_file"), "source_span": item.get("source_span"),
            "unreal_annotation_raw": annotation.get("raw") if annotation else None,
            "resolution_status": item.get("resolution_status"), "issues": item.get("issues") or [],
        }
        builder.entity("cpp_fields", entity, item.get("symbol_name"), item.get("qualified_name"))
        owner = item.get("owner")
        if module and owner and item.get("symbol_name"):
            cpp_fields_by_member[(module, _unreal_name(owner), item["symbol_name"])].append(item)
        if owner and item.get("symbol_name"):
            fields_by_owner_member[(owner, item["symbol_name"])].append(item)

    bp_assets = set(blueprints)
    bp_functions: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for asset_path, summary in blueprints.items():
        graph_ir = summary.get("graph_ir") if isinstance(summary.get("graph_ir"), dict) else {}
        for graph in graph_ir.get("graphs") or []:
            name, graph_id = graph.get("name"), graph.get("id")
            if isinstance(name, str) and isinstance(graph_id, str):
                bp_functions[(asset_path, name)].append(
                    _identity("blueprint_function", "blueprint-function:" + graph_id, name, graph_id))
    bp_variables: dict[tuple[str, str], list[dict]] = defaultdict(list)
    graph_statuses, declaration_statuses = Counter(), Counter()

    for asset_path, summary in sorted(blueprints.items()):
        graph_ir = summary.get("graph_ir") if isinstance(summary.get("graph_ir"), dict) else {}
        declaration = summary.get("declaration_ir") if isinstance(summary.get("declaration_ir"), dict) else {}
        graph_statuses[graph_ir.get("status", "unavailable")] += 1
        declaration_statuses[declaration.get("status", "unavailable")] += 1
        asset_id = "blueprint:" + asset_path
        parent = declaration.get("parent_class")
        asset_entity = {
            "id": asset_id, "asset_path": asset_path, "kind": summary.get("kind"),
            "display_parent": summary.get("parent"), "saved_parent_object_path": parent,
            "interfaces": summary.get("interfaces") or [], "graph_ir_status": graph_ir.get("status"),
            "declaration_ir_status": declaration.get("status"), "issues": summary.get("issues") or [],
        }
        builder.entity("blueprint_assets", asset_entity, asset_path, asset_path.rsplit("/", 1)[-1])

        script = _script_identity(parent)
        if script:
            targets = reflected_by_script.get(script, [])
            identities = [_identity("cpp_type", t["id"], t.get("symbol_name"), t.get("qualified_name")) for t in targets]
            status = "candidate" if len(identities) == 1 else ("ambiguous" if len(identities) > 1 else "unavailable")
            builder.relation(
                kind="blueprint_parent_cpp_type", source=_identity("blueprint_asset", asset_id, asset_path),
                status=status, candidates=identities if status != "unavailable" else [], asset_path=asset_path,
                provenance=["declaration_ir:saved-package", "cpp.precision:tree-sitter-cpp"],
                evidence=[{"saved_parent_object_path": parent}, {"module_and_unreal_name": list(script)}],
                issues=["compiler/UHT type identity was not available"] if targets else
                       ["no unique reflected C++ type spelling candidate was observed"],
            )
        elif parent is not None:
            builder.relation(
                kind="blueprint_parent_cpp_type", source=_identity("blueprint_asset", asset_id, asset_path),
                status="unavailable", asset_path=asset_path,
                provenance=["declaration_ir:saved-package"], evidence=[{"saved_parent_object_path": parent}],
                issues=["saved parent is unknown, non-native, or has no /Script module identity"],
            )

        variables = declaration.get("variables")
        if isinstance(variables, list):
            for ordinal, variable in enumerate(variables):
                name = variable.get("name")
                variable_id = f"blueprint-variable:{asset_path}:{name if isinstance(name, str) else ordinal}"
                entity = {"id": variable_id, "asset_path": asset_path, "name": name,
                          "type": variable.get("type"), "flags": variable.get("flags"),
                          "default_value": variable.get("default_value"),
                          "saved_fields": variable.get("saved_fields") or {},
                          "resolution_status": "unavailable" if _unknown(name) else "verified",
                          "issues": [] if isinstance(name, str) and name else ["saved variable identity unavailable"]}
                builder.entity("blueprint_variables", entity, name, asset_path + "::" + str(name))
                if isinstance(name, str) and name:
                    bp_variables[(asset_path, name)].append(entity)

        for graph in graph_ir.get("graphs") or []:
            graph_id = graph.get("id")
            function_id = "blueprint-function:" + str(graph_id)
            inputs, outputs, returns = _bp_inputs_outputs(graph)
            entity = {"id": function_id, "asset_path": asset_path, "graph_id": graph_id,
                      "name": graph.get("name"), "guid_raw": graph.get("guid_raw"),
                      "inputs": inputs, "outputs": outputs, "returns": returns,
                      "resolution_status": "verified" if isinstance(graph_id, str) and graph_id.startswith("/") else "unavailable",
                      "issues": [] if isinstance(graph_id, str) and graph_id.startswith("/") else ["exact graph object path unavailable"]}
            builder.entity("blueprint_functions", entity, graph.get("name"), graph_id)
            _blueprint_graph_relations(builder, asset_path, graph, function_id, bp_assets, bp_variables,
                                       bp_functions, cpp_functions_by_member, cpp_fields_by_member)

    # Level Blueprint pin flow is retained, but no declaration or C++ parent is inferred.
    for asset_path, summary in sorted(maps.items()):
        graph_ir = summary.get("level_bp_graph_ir") if isinstance(summary.get("level_bp_graph_ir"), dict) else {}
        if graph_ir:
            graph_statuses[graph_ir.get("status", "unavailable")] += 1
        for graph in graph_ir.get("graphs") or []:
            graph_id = graph.get("id")
            function_id = "level-blueprint-function:" + str(graph_id)
            inputs, outputs, returns = _bp_inputs_outputs(graph)
            entity = {"id": function_id, "asset_path": asset_path, "graph_id": graph_id,
                      "name": graph.get("name"), "guid_raw": graph.get("guid_raw"),
                      "inputs": inputs, "outputs": outputs, "returns": returns,
                      "resolution_status": "verified" if isinstance(graph_id, str) and graph_id.startswith("/") else "unavailable",
                      "issues": ["map Level Blueprint declarations are outside declaration_ir"]}
            builder.entity("blueprint_functions", entity, graph.get("name"), graph_id)
            _blueprint_graph_relations(builder, asset_path, graph, function_id, bp_assets, bp_variables,
                                       bp_functions, cpp_functions_by_member, cpp_fields_by_member)

    _cpp_relations(builder, precision, function_by_id, field_by_id, functions_by_owner_member,
                   fields_by_owner_member, types)

    native_status = "unavailable"
    native_issues = ["P2 semantic-reference producer was not run for this digest"]
    if isinstance(native_reference_validation, dict):
        native_status = native_reference_validation.get("status", "unavailable")
        native_issues = list(native_reference_validation.get("issues") or [])
        if native_status not in {"passed", "complete"}:
            builder.issues.append({"kind": "native_reference_validation", "status": native_status,
                                   "issues": native_issues,
                                   "differences": native_reference_validation.get("differences") or []})

    input_status = {
        "cpp_precision": precision.get("status", "unavailable"),
        "blueprint_graph_ir": dict(graph_statuses),
        "blueprint_declaration_ir": dict(declaration_statuses),
        "native_semantic_reference_validation": {"status": native_status, "issues": native_issues,
                                                   "engine_execution_required": True},
    }
    partial = (precision.get("status") != "ok" or native_status not in {"passed", "complete"}
               or any(key != "complete" and count for key, count in graph_statuses.items())
               or any(key != "complete" and count for key, count in declaration_statuses.items()))
    status_counts = Counter(item["resolution_status"] for item in builder.relations)
    kind_counts = Counter(item["reference_kind"] for item in builder.relations)
    relations_by_source: dict[str, list[str]] = defaultdict(list)
    relations_by_target: dict[str, list[str]] = defaultdict(list)
    for relation in builder.relations:
        source_id = (relation.get("source_identity") or {}).get("id")
        if source_id:
            relations_by_source[source_id].append(relation["id"])
        targets = [relation.get("target_identity"), *(relation.get("target_candidates") or [])]
        for target in targets:
            target_id = (target or {}).get("id")
            if target_id:
                relations_by_target[target_id].append(relation["id"])
    output = {
        "schema_version": SCHEMA_VERSION, "status": "partial" if partial else "complete",
        "accuracy_contract": {
            "verified": "exact saved source and target identities within an existing IR; not runtime semantics",
            "candidate": "one logical spelling/path candidate; compiler/UHT identity is not proven",
            "ambiguous": "multiple logical target candidates retained",
            "unavailable": "identity evidence is missing or no target candidate is observable",
            "cross_language_verified_count": 0,
            "execution_order": "saved Blueprint pin links are observations; no runtime order is inferred",
        },
        "input_status": input_status, "entities": builder.entities,
        "relations": builder.relations, "lookup_by_name": {k: sorted(v) for k, v in sorted(builder.lookup.items())},
        "relation_index": {
            "by_source": {key: sorted(value) for key, value in sorted(relations_by_source.items())},
            "by_target_or_candidate": {key: sorted(value) for key, value in sorted(relations_by_target.items())},
        },
        "issues": builder.issues,
        "statistics": {
            "entities": {key: len(value) for key, value in builder.entities.items()},
            "relations": len(builder.relations), "by_resolution_status": {key: status_counts.get(key, 0) for key in STATUSES},
            "by_reference_kind": dict(sorted(kind_counts.items())),
        },
    }
    return output


def _blueprint_graph_relations(builder: _Builder, asset_path: str, graph: dict, function_id: str,
                               bp_assets: set[str], bp_variables: dict,
                               bp_functions: dict, cpp_functions_by_member: dict,
                               cpp_fields_by_member: dict) -> None:
    graph_id = graph.get("id")
    for node in graph.get("nodes") or []:
        node_id = node.get("id")
        for pin in node.get("pins") or []:
            pin_id = pin.get("id")
            source = _identity("blueprint_pin", str(pin_id), pin.get("pin_name"))
            category = (pin.get("type") or {}).get("pin_category")
            kind = "blueprint_exec_pin_link" if category == "exec" else "blueprint_data_pin_link"
            for link in pin.get("linked_to_raw") or []:
                target = link.get("target")
                candidates = [_identity("blueprint_pin", str(value)) for value in link.get("candidates") or []]
                if link.get("status") == "resolved" and isinstance(target, str):
                    status, target_identity = "verified", _identity("blueprint_pin", target)
                    candidates = []
                    issues = []
                elif len(candidates) > 1:
                    status, target_identity = "ambiguous", None
                    issues = ["saved pin reference resolves to multiple pins"]
                elif len(candidates) == 1:
                    status, target_identity = "candidate", None
                    issues = ["pin target is a single structural candidate, not exact"]
                else:
                    status, target_identity = "unavailable", None
                    issues = ["saved pin target is unresolved"]
                builder.relation(
                    kind=kind, source=source, status=status, target=target_identity, candidates=candidates,
                    asset_path=asset_path, graph_id=graph_id, node_id=node_id, pin_id=pin_id,
                    provenance=["graph_ir:saved-package", "saved-pin-reference"],
                    evidence=[{"basis": link.get("basis"), "owner_path": link.get("owner_path"),
                               "raw_reference": link.get("reference")}], issues=issues,
                )

        for reference in node.get("semantic_references") or []:
            _semantic_reference_relation(builder, asset_path, graph_id, function_id, node, reference,
                                         bp_assets, bp_variables, bp_functions,
                                         cpp_functions_by_member, cpp_fields_by_member)


def _semantic_reference_relation(builder: _Builder, asset_path: str, graph_id: str, function_id: str,
                                 node: dict, reference: dict, bp_assets: set[str], bp_variables: dict,
                                 bp_functions: dict, cpp_functions_by_member: dict,
                                 cpp_fields_by_member: dict) -> None:
    node_id = node.get("id")
    kind = reference.get("kind", "unknown")
    source = _identity("blueprint_node", str(node_id), node.get("object_name"))
    parent = reference.get("parent") if isinstance(reference.get("parent"), dict) else {}
    parent_path = parent.get("object_path")
    name = reference.get("name")
    if _unknown(name):
        name = None
    if kind in {"macro_graph", "delegate_function", "custom_event"}:
        value = reference.get("value")
        if isinstance(value, str):
            name = value
        elif isinstance(value, dict) and not _unknown(value):
            parent_path = value.get("object_path")
    evidence = [{"saved_reference": reference}, {"node_class": node.get("class")}]
    common = dict(asset_path=asset_path, graph_id=graph_id, node_id=node_id,
                  provenance=["graph_ir:saved-package"], evidence=evidence)

    if kind == "macro_graph" and isinstance(parent_path, str) and parent_path.startswith("/"):
        builder.relation(
            kind="blueprint_macro_graph_reference", source=source, status="verified",
            target=_identity("blueprint_graph_object", parent_path, name, parent_path),
            issues=["exact saved graph object identity; target graph contents may be outside this digest"], **common)
        return

    script = _script_identity(parent_path)
    if script and isinstance(name, str):
        if kind in {"function", "event", "interface_function"}:
            raw = cpp_functions_by_member.get((script[0], script[1], name), [])
            candidates, logical = _logical_function_candidates(raw)
            status = "candidate" if len(logical) == 1 else ("ambiguous" if len(logical) > 1 else "unavailable")
            issues = ["compiler/UHT member identity and runtime dispatch were not verified"]
            if kind in {"event", "interface_function"} or node.get("class") in {"K2Node_Message", "K2Node_CallParentFunction"}:
                issues.append("interface/override/virtual dispatch target remains runtime-dependent")
            annotations = " ".join(
                str((item.get("annotation") or {}).get("raw") or "") for item in raw
                if isinstance(item.get("annotation"), dict))
            if "BlueprintNativeEvent" in annotations or "BlueprintImplementableEvent" in annotations:
                issues.append("generated event thunk and _Implementation dispatch require UHT/runtime validation")
            if any(token in annotations for token in ("Server", "Client", "NetMulticast")):
                issues.append("RPC transport and implementation dispatch require UHT/runtime validation")
            builder.relation(kind="blueprint_cpp_" + kind, source=source, status=status,
                             candidates=candidates if status != "unavailable" else [], issues=issues, **common)
            return
        if kind in {"variable", "delegate"}:
            raw = cpp_fields_by_member.get((script[0], script[1], name), [])
            candidates = [_identity("cpp_field", item["id"], item.get("symbol_name"), item.get("qualified_name")) for item in raw]
            qualified = {item.get("qualified_name") for item in raw}
            status = "candidate" if len(qualified) == 1 else ("ambiguous" if len(qualified) > 1 else "unavailable")
            builder.relation(kind="blueprint_cpp_" + kind, source=source, status=status,
                             candidates=candidates if status != "unavailable" else [],
                             issues=["compiler/UHT member identity was not verified"] if raw else
                                    ["no matching C++ field spelling candidate was observed"], **common)
            return

    parent_asset = _asset_from_object(parent_path, bp_assets)
    function_asset = parent_asset or (asset_path if reference.get("self_context") is True else None)
    if function_asset and isinstance(name, str) and kind in {"function", "event", "interface_function", "delegate_function"}:
        candidates = list(bp_functions.get((function_asset, name), []))
        status = "candidate" if len(candidates) == 1 else ("ambiguous" if len(candidates) > 1 else "unavailable")
        builder.relation(kind="blueprint_function_reference", source=source, status=status,
                         candidates=candidates if status != "unavailable" else [],
                         issues=["saved member GUID is not shared with graph identity; name/path is a candidate"]
                                if candidates else ["matching Blueprint graph candidate unavailable"], **common)
        return
    if parent_asset and isinstance(name, str) and kind == "variable":
        raw = bp_variables.get((parent_asset, name), [])
        candidates = [_identity("blueprint_variable", item["id"], item.get("name")) for item in raw]
        status = "candidate" if len(candidates) == 1 else ("ambiguous" if len(candidates) > 1 else "unavailable")
        builder.relation(kind="blueprint_variable_use", source=source, status=status,
                         candidates=candidates if status != "unavailable" else [],
                         issues=[] if raw else ["saved Blueprint variable declaration candidate unavailable"], **common)
        return

    if parent_asset and isinstance(name, str) and kind == "delegate":
        raw = bp_variables.get((parent_asset, name), [])
        candidates = [_identity("blueprint_variable", item["id"], item.get("name")) for item in raw]
        status = "candidate" if len(candidates) == 1 else ("ambiguous" if len(candidates) > 1 else "unavailable")
        builder.relation(kind="blueprint_delegate_use", source=source, status=status,
                         candidates=candidates if status != "unavailable" else [],
                         issues=["delegate declaration candidate is based on saved asset path and name"] if raw else
                                ["saved Blueprint delegate declaration candidate unavailable"], **common)
        return

    if kind == "variable" and reference.get("self_context") is True and isinstance(name, str):
        raw = bp_variables.get((asset_path, name), [])
        candidates = [_identity("blueprint_variable", item["id"], item.get("name")) for item in raw]
        status = "candidate" if len(candidates) == 1 else ("ambiguous" if len(candidates) > 1 else "unavailable")
        builder.relation(kind="blueprint_variable_use", source=source, status=status,
                         candidates=candidates if status != "unavailable" else [],
                         issues=["self-context is saved, but declaration has no shared member GUID"] if raw else
                                ["self-context variable declaration candidate unavailable"], **common)
        return

    builder.relation(kind="blueprint_reference_" + str(kind), source=source, status="unavailable",
                     issues=["saved owner/member identity is incomplete or has no observable target"], **common)


def _logical_function_candidates(raw: list[dict]) -> tuple[list[dict], set[tuple[Any, ...]]]:
    candidates = [_identity("cpp_function", item["id"], item.get("symbol_name"), item.get("qualified_name")) for item in raw]
    return candidates, {_function_key(item) for item in raw}


def _cpp_relations(builder: _Builder, precision: dict, function_by_id: dict, field_by_id: dict,
                   functions_by_owner_member: dict, fields_by_owner_member: dict, types: list[dict]) -> None:
    type_by_name: dict[str, list[dict]] = defaultdict(list)
    for item in types:
        if item.get("symbol_name"):
            type_by_name[item["symbol_name"]].append(item)
            if item.get("qualified_name") != item.get("symbol_name"):
                type_by_name[item.get("qualified_name")].append(item)

    for item in types:
        for base in item.get("bases") or []:
            raw = type_by_name.get(base.get("name"), [])
            candidates = [_identity("cpp_type", t["id"], t.get("symbol_name"), t.get("qualified_name")) for t in raw]
            unique = {t.get("qualified_name") for t in raw}
            status = "candidate" if len(unique) == 1 else ("ambiguous" if len(unique) > 1 else "unavailable")
            builder.relation(
                kind="cpp_inherits", source=_identity("cpp_type", item["id"], item.get("symbol_name"), item.get("qualified_name")),
                status=status, candidates=candidates if status != "unavailable" else [],
                source_file=item.get("source_file"), source_span=item.get("source_span"),
                provenance=["cpp.precision:tree-sitter-cpp"], evidence=[{"base_syntax": base}],
                issues=["C++ base type lookup was not performed"],
            )

    # ``override`` is direct syntax evidence, but its selected base declaration is a
    # semantic compiler result. Retain every observable base-member spelling candidate.
    for function in function_by_id.values():
        if not re.search(r"\boverride\b", function.get("signature_raw") or ""):
            continue
        owner_types = type_by_name.get(function.get("owner"), [])
        raw: list[dict] = []
        base_syntax: list[str] = []
        for owner_type in owner_types:
            for base in owner_type.get("bases") or []:
                base_name = base.get("name")
                if isinstance(base_name, str):
                    base_syntax.append(base_name)
                    raw.extend(functions_by_owner_member.get((base_name, function.get("symbol_name")), []))
        raw = list({item.get("id"): item for item in raw if item.get("id")}.values())
        candidates, logical = _logical_function_candidates(raw)
        status = "candidate" if len(logical) == 1 else ("ambiguous" if len(logical) > 1 else "unavailable")
        builder.relation(
            kind="cpp_override_candidate",
            source=_identity("cpp_function", function["id"], function.get("symbol_name"), function.get("qualified_name")),
            status=status, candidates=candidates if status != "unavailable" else [],
            source_file=function.get("source_file"), source_span=function.get("source_span"),
            provenance=["cpp.precision:tree-sitter-cpp"],
            evidence=[{"override_syntax": function.get("signature_raw"), "base_syntax": base_syntax}],
            issues=["compiler virtual override resolution was not performed"],
        )

    for call in precision.get("calls") or []:
        raw = [function_by_id[item] for item in call.get("candidates") or [] if item in function_by_id]
        candidates, logical = _logical_function_candidates(raw)
        status = "candidate" if len(logical) == 1 else ("ambiguous" if len(logical) > 1 else "unavailable")
        builder.relation(
            kind="cpp_call", source=_identity("cpp_function", str(call.get("caller_id")), call.get("caller")),
            status=status, candidates=candidates if status != "unavailable" else [],
            source_file=call.get("source_file"), source_span=call.get("source_span"),
            provenance=["cpp.precision:tree-sitter-cpp"],
            evidence=[{"callee_expression": call.get("callee_expression"), "call_kind": call.get("call_kind"),
                       "candidate_status": call.get("candidate_status")}],
            issues=["tree-sitter does not perform type or overload resolution"],
        )

    for access in precision.get("data_accesses") or []:
        caller = function_by_id.get(access.get("function_id"))
        owner = caller.get("owner") if caller else None
        expression = access.get("expression_raw") or access.get("symbol_name") or ""
        names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)
        member = names[-1] if names else None
        raw = fields_by_owner_member.get((owner, member), []) if owner and member else []
        candidates = [_identity("cpp_field", item["id"], item.get("symbol_name"), item.get("qualified_name")) for item in raw]
        unique = {item.get("qualified_name") for item in raw}
        status = "candidate" if len(unique) == 1 else ("ambiguous" if len(unique) > 1 else "unavailable")
        source_id = f"cpp-access:{access.get('source_file')}:{(access.get('source_span') or {}).get('byte_start')}:{access.get('access')}"
        builder.relation(
            kind="cpp_variable_" + str(access.get("access", "access")),
            source=_identity("cpp_access", source_id, expression), status=status,
            candidates=candidates if status != "unavailable" else [], source_file=access.get("source_file"),
            source_span=access.get("source_span"), provenance=["cpp.precision:tree-sitter-cpp"],
            evidence=[{"expression_raw": expression, "containing_function_id": access.get("function_id")}],
            issues=["lexical access does not establish aliasing or a typed member target"],
        )

    for link in precision.get("unreal_function_links") or []:
        source_item = function_by_id.get(link.get("implementation_id"))
        raw = [function_by_id[item] for item in link.get("declaration_candidates") or [] if item in function_by_id]
        candidates, logical = _logical_function_candidates(raw)
        status = "candidate" if len(logical) == 1 else ("ambiguous" if len(logical) > 1 else "unavailable")
        builder.relation(
            kind="cpp_unreal_implementation", source=_identity("cpp_function", str(link.get("implementation_id")),
                                                                 source_item.get("symbol_name") if source_item else None),
            status=status, candidates=candidates if status != "unavailable" else [],
            source_file=source_item.get("source_file") if source_item else None,
            source_span=source_item.get("source_span") if source_item else None,
            provenance=["cpp.precision:tree-sitter-cpp"], evidence=[{"link": link}],
            issues=["UHT generated declarations and runtime RPC/event dispatch were not verified"],
        )


def overview_markdown(index: dict) -> str:
    stats = index["statistics"]
    by_status = stats["by_resolution_status"]
    out = ["# Unified C++ ↔ Blueprint analysis", "",
           f"Schema: **{index['schema_version']}** · status: **{index['status']}**", "",
           "This is a synthesis of saved Blueprint IR and C++ syntax observations. Cross-language links are never",
           "verified without compiler/UHT identity. Saved pin links and exact MacroGraph object paths may be verified",
           "as stored identities; this does not establish runtime execution order or gameplay behavior.", "",
           "## Relation coverage", "",
           f"- verified: {by_status['verified']}", f"- candidate: {by_status['candidate']}",
           f"- ambiguous: {by_status['ambiguous']}", f"- unavailable: {by_status['unavailable']}",
           f"- cross-language verified: {index['accuracy_contract']['cross_language_verified_count']}", "",
           "## Entity counts", ""]
    out.extend(f"- {key}: {value}" for key, value in stats["entities"].items())
    out += ["", "## Input status", "", "```json"]
    import json
    out.append(json.dumps(index["input_status"], ensure_ascii=False, indent=2))
    out += ["```", "", "Use `UNIFIED_ANALYSIS.json` for identities, evidence, candidates and source spans.",
            "`relation_index.by_source` and `by_target_or_candidate` support forward and reverse traversal.", ""]
    return "\n".join(out)


def unresolved_markdown(index: dict) -> str:
    out = ["# Unified ambiguous and unavailable relations", "",
           "Candidates are retained for review. No short-name match below is a verified C++ ↔ Blueprint target.", ""]
    for relation in index["relations"]:
        if relation["resolution_status"] not in {"ambiguous", "unavailable"}:
            continue
        source = relation["source_identity"].get("name") or relation["source_identity"].get("id")
        out.append(f"- `{relation['reference_kind']}` · **{relation['resolution_status']}** · `{source}`")
        if relation["asset_path"]:
            out.append(f"  - asset: `{relation['asset_path']}`")
        if relation["source_file"]:
            line = (relation.get("source_span") or {}).get("line_start")
            out.append(f"  - source: `{relation['source_file']}{':' + str(line) if line else ''}`")
        for issue in relation["issues"]:
            out.append("  - " + issue)
    if len(out) == 4:
        out.append("_No ambiguous or unavailable relation was recorded._")
    return "\n".join(out) + "\n"
