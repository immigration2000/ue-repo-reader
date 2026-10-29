"""Compare independently captured native editor observations with a fresh binary read.

No digest is accepted as an oracle or reused as the actual result. Package hashes
bind both reads to the same saved bytes. A scoped match is not gameplay validation.

Declarations (parent class, variables, function graphs, widget bindings) come from
the reader's public ``summary["declaration_ir"]`` projection; this adapter re-parses
nothing to obtain them and never turns an absent saved property into an empty value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

DECLARATION_SCHEMA_VERSION = 1
DECLARATION_BASIS = "saved-tagged-properties"
# Native field names, in the shape the editor bridge writes them.
_VARIABLE_FIELDS = ("name", "type", "flags", "category", "default_value")
_BINDING_FIELDS = ("object_name", "property_name", "function_name", "kind")
_TYPE_FIELDS = ("category", "subcategory", "object_path", "container",
                "is_reference", "is_const", "is_weak_pointer")
_TERMINAL_FIELDS = ("category", "subcategory", "object_path")
# Compared for declarations, where both sides report them; still excluded for graph pins.
_TERMINAL_FLAG_FIELDS = ("is_const", "is_weak_pointer")
_MISSING = object()


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


def _is_unknown(value):
    """Both unknown markers: this adapter's $unavailable and the reader IR's status/reason."""
    return isinstance(value, dict) and ("$unavailable" in value or value.get("status") == "unknown")


def _identity(value, label):
    """An identity is a usable nonempty string (or tuple of them); never an unknown marker."""
    if isinstance(value, tuple):
        if not value:
            raise OracleError(f"{label} identity is empty")
        for item in value:
            _identity(item, label)
        return value
    if type(value) is not str or not value:
        raise OracleError(f"{label} identity is missing or not a nonempty string: {value!r}")
    return value


def _indexed(records, key, label):
    if not isinstance(records, list):
        raise OracleError(f"{label} must be an array")
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise OracleError(f"{label} contains a non-object")
        try:
            identity = _identity(key(record), label)
        except (KeyError, TypeError) as error:
            raise OracleError(f"{label} identity is unusable: {type(error).__name__}: {error}") from error
        if identity in result:
            raise OracleError(f"duplicate {label} identity: {identity}")
        result[identity] = record
    return result


def _select(record, keys, label):
    """Exactly the agreed native fields: provenance and editor-only extras are ignored."""
    if not isinstance(record, dict):
        raise OracleError(f"{label} must be an object")
    missing = [key for key in keys if key not in record]
    if missing:
        raise OracleError(f"{label} is missing {', '.join(missing)}")
    return {key: record[key] for key in keys}


def _canonical_type(value, *, terminal_flags=False):
    if _is_unknown(value):
        return dict(value)
    result = _select(value, _TYPE_FIELDS, "type")
    for key in ("category", "subcategory"):
        result[key] = _fname(result[key])
    terminal = value.get("terminal", _MISSING)
    if terminal is _MISSING:
        raise OracleError("type is missing terminal")
    if _is_unknown(terminal):
        result["terminal"] = dict(terminal)
    else:
        fields = _TERMINAL_FIELDS + (_TERMINAL_FLAG_FIELDS if terminal_flags else ())
        result["terminal"] = _select(terminal, fields, "terminal type")
        for key in ("category", "subcategory"):
            result["terminal"][key] = _fname(result["terminal"][key])
    return result


def validate_native_snapshot(snapshot):
    """Do not turn malformed/partial expected observations into a scoped pass."""
    try:
        _validate_native_snapshot(snapshot)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise OracleError(f"native snapshot is malformed: {type(error).__name__}: {error}") from error


def _validate_native_snapshot(snapshot):
    def scalar(value, kind, label, nullable=False):
        if nullable and value is None:
            return
        if type(value) is not kind:
            raise OracleError(f"native {label} must be {kind.__name__}")
    def records(value, label, nullable=False):
        if nullable and value is None:
            return []
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise OracleError(f"native {label} must be an array of objects")
        return value
    def uint64_decimal(value, label):
        # The bridge prints uint64 flags with %llu; anything else is not that observation.
        scalar(value, str, label)
        if not re.fullmatch(r"0|[1-9][0-9]*", value) or int(value) >= 1 << 64:
            raise OracleError(f"native {label} must be a canonical uint64 decimal string")
    def type_record(value, terminal_flags=False):
        if not isinstance(value, dict):
            raise OracleError("native type must be an object")
        for key in ("category", "subcategory"):
            scalar(value[key], str, key)
        scalar(value["object_path"], str, "type object path", True)
        scalar(value["container"], int, "container")
        if value["container"] not in (0, 1, 2, 3):
            raise OracleError("invalid native container type")
        for key in ("is_reference", "is_const", "is_weak_pointer"):
            scalar(value[key], bool, key)
        terminal = value["terminal"]
        if not isinstance(terminal, dict):
            raise OracleError("native terminal type must be an object")
        for key in ("category", "subcategory"):
            scalar(terminal[key], str, "terminal " + key)
        scalar(terminal["object_path"], str, "terminal object path", True)
        for key in _TERMINAL_FLAG_FIELDS if terminal_flags else ():
            scalar(terminal[key], bool, "terminal " + key)
    if snapshot.get("text_values") != "source":
        raise OracleError("native text fields must be authored source text")
    if snapshot.get("package_dirty") is not False:
        raise OracleError("native snapshot has unsaved or unconfirmed package state")
    scalar(snapshot["asset_class"], str, "asset class")
    scalar(snapshot["parent_class"], str, "parent class", True)
    if not isinstance(snapshot.get("issues"), list) or any(type(i) is not str for i in snapshot["issues"]):
        raise OracleError("native snapshot issues must be strings")
    for variable in records(snapshot["variables"], "variables"):
        for key in ("name", "category", "default_value"):
            scalar(variable[key], str, "variable " + key)
        _identity(variable["name"], "native variable")
        uint64_decimal(variable["flags"], "variable flags")
        type_record(variable["type"], terminal_flags=True)
    if not isinstance(snapshot["function_graphs"], list):
        raise OracleError("native function graphs must be an array")
    for declared in snapshot["function_graphs"]:
        # object_path() refuses anything that is not a native '/...' object path.
        object_path(declared)
    for binding in records(snapshot["widget_bindings"], "widget bindings", nullable=True):
        for key in ("object_name", "property_name", "function_name"):
            scalar(binding[key], str, "binding " + key)
        _identity((binding["object_name"], binding["property_name"]), "native widget binding")
        # A bool is not an acceptable native binding kind, and type() is what rules it out.
        scalar(binding["kind"], int, "binding kind")
        if binding["kind"] not in (0, 1):
            raise OracleError("native widget binding kind must be EBindingKind Function(0) or Property(1)")
    for graph in records(snapshot["graphs"], "graphs"):
        scalar(graph["name"], str, "graph name")
        for node in records(graph["nodes"], "graph nodes"):
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
    # A whole declaration collection may be unknown (the saved property is absent or
    # undecodable). It stays unknown here: an empty collection is a different claim.
    variables = snapshot["variables"]
    if _is_unknown(variables):
        result["variables"] = dict(variables)
    else:
        result["variables"] = {}
        for name, var in _indexed(variables, lambda v: v["name"], "variable").items():
            record = _select(var, ("type", "flags", "category", "default_value"), f"variable {name}")
            record["type"] = _canonical_type(record["type"], terminal_flags=True)
            result["variables"][name] = record
    if _is_unknown(snapshot["function_graphs"]):
        result["function_graphs"] = dict(snapshot["function_graphs"])
    else:
        if not isinstance(snapshot["function_graphs"], list):
            raise OracleError("function graphs must be an array or an unknown marker")
        result["function_graphs"] = sorted(object_path(p) for p in snapshot["function_graphs"])
        if len(set(result["function_graphs"])) != len(result["function_graphs"]):
            raise OracleError("duplicate function graph")
    bindings = snapshot["widget_bindings"]
    if bindings is None or _is_unknown(bindings):
        result["widget_bindings"] = None if bindings is None else dict(bindings)
    else:
        indexed = _indexed(bindings, lambda b: (b["object_name"], b["property_name"]), "widget binding")
        result["widget_bindings"] = {json.dumps(key, ensure_ascii=False): _select(value, _BINDING_FIELDS, "widget binding")
                                     for key, value in indexed.items()}
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
                if _is_unknown(pin["links"]):
                    value["links"] = dict(pin["links"])
                else:
                    links = [(object_path(link["owner_path"]), display_guid_to_serialized(link["guid"])) for link in pin["links"]]
                    value["links"] = sorted(links)  # Preserve duplicate observations.
                pins[guid] = value
            metadata = node["function_metadata"]
            if isinstance(metadata, dict) and not _is_unknown(metadata):
                metadata = _select(metadata, ("tooltip", "category", "call_in_editor"), "function metadata")
            nodes[node_path] = {"class": node["class"], "pins": pins, "function_metadata": metadata}
        result["graphs"][path] = {"name": graph["name"], "nodes": nodes}
    return result


EXCLUSIONS = ["Empty graphs; graph/node/variable GUIDs and editor layout",
              "Control Rig/RigVM graphs are outside this native-oracle comparison adapter's scope",
              "Graph-pin map terminal const/weak flags (compared for variable declarations), "
              "FText localization identity and effective inherited/CDO values",
              "Declarations are the asset's own saved properties: inherited variables, "
              "ubergraph/macro/interface graph lists and component/widget-tree declarations",
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
        if _is_unknown(got):
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


def _declaration_ir(summary):
    """The reader's public declaration projection, refused outright when it is not the agreed one."""
    ir = summary.get("declaration_ir")
    if not isinstance(ir, dict):
        raise OracleError("the reader exposes no declaration_ir; declarations cannot be compared")
    version = ir.get("schema_version")
    if type(version) is not int or version != DECLARATION_SCHEMA_VERSION or ir.get("basis") != DECLARATION_BASIS:
        raise OracleError(f"unsupported declaration_ir: schema {version!r}, basis {ir.get('basis')!r}")
    return ir


