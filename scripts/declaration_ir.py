"""Saved Blueprint declarations, without display-label parsing or default inference.

Serialization facts checked against installed UE 5.7/5.8 EdGraphPin.cpp and
EdGraphNode.cpp; this is our own bounded decoder, not copied engine code.
Public API reference: https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/FEdGraphTerminalType
"""
from __future__ import annotations

import struct
from pathlib import Path

SCHEMA_VERSION = 1
_FRAMEWORK = "3f74fccf8044b043df14919373201d17"
_RELEASE = "22d5549cbe4f26a846072194d082b461"
_UE5 = "425e9bd8464dbd24a8ac1284791764df"


def unknown(reason):
    return {"status": "unknown", "reason": reason}


def _fields(value):
    if isinstance(value, dict):
        return value.get("fields", value) if isinstance(value.get("fields", value), dict) else {}
    return dict(getattr(value, "fields", {}) or {})


def reference(ctx, value):
    """Resolve an exact package index or unique tagged reference; never a short name."""
    if isinstance(value, int) and not isinstance(value, bool):
        if value == 0:
            return None
        try:
            obj = ctx.obj(value)
            path = ctx.full_name(obj) if obj is not None else None
        except (AttributeError, IndexError, TypeError, ValueError):
            path = None
        return path if isinstance(path, str) and path.startswith("/") else unknown("object index unresolved")
    if isinstance(value, dict):
        path = value.get("full_name")
        candidates = []
        for obj in ctx.r.all_objects:
            if getattr(obj, "object_name", None) != value.get("object_name"):
                continue
            try:
                if ctx.full_name(obj) == path or obj.get_full_name() == path:
                    candidates.append(obj)
            except (AttributeError, TypeError, ValueError):
                continue
        if len(candidates) == 1:
            path = ctx.full_name(candidates[0])
            if isinstance(path, str) and path.startswith("/"):
                return path
    return unknown("saved object reference unresolved or absent")


def decode_pin_type(ctx, raw, summary):
    """Decode a complete modern native FEdGraphPinType blob, retaining saved bytes.

    Older saved layouts stay unknown. No engine version is inferred from project
    association, byte length or a rendered label. Bool archive fields are int32.
    """
    versions = {str(v.guid).lower(): v.version for v in (getattr(summary, "custom_versions", None) or [])}
    if (getattr(summary, "file_version_ue4", 0) < 518
            or versions.get(_FRAMEWORK, -1) < 37
            or versions.get(_RELEASE, -1) < 31
            or versions.get(_UE5, -1) < 36):
        return {**unknown("saved pin type layout outside the verified modern version gates"),
                "raw_hex": raw.hex() if isinstance(raw, bytes) else None}
    if not isinstance(raw, bytes):
        return unknown("native pin type bytes unavailable")
    cursor = 0

    def take(fmt):
        nonlocal cursor
        size = struct.calcsize(fmt)
        if cursor + size > len(raw):
            raise ValueError("truncated native pin type")
        result = struct.unpack_from(fmt, raw, cursor)
        cursor += size
        return result[0] if len(result) == 1 else result

    def fname():
        index, number = take("<ii")
        if not 0 <= index < len(ctx.name_map) or number < 0:
            raise ValueError("invalid saved FName index or number")
        return ctx.fname(index, number)

    def boolean():
        value = take("<i")
        if value not in (0, 1):
            raise ValueError("invalid archive boolean")
        return bool(value)

    try:
        output = {"category": fname(), "subcategory": fname()}
        obj = take("<i")
        output.update(object_index=obj, object_path=reference(ctx, obj), container=take("<B"))
        if output["container"] not in (0, 1, 2, 3):
            raise ValueError("invalid container kind")
        if output["container"] == 3:
            terminal = {"category": fname(), "subcategory": fname()}
            obj = take("<i")
            terminal.update(object_index=obj, object_path=reference(ctx, obj), is_const=boolean())
            terminal["is_weak_pointer"] = boolean()
            terminal["is_uobject_wrapper"] = boolean()
            output["terminal"] = terminal
        else:
            output["terminal"] = unknown("terminal type not serialized for a non-map declaration")
        output["is_reference"], output["is_weak_pointer"] = boolean(), boolean()
        member_parent = take("<i")
        member_name = fname()
        output["member_reference"] = {"parent_index": member_parent, "parent_path": reference(ctx, member_parent),
                                      "name": member_name, "guid_raw": raw[cursor:cursor + 16].hex()}
        take("<16s")
        output["is_const"] = boolean()
        output["is_uobject_wrapper"] = boolean()
        output["serialize_single_precision"] = boolean()
        if cursor != len(raw):
            raise ValueError("unconsumed native pin type bytes")
        output["raw_hex"] = raw.hex()
        return output
    except (ValueError, struct.error, IndexError, TypeError, AttributeError) as error:
        return {**unknown(str(error)), "raw_hex": raw.hex()}


