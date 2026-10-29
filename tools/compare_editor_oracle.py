"""Compare independently captured native editor observations with a fresh binary read.

No digest is accepted as an oracle or reused as the actual result. Package hashes
bind both reads to the same saved bytes. A scoped match is not gameplay validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


class OracleError(ValueError):
    pass


def load_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise OracleError(f"duplicate JSON field: {key}")
            result[key] = value
        return result
    def constant(value):
        raise OracleError(f"non-finite JSON constant: {value}")
    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as error:
        raise OracleError(str(error)) from error
    if not isinstance(result, dict):
        raise OracleError("oracle must be a JSON object")
    return result


def object_path(value):
    if not isinstance(value, str) or not value.startswith("/"):
        raise OracleError(f"invalid native object path: {value!r}")
    return value.replace(":", ".", 1)


def display_guid_to_serialized(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", value) or not int(value, 16):
        raise OracleError("pin GUID must be a nonzero four-word Unreal display GUID")
    return b"".join(int(value[i:i + 8], 16).to_bytes(4, "little") for i in range(0, 32, 8)).hex()


def _fname(value):
    # Native FName None prints 'None'; serialized empty FName fields may be ''.
    if isinstance(value, str):
        return None if value.casefold() in ("", "none") else value.casefold()
    return value


def unknown(reason):
    return {"$unavailable": str(reason)}


def _indexed(records, key, label):
    if not isinstance(records, list):
        raise OracleError(f"{label} must be an array")
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise OracleError(f"{label} contains a non-object")
        identity = key(record)
        if identity in result:
            raise OracleError(f"duplicate {label} identity: {identity}")
        result[identity] = record
    return result


def _canonical_type(value):
    if isinstance(value, dict) and ("$unavailable" in value or value.get("status") == "unknown"):
        return dict(value)
    result = dict(value)
    for key in ("category", "subcategory"):
        result[key] = _fname(result[key])
    terminal = result.get("terminal")
    if terminal is not None:
        if isinstance(terminal, dict) and ("$unavailable" in terminal or terminal.get("status") == "unknown"):
            result["terminal"] = dict(terminal)
        else:
            result["terminal"] = {k: terminal[k] for k in ("category", "subcategory", "object_path")}
            for key in ("category", "subcategory"):
                result["terminal"][key] = _fname(terminal[key])
    return result


def validate_native_snapshot(snapshot):
    """Do not turn malformed/partial expected observations into a scoped pass."""
    def scalar(value, kind, label, nullable=False):
        if nullable and value is None:
            return
        if type(value) is not kind:
            raise OracleError(f"native {label} must be {kind.__name__}")
    def type_record(value):
        for key in ("category", "subcategory"):
            scalar(value[key], str, key)
        scalar(value["object_path"], str, "type object path", True)
        scalar(value["container"], int, "container")
        if value["container"] not in (0, 1, 2, 3):
            raise OracleError("invalid native container type")
        for key in ("is_reference", "is_const", "is_weak_pointer"):
            scalar(value[key], bool, key)
        terminal = value["terminal"]
        for key in ("category", "subcategory"):
            scalar(terminal[key], str, "terminal " + key)
        scalar(terminal["object_path"], str, "terminal object path", True)
    if snapshot.get("text_values") != "source":
        raise OracleError("native text fields must be authored source text")
    if snapshot.get("package_dirty") is not False:
        raise OracleError("native snapshot has unsaved or unconfirmed package state")
    scalar(snapshot["asset_class"], str, "asset class")
    scalar(snapshot["parent_class"], str, "parent class", True)
    if not isinstance(snapshot.get("issues"), list) or any(type(i) is not str for i in snapshot["issues"]):
        raise OracleError("native snapshot issues must be strings")
    for variable in snapshot["variables"]:
        for key in ("name", "flags", "category", "default_value"):
            scalar(variable[key], str, "variable " + key)
        type_record(variable["type"])
    for graph in snapshot["graphs"]:
        scalar(graph["name"], str, "graph name")
        for node in graph["nodes"]:
            scalar(node["class"], str, "node class")
            metadata = node["function_metadata"]
            if metadata is not None:
                for key in ("tooltip", "category"):
                    scalar(metadata[key], str, "function " + key)
                scalar(metadata["call_in_editor"], bool, "CallInEditor")
            for pin in node["pins"]:
                for key in ("name", "default_value", "auto_default_value", "default_text_value"):
                    scalar(pin[key], str, "pin " + key)
                scalar(pin["default_object"], str, "default object", True)
                scalar(pin["direction"], int, "pin direction")
                if pin["direction"] not in (0, 1):
                    raise OracleError("invalid native pin direction")
                for key in ("hidden", "orphaned_pin", "not_connectable", "advanced_view"):
                    scalar(pin[key], bool, key)
                type_record(pin["type"])


def canonical_snapshot(snapshot):
    """Native/decoded snapshots share this contract; ordering and layout are irrelevant."""
    if not isinstance(snapshot, dict):
        raise OracleError("snapshot must be an object")
    result = {"asset_class": snapshot["asset_class"], "parent_class": snapshot["parent_class"]}
    result["variables"] = {}
    for name, var in _indexed(snapshot["variables"], lambda v: v["name"], "variable").items():
        result["variables"][name] = {key: var[key] for key in ("type", "flags", "category", "default_value")}
        result["variables"][name]["type"] = _canonical_type(var["type"])
    if isinstance(snapshot["function_graphs"], dict) and "$unavailable" in snapshot["function_graphs"]:
        result["function_graphs"] = snapshot["function_graphs"]
    else:
        result["function_graphs"] = sorted(object_path(p) for p in snapshot["function_graphs"])
        if len(set(result["function_graphs"])) != len(result["function_graphs"]):
            raise OracleError("duplicate function graph")
    result["widget_bindings"] = snapshot["widget_bindings"]
    if isinstance(result["widget_bindings"], list):
        bindings = _indexed(result["widget_bindings"], lambda b: (b["object_name"], b["property_name"]), "widget binding")
        result["widget_bindings"] = {json.dumps(key): value for key, value in bindings.items()}
    result["graphs"] = {}
    graphs = _indexed(snapshot["graphs"], lambda g: object_path(g["object_path"]), "graph")
    for path, graph in graphs.items():
        # Q9 IR explicitly excludes empty graphs. Their presence is recorded in
        # the report's exclusions, never counted as a verified empty graph.
        if not graph["nodes"]:
            continue
        nodes = {}
        for node_path, node in _indexed(graph["nodes"], lambda n: object_path(n["object_path"]), "node").items():
            pins = {}
            for guid, pin in _indexed(node["pins"], lambda p: display_guid_to_serialized(p["guid"]), "pin").items():
                value = {k: pin[k] for k in ("name", "direction", "default_value", "auto_default_value",
                                           "default_object", "default_text_value", "hidden", "orphaned_pin",
                                           "not_connectable", "advanced_view")}
                value["type"] = _canonical_type(pin["type"])
                if isinstance(pin["links"], dict) and "$unavailable" in pin["links"]:
                    value["links"] = pin["links"]
                else:
                    links = [(object_path(link["owner_path"]), display_guid_to_serialized(link["guid"])) for link in pin["links"]]
                    value["links"] = sorted(links)  # Preserve duplicate observations.
                pins[guid] = value
            metadata = node["function_metadata"]
            if isinstance(metadata, dict) and "$unavailable" not in metadata:
                metadata = {k: metadata[k] for k in ("tooltip", "category", "call_in_editor")}
            nodes[node_path] = {"class": node["class"], "pins": pins, "function_metadata": metadata}
        result["graphs"][path] = {"name": graph["name"], "nodes": nodes}
    return result


EXCLUSIONS = ["Empty graphs; graph/node/variable GUIDs and editor layout",
              "Control Rig/RigVM graphs are outside this native-oracle comparison adapter's scope",
              "Map terminal const/weak flags, FText localization identity and effective inherited/CDO values",
              "Function keywords/compact title/flags; widget SourcePath segments",
              "Runtime reachability, compiled behavior and gameplay correctness"]


def compare_snapshots(expected, actual, *, profile="all"):
    if profile not in ("all", "graph"):
        raise OracleError("comparison profile must be all or graph")
    validate_native_snapshot(expected)
    expected, actual = canonical_snapshot(expected), canonical_snapshot(actual)
    if profile == "graph":
        for value in (expected, actual):
            for key in list(value):
                if key not in ("asset_class", "graphs"):
                    del value[key]
            for graph in value["graphs"].values():
                for node in graph["nodes"].values():
                    del node["function_metadata"]
        if not expected["graphs"]:
            return {"checked": 0, "mismatches": [], "unavailable": [{"path": "snapshot/graphs", "reason": "no nonempty native graph to compare"}]}
    result = {"checked": 0, "mismatches": [], "unavailable": []}
    def walk(want, got, path):
        if isinstance(got, dict) and ("$unavailable" in got or got.get("status") == "unknown"):
            result["unavailable"].append({"path": path, "reason": got.get("$unavailable", got.get("reason", "decoder field is unknown"))})
        elif isinstance(want, dict) and isinstance(got, dict):
            for key in sorted(want.keys() | got.keys()):
                location = path + "/" + key
                if key not in want or key not in got:
                    result["mismatches"].append({"path": location, "expected": want.get(key), "actual": got.get(key),
                                                  "reason": "missing or extra identity/field"})
                else:
                    walk(want[key], got[key], location)
        elif type(want) is not type(got) or want != got:
            result["checked"] += 1
            result["mismatches"].append({"path": path, "expected": want, "actual": got})
        else:
            result["checked"] += 1
    walk(expected, actual, "snapshot")
    return result


def _package(root, record):
    path = record.get("asset_path")
    if (not isinstance(path, str) or not path.startswith("/Game/") or "\\" in path
            or any(p in ("", ".", "..") for p in path[len("/Game/"):].split("/")) or "." in path.rsplit("/", 1)[-1]):
        raise OracleError("only unambiguous /Game package paths are supported")
    relative = "Content/" + path[len("/Game/"):] + ".uasset"
    if record.get("package_file") != relative:
        raise OracleError("package_file does not match the mounted asset path")
    full = (root / PurePosixPath(relative)).resolve()
    if not full.is_relative_to(root):
        raise OracleError("package file escapes project root")
    return full


def compare_oracle(oracle, project_root, *, reader=None, profile="all"):
    if profile not in ("all", "graph"):
        raise OracleError("comparison profile must be all or graph")
    if type(oracle.get("schema_version")) is not int or oracle["schema_version"] != 1:
        raise OracleError("unsupported oracle schema")
    if oracle.get("producer") != "unreal-editor-native":
        raise OracleError("oracle producer is not the native editor")
    match = re.match(r"(\d+)\.(\d+)\.", str(oracle.get("engine_version", "")))
    if not match or tuple(map(int, match.groups())) < (5, 7):
        raise OracleError("oracle requires an identified UE 5.7+ editor")
    if not isinstance(oracle.get("project_file"), str) or not oracle["project_file"].endswith(".uproject"):
        raise OracleError("missing source project identity")
    if not isinstance(oracle.get("issues"), list) or any(not isinstance(i, str) for i in oracle["issues"]):
        raise OracleError("oracle issues must be an array of strings")
    assets = _indexed(oracle.get("assets"), lambda a: a["asset_path"], "asset")
    if not assets:
        raise OracleError("an empty oracle cannot verify anything")
    root = Path(project_root).resolve(strict=True)
    exclusions = list(EXCLUSIONS)
    if profile == "graph":
        exclusions.append("Graph profile: parent, variable/function declarations, function metadata and widget bindings are not compared")
    report = {"schema_version": 1, "status": "incomplete", "engine_version": oracle["engine_version"], "profile": profile,
              "scope": "saved-package versus native loaded-editor observations", "exclusions": exclusions,
              "issues": list(oracle["issues"]), "assets": [], "checked": 0}
    for path, asset in assets.items():
        if not isinstance(asset.get("issues"), list) or any(not isinstance(i, str) for i in asset["issues"]):
            raise OracleError("asset issues must be an array of strings")
        item = {"asset_path": path, "checked": 0, "mismatches": [], "unavailable": []}
        report["assets"].append(item)
        if asset["issues"] or not isinstance(asset.get("snapshot"), dict):
            item["unavailable"].append({"path": path, "reason": "; ".join(asset["issues"]) or "native snapshot unavailable"})
            continue
        if asset["snapshot"].get("issues") or asset["snapshot"].get("package_dirty") is not False:
            item["unavailable"].append({"path": path, "reason": "native snapshot has capture gaps or unsaved/unconfirmed package state"})
            continue
        try:
            file = _package(root, asset)
            for key in ("sha256_before", "sha256_after"):
                if not isinstance(asset.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", asset[key]):
                    raise OracleError(f"invalid {key}: {path}")
            before = hashlib.sha256(file.read_bytes()).hexdigest()
            if asset["sha256_before"] != asset["sha256_after"] or before != asset["sha256_before"]:
                raise OracleError("saved package changed between editor capture and binary comparison")
            decoded = reader(file, path) if reader else read_snapshot(file, path, native_class=asset["snapshot"].get("asset_class"))
            if hashlib.sha256(file.read_bytes()).hexdigest() != before:
                raise OracleError("package changed during binary comparison")
            item.update(compare_snapshots(asset["snapshot"], decoded, profile=profile))
            native_nodes = [n for g in asset["snapshot"]["graphs"] for n in g["nodes"]]
            native_pins = [p for n in native_nodes for p in n["pins"]]
            item["native_counts"] = {"graphs": len(asset["snapshot"]["graphs"]), "nodes": len(native_nodes),
                                      "pins": len(native_pins), "link_observations": sum(len(p["links"]) for p in native_pins)}
            if decoded.get("issues"):
                item["unavailable"].append({"path": path, "reason": "decoder reports parse/projection gaps"})
            if not item["checked"] and not item["unavailable"]:
                item["unavailable"].append({"path": path, "reason": "no observations compared for this asset"})
            report["checked"] += item["checked"]
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            item["unavailable"].append({"path": path, "reason": f"{type(error).__name__}: {error}"})
    if any(a["mismatches"] for a in report["assets"]):
        report["status"] = "mismatch"
    elif report["checked"] and not report["issues"] and not any(a["unavailable"] for a in report["assets"]):
        report["status"] = "passed"
    return report


def read_snapshot(path, asset_path, *, native_class=None):
    """Adapter for our existing parser/public graph IR; never used by the exporter."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import bp_reader as B
    import data_reader as R
    if native_class == "ControlRigBlueprint":
        raise OracleError("Control Rig/RigVM graphs are outside this oracle adapter's comparison scope")
    rendered = B.read_blueprint(str(path), asset_path)
    summary, ir = rendered["summary"], rendered["summary"]["graph_ir"]
    parsed, _ = B._parse(str(path))
    ctx = B.Ctx(parsed)
    bp, kind = B._find_blueprint_object(ctx, Path(path).stem)
    if bp is None:
        raise OracleError("Blueprint export is unavailable")
    raw_props = ctx.props(bp)
    exp = next(e for e in parsed.export_map if e.object_name == bp.object_name)
    tagged = R.TaggedReader(str(path), parsed, ctx)
    try:
        items, _ = tagged.export_stream(exp)
        props = dict(items)
    finally:
        tagged.close()
    def ref(value):
        if value in (None, 0):
            return None
        if isinstance(value, dict):
            path = value.get("full_name")
            candidates = []
            for obj in parsed.all_objects:
                if getattr(obj, "object_name", None) != value.get("object_name"):
                    continue
                try:
                    if obj.get_full_name() == path or ctx.full_name(obj) == path:
                        candidates.append(obj)
                except Exception:
                    continue
            return ctx.full_name(candidates[0]) if len(candidates) == 1 else unknown("saved object reference unresolved or ambiguous")
        if not isinstance(value, int) or isinstance(value, bool):
            return unknown("object index unavailable")
        obj = ctx.obj(value)
        return ctx.full_name(obj) if obj is not None else unknown("object index unresolved")
    def pin_type(value, serialized=False):
        # Struct fields are already decoded; no rendered type-label parsing.
        f = B._fields(value) if not serialized else value
        if not f and not serialized:
            return unknown("declaration pin type is opaque to this adapter; no terminal defaults inferred")
        names = ({"category": "pin_category", "subcategory": "pin_subcategory", "object_path": "pin_subcategory_object",
                  "container": "container_type", "is_reference": "is_reference", "is_const": "is_const", "is_weak_pointer": "is_weak_pointer"}
                 if serialized else {"category": "PinCategory", "subcategory": "PinSubCategory", "object_path": "PinSubCategoryObject",
                                     "container": "ContainerType", "is_reference": "bIsReference", "is_const": "bIsConst", "is_weak_pointer": "bIsWeakPointer"})
        result = {}
        for name, source in names.items():
            raw = f.get(source, unknown(f"type field {source} absent"))
            result[name] = ref(raw) if name == "object_path" else raw
        if serialized:
            result["terminal"] = {"category": f["map_key_terminal_category"], "subcategory": f["map_key_terminal_sub_category"],
                                   "object_path": ref(f["map_key_terminal_sub_category_object"])}
        else:
            terminal = B._fields(f.get("PinValueType"))
            result["terminal"] = ({"category": terminal.get("TerminalCategory", unknown("terminal category absent")),
                                    "subcategory": terminal.get("TerminalSubCategory", unknown("terminal subcategory absent")),
                                    "object_path": ref(terminal.get("TerminalSubCategoryObject"))}
                                   if terminal else unknown("declaration terminal type not decoded"))
        return result
    def native_guid(value):
        raw = re.sub(r"[-]", "", value) if isinstance(value, str) else ""
        if not re.fullmatch("[a-fA-F0-9]{32}", raw):
            raise OracleError("decoded pin GUID unavailable")
        return "".join(f"{int.from_bytes(bytes.fromhex(raw[i:i+8]), 'little'):08x}" for i in range(0,32,8))
    pin_targets = {p["id"]: {"owner_path": n["object_path"], "guid": native_guid(p["guid"])}
                   for g in ir["graphs"] for n in g["nodes"] for p in n["pins"]}
    graphs = []
    raw_nodes = {}
    for graph, _ in B._walk_graphs(parsed.graphs):
        for node in graph.nodes:
            if getattr(node, "class_name", None) != "K2Node_FunctionEntry":
                continue
            export = getattr(node, "_export_index", None)
            obj = ctx.obj(export) if export else None
            if obj is not None:
                key = ctx.full_name(obj)
                if key in raw_nodes:
                    previous = raw_nodes[key]
                    if previous is not None and getattr(previous, "_export_index", None) == export:
                        continue  # The same saved export can occur in nested walk views.
                    raw_nodes[key] = None  # Different saved exports: never choose one.
                else:
                    raw_nodes[key] = node
    for graph in ir["graphs"]:
        nodes = []
        for node in graph["nodes"]:
            pins = []
            for pin in node["pins"]:
                links = pin["linked_to_raw"]
                connections = ([pin_targets[r["target"]] for r in links] if all(r["status"] == "resolved" and r["target"] in pin_targets for r in links)
                               else unknown("saved pin link unresolved or ambiguous"))
                pins.append({"guid": native_guid(pin["guid"]), "name": pin["pin_name"], "direction": pin["direction"],
                             "type": pin_type(pin["type"], True), "default_value": pin["defaults"]["default_value"],
                             "auto_default_value": pin["defaults"]["auto_default_value"], "default_object": pin["defaults"]["default_object_path"],
                             "default_text_value": pin["defaults"]["default_text_value"],
                             **{k: pin[k] for k in ("hidden", "orphaned_pin", "not_connectable", "advanced_view")}, "links": connections})
            meta = None
            if node["class"] == "K2Node_FunctionEntry":
                raw = raw_nodes.get(node["object_path"])
                found = B._function_metadata(ctx, raw, str(path), parsed, node["object_path"]) if raw is not None else {}
                meta = {k: found.get(k, unknown("metadata not explicitly decoded")) for k in ("tooltip", "category", "call_in_editor")}
            nodes.append({"object_path": node["object_path"], "class": node["class"], "guid": node["guid_raw"], "pins": pins, "function_metadata": meta})
        graphs.append({"object_path": graph["id"], "name": graph["name"], "nodes": nodes})
    variables = []
    for variable in props.get("NewVariables", []):
        f = B._fields(variable)
        if not isinstance(f.get("VarName"), str):
            raise OracleError("variable declaration opaque or missing name")
        category = f.get("Category")
        variables.append({"name": f["VarName"], "type": pin_type(f.get("VarType")), "flags": str(f["PropertyFlags"]) if "PropertyFlags" in f else unknown("variable flags absent"),
                          "category": category if isinstance(category, str) else getattr(category, "source_string", unknown("category absent")),
                          "default_value": f.get("DefaultValue", unknown("declaration default absent; effective CDO value not inferred"))})
    bindings = None
    if kind == "WidgetBlueprint":
        bindings = []
        for binding in props.get("Bindings", []):
            f = B._fields(binding)
            bindings.append({"object_name": f.get("ObjectName", unknown("binding object absent")),
                             "property_name": f.get("PropertyName", unknown("binding property absent")),
                             "function_name": f.get("FunctionName", unknown("binding function absent")),
                             "kind": f.get("Kind", unknown("binding kind absent"))})
    functions = raw_props.get("FunctionGraphs", [])
    function_paths = ([ref(v) for v in functions] if all(isinstance(ref(v), str) for v in functions)
                      else unknown("declared function graph reference unresolved"))
    return {"asset_class": kind, "parent_class": ref(raw_props.get("ParentClass")), "variables": variables,
            "function_graphs": function_paths,
            "graphs": graphs, "widget_bindings": bindings, "issues": summary["issues"] + ctx.issues}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--profile", choices=("all", "graph"), default="all", help="graph explicitly excludes declaration/metadata/widget comparisons")
    parser.add_argument("--out", type=Path, help="write a new comparison report; existing files are preserved")
    args = parser.parse_args(argv)
    try:
        if args.out:
            destination = args.out.resolve()
            if destination.suffix.lower() != ".json" or destination.exists():
                raise OracleError("comparison output must be a new .json file")
            content = (args.project_root.resolve() / "Content").resolve()
            if destination.is_relative_to(content):
                raise OracleError("comparison output must be outside project Content")
        oracle = load_json(args.oracle.read_text(encoding="utf-8-sig"))
        report = compare_oracle(oracle, args.project_root, profile=args.profile)
        text = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
        if args.out:
            with args.out.open("x", encoding="utf-8") as output:
                output.write(text + "\n")
        print(f"{report['status']}: {len(report['assets'])} assets; {report['checked']} compared scalar/sequence observations. "
              "Scoped editor comparison only; read report exclusions and unavailable fields.")
        if not args.out:
            print(text)
        return 0 if report["status"] == "passed" else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