def _project(record, fields, context):
    """Native fields only, keeping every unknown the IR reported and dropping its provenance.

    ``saved_fields`` says whether each native key was saved, absent or unknown. An
    absent saved value is an unknown value here; it is never read as a default.
    """
    saved = record.get("saved_fields")
    saved = saved if isinstance(saved, dict) else {}
    result = {}
    for name in fields:
        value = record.get(name, _MISSING)
        state = saved.get(name)
        if value is _MISSING:
            result[name] = unknown(f"{context} {name} is absent from the reader's declaration projection")
        elif _is_unknown(value):
            result[name] = dict(value)
        elif state is not None and state != "saved":
            result[name] = unknown(f"{context} {name} is reported {state} in the saved package")
        else:
            result[name] = value
    return result


def _declaration_type(value, context):
    """A declaration's native type record; an undecoded terminal stays unknown, never empty."""
    if _is_unknown(value):
        return dict(value)
    if not isinstance(value, dict):
        return unknown(f"{context} type is not a decoded record")
    result = _project(value, _TYPE_FIELDS, context + " type")
    terminal = value.get("terminal", _MISSING)
    if _is_unknown(terminal):
        result["terminal"] = dict(terminal)
    elif isinstance(terminal, dict):
        result["terminal"] = _project(terminal, _TERMINAL_FIELDS + _TERMINAL_FLAG_FIELDS,
                                      context + " terminal type")
    else:
        result["terminal"] = unknown(f"{context} terminal type was not decoded; no empty terminal is assumed")
    return result