def build_declaration_ir(path, result, ctx, bp_obj, kind):
    """Read the exact Blueprint tagged export. Absent tags remain unknown.

    Every collection and record retains presence information. Explicit zero/false/
    empty are values; absent properties never establish effective class defaults.
    This API is independent of Markdown and excludes CDO/inherited/runtime values.
    """
    issues = []
    output = {"schema_version": SCHEMA_VERSION, "basis": "saved-tagged-properties", "issues": issues}
    is_map = Path(path).suffix.lower() == ".umap"
    if bp_obj is None or is_map:
        # read_blueprint also renders map Level Script graphs. Their
        # declarations require a map-specific export selector outside this API.
        # Their absence here is not a damaged tagged stream.
        reason = ("map Level Blueprint declarations are outside this projection"
                  if is_map else "Blueprint declaration export unavailable")
        output.update({key: unknown(reason)
                       for key in ("parent_class", "variables", "function_graphs", "widget_bindings")})
        output.update(status="partial", saved_fields={})
        return output

    def failure(context, message):
        item = {"stage": "declaration_ir", "context": str(context), "message": str(message)}
        if item not in ctx.issues:
            ctx.issues.append(item)
        if item not in issues:
            issues.append(item)
    try:
        import data_reader as D
        exports = [e for e in result.export_map if e.object_name == bp_obj.object_name]
        if len(exports) != 1:
            raise ValueError("Blueprint export identity missing or ambiguous")
        reader = D.TaggedReader(str(path), result, ctx)
        reader.preserve_object_indices = True
        checkpoint = len(ctx.issues)
        try:
            items, _ = reader.export_stream(exports[0])
        finally:
            reader.close()
        issues.extend(dict(i) for i in ctx.issues[checkpoint:])
        props = {}
        for name, value in items:
            if name in props:
                raise ValueError("duplicate saved declaration property: " + str(name))
            props[name] = value
    except Exception as error:  # Preserve the failure, never an empty declaration set.
        output.update({key: unknown(str(error)) for key in ("parent_class", "variables", "function_graphs", "widget_bindings")})
        failure(getattr(bp_obj, "object_name", "?"), str(error))
        output.update(status="partial", saved_fields={})
        return output

    def field(fields, source, kind):
        if source not in fields:
            return unknown("saved field " + source + " absent")
        value = fields[source]
        if isinstance(value, D.UnreadableValue):
            return unknown("saved field " + source + " unreadable: " + value.reason)
        if kind == "text":
            value = value if isinstance(value, str) else getattr(value, "source_string", None)
        elif kind == "reference":
            return reference(ctx, value)
        elif kind == "flags":
            return str(value) if type(value) is int and 0 <= value < 2**64 else unknown("invalid uint64 flags")
        if kind == "binding_kind":
            # ByteProperty enum names are retained by the tagged reader.
            if value in ("EBindingKind::Function", "Function"):
                return 0
            if value in ("EBindingKind::Property", "Property"):
                return 1
            return value if type(value) is int and value in (0, 1) else unknown("invalid or opaque binding kind")
        return value if isinstance(value, str) else unknown("saved field " + source + " unreadable")

    def presence(fields, mapping):
        return {target: "saved" if source in fields else "absent" for target, source in mapping.items()}

    def records(source, mapping, identity, project):
        if source not in props:
            return unknown("saved field " + source + " absent")
        value = props[source]
        if not isinstance(value, list):
            return unknown("saved field " + source + " is not a decoded array")
        records, seen = [], set()
        for item in value:
            f = _fields(item)
            record = project(f)
            record["saved_fields"] = presence(f, mapping)
            key = tuple(record.get(k) for k in identity)
            if any(not isinstance(k, str) or not k for k in key) or key in seen:
                return unknown("saved " + source + " record identity missing, unreadable or duplicated")
            seen.add(key)
            records.append(record)
        return records

    var_fields = {"name": "VarName", "type": "VarType", "flags": "PropertyFlags", "category": "Category", "default_value": "DefaultValue"}

    def variable(f):
        vt = f.get("VarType")
        raw = vt.get("raw_data") if isinstance(vt, dict) else None
        decoded = decode_pin_type(ctx, raw, result.summary)
        if (isinstance(raw, bytes) and decoded.get("status") == "unknown"
                and not decoded["reason"].startswith("saved pin type layout outside")):
            failure(str(f.get("VarName", "?")) + ".VarType", decoded["reason"])
        return {"name": field(f, "VarName", "string"), "type": decoded,
                "flags": field(f, "PropertyFlags", "flags"), "category": field(f, "Category", "text"),
                "default_value": field(f, "DefaultValue", "string")}

    output["variables"] = records("NewVariables", var_fields, ("name",), variable)
    output["parent_class"] = field(props, "ParentClass", "reference")
    functions = props.get("FunctionGraphs")
    output["function_graphs"] = ([reference(ctx, v) for v in functions] if isinstance(functions, list)
                                 else unknown("saved FunctionGraphs absent or not a decoded array"))
    if kind in ("WidgetBlueprint", "EditorUtilityWidgetBlueprint"):
        mapping = {"object_name": "ObjectName", "property_name": "PropertyName", "function_name": "FunctionName", "kind": "Kind"}
        output["widget_bindings"] = records("Bindings", mapping, ("object_name", "property_name"),
                                            lambda f: {k: field(f, v, "binding_kind" if k == "kind" else "string") for k, v in mapping.items()})
    else:
        output["widget_bindings"] = None  # Not applicable, not an inferred saved empty list.
    output["saved_fields"] = presence(props, {"variables": "NewVariables", "parent_class": "ParentClass",
                                             "function_graphs": "FunctionGraphs", "widget_bindings": "Bindings"})

    def has_unknown(value):
        if isinstance(value, dict):
            return value.get("status") == "unknown" or any(has_unknown(v) for v in value.values())
        return isinstance(value, list) and any(has_unknown(v) for v in value)

    output["status"] = "partial" if issues or has_unknown(output) else "complete"
    return output