def _declaration_records(value, fields, identity, context):
    """One IR collection: unknown stays unknown, and no record is dropped to keep the rest usable.

    A record whose identity is missing or duplicated makes the whole collection
    unknown, because a partial list would read as a complete one.
    """
    if _is_unknown(value):
        return dict(value)
    if not isinstance(value, list):
        return unknown(f"{context} were not projected as a list; the saved collection is unknown")
    records, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            return unknown(f"{context} contain a record that is not an object; the collection is unknown")
        named = item.get(identity[0])
        label = f"{context} {named}" if isinstance(named, str) and named else context
        record = _project(item, fields, label)
        if "type" in record:
            record["type"] = _declaration_type(record["type"], label)
        try:
            key = _identity(tuple(record[name] for name in identity), context)
        except OracleError as error:
            return unknown(f"{context} identity is unusable ({error}); the whole collection is unknown")
        if key in seen:
            return unknown(f"{context} repeat the identity {key}; the whole collection is unknown")
        seen.add(key)
        records.append(record)
    return records


def _declaration_snapshot(ir, *, widget):
    """The declaration half of a decoded snapshot, straight from the public IR."""
    saved = ir.get("saved_fields")
    saved = saved if isinstance(saved, dict) else {}
    def field(name):
        value = ir.get(name, unknown(f"declaration_ir has no {name}"))
        state = saved.get(name)
        if _is_unknown(value) or state is None or state == "saved":
            return value
        if name == "widget_bindings" and value is None and not widget:
            # A non-widget Blueprint has no binding list to save: class applicability,
            # not missing data. Every other null stays unknown when the tag was absent.
            return None
        return unknown(f"{name} is reported {state} in the saved package")
    parent = field("parent_class")
    if not (parent is None or _is_unknown(parent) or isinstance(parent, str) and parent.startswith("/")):
        parent = unknown("parent class is not a native object path or null")
    declared = field("function_graphs")
    if not _is_unknown(declared):
        if (not isinstance(declared, list)
                or any(not isinstance(p, str) or not p.startswith("/") for p in declared)):
            declared = unknown("declared function graph references are unresolved or not native paths")
        elif len({p.replace(":", ".", 1) for p in declared}) != len(declared):
            declared = unknown("declared function graphs repeat an object path; the collection is unknown")
        else:
            declared = list(declared)
    bindings = field("widget_bindings")
    if bindings is None:
        # Null is the native answer for a non-widget Blueprint; a widget must still report its list.
        bindings = None if not widget else unknown("widget Blueprint reported no binding list at all")
    else:
        bindings = _declaration_records(bindings, _BINDING_FIELDS, ("object_name", "property_name"),
                                        "widget bindings")
    return {"parent_class": dict(parent) if _is_unknown(parent) else parent,
            "variables": _declaration_records(field("variables"), _VARIABLE_FIELDS, ("name",),
                                              "variable declarations"),
            "function_graphs": dict(declared) if _is_unknown(declared) else declared,
            "widget_bindings": bindings}


def read_snapshot(path, asset_path, *, native_class=None):
    """Adapter for our existing parser and public graph/declaration IRs; never used by the exporter."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import bp_reader as B
    if native_class == "ControlRigBlueprint":
        raise OracleError("Control Rig/RigVM graphs are outside this oracle adapter's comparison scope")
    rendered = B.read_blueprint(str(path), asset_path)
    summary, ir = rendered["summary"], rendered["summary"]["graph_ir"]
    declarations = _declaration_ir(summary)
    # The second parse is only for the raw function-entry nodes the metadata reader needs;
    # declarations come from the public IR above, not from another property read here.
    parsed, _ = B._parse(str(path))
    ctx = B.Ctx(parsed)
    bp, kind = B._find_blueprint_object(ctx, Path(path).stem)
    if bp is None:
        raise OracleError("Blueprint export is unavailable")
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
    def pin_type(value):
        """Graph-pin types from the Q9 graph IR; declaration types come from the declaration IR."""
        if not isinstance(value, dict):
            return unknown("graph pin type was not projected by the reader")
        def fields(names):
            projected = {}
            for name, source in names.items():
                raw = value.get(source, unknown(f"type field {source} absent"))
                projected[name] = ref(raw) if name == "object_path" else raw
            return projected
        result = fields({"category": "pin_category", "subcategory": "pin_subcategory",
                         "object_path": "pin_subcategory_object", "container": "container_type",
                         "is_reference": "is_reference", "is_const": "is_const",
                         "is_weak_pointer": "is_weak_pointer"})
        # Terminal const/weak flags are not projected for graph pins and stay out of scope.
        result["terminal"] = fields({"category": "map_key_terminal_category",
                                     "subcategory": "map_key_terminal_sub_category",
                                     "object_path": "map_key_terminal_sub_category_object"})
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
                             "type": pin_type(pin["type"]), "default_value": pin["defaults"]["default_value"],
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
    # The native bridge reports a binding list for every UWidgetBlueprint, editor utility ones included.
    declared = _declaration_snapshot(declarations, widget=kind in ("WidgetBlueprint", "EditorUtilityWidgetBlueprint"))
    reported = declarations.get("issues") or []
    if not isinstance(reported, list):
        reported = [{"stage": "declaration_ir", "context": asset_path,
                     "message": f"declaration_ir issues is {type(reported).__name__}, not a list"}]
    return {"asset_class": kind, "graphs": graphs, **declared,
            "issues": summary["issues"] + ctx.issues + list(reported)}


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
