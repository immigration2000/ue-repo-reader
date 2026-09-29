"""Blueprint .uasset -> AI-readable Markdown, without the Unreal Editor.

Built on soatori/uasset_read (pinned commit), plus compatibility patches for
assets that were last saved by older engines (UE 4.2x, UE 5.0-5.3).

Public entry points:
    ensure_uasset_read()                 -> make the parser importable (auto-clone if missing)
    read_blueprint(path, game_path)      -> dict(markdown=..., summary=...)
"""
from __future__ import annotations

import logging
import os
import struct
import subprocess
import sys
from pathlib import Path

UASSET_READ_REPO = "https://github.com/soatori/uasset_read.git"
UASSET_READ_COMMIT = "a33da094177c3000d5eed5b246f5634b9764042c"

_PATCHED = False
# Which version-gated pin fields exist in the package currently being parsed.
_FIELDS = {"source_index": True, "single_precision": True, "uobject_wrapper": True}
# UE 5.8 appends an int32 to FTextHistory_Base (namespace/key/source); older engines don't.
_TEXT = {"base_extra": False, "override": None}


# =========================================================================== setup

def ensure_uasset_read(cache_dir: str | None = None) -> None:
    """Import uasset_read, cloning the pinned commit into a cache dir if needed."""
    try:
        import uasset_read  # noqa: F401
        return
    except ImportError:
        pass
    cache = Path(cache_dir or os.environ.get("UE_REPO_READER_CACHE")
                 or Path.home() / ".cache" / "ue-repo-reader")
    dest = cache / f"uasset_read-{UASSET_READ_COMMIT[:10]}"
    if not (dest / "src" / "uasset_read").exists():
        dest.mkdir(parents=True, exist_ok=True)
        git = ["git", "-C", str(dest)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["fetch", "-q", "--depth", "1", UASSET_READ_REPO, UASSET_READ_COMMIT], check=True)
        subprocess.run(git + ["checkout", "-q", "FETCH_HEAD"], check=True)
    sys.path.insert(0, str(dest / "src"))
    import uasset_read  # noqa: F401


def _install_patches() -> None:
    """Patch uasset_read so that assets saved by older engines parse correctly.

    0. Map-typed pins: the value terminal type has three bools uasset_read does not read.
    1. Pre-5.4 packages have no ScriptSerializationEnd offset in the export table, so the
       parser seeks to the wrong place for the pin array. We locate the end of the tagged
       property stream ourselves (the 'None' terminator) and fill the offsets in.
    2. Some pin fields only exist in newer engines (SourceIndex, bSerializeAsSinglePrecisionFloat,
       bIsUObjectWrapper). _parse() probes which combination fits each file.
    3. UE 5.8 serializes one extra int32 after a Base-history FText (namespace/key/source string).
       Enabled per file from the header's saved-by engine version; _parse() also probes it.
    """
    global _PATCHED
    if _PATCHED:
        return
    from uasset_read import archive as A
    from uasset_read.serializers import graph_node as GN
    from uasset_read.serializers.property_tags import read_property_tag

    orig_i32, orig_bool = A.FArchive.read_i32, A.FArchive.read_bool

    def read_i32(self, key=""):
        if key == "Pin.SourceIndex" and not _FIELDS["source_index"]:
            return -1
        value = orig_i32(self, key)
        if key == "PinType.TerminalSubCategoryObject":
            # FEdGraphTerminalType (Map value type) also stores bTerminalIsConst, bTerminalIsWeakPointer
            # and bTerminalIsUObjectWrapper; uasset_read stops after the object reference.
            for _ in range(3):
                orig_i32(self, "PinType.TerminalBool")
        return value

    def read_bool(self, key=""):
        if key == "PinType.bSerializeAsSinglePrecisionFloat" and not _FIELDS["single_precision"]:
            return False
        if key == "PinType.bIsUObjectWrapper" and not _FIELDS["uobject_wrapper"]:
            return False
        return orig_bool(self, key)

    A.FArchive.read_i32 = read_i32
    A.FArchive.read_bool = read_bool

    orig_script = GN._read_node_script_serial

    def script_serial(archive, name_map, summary, node_export, import_map, export_map, linker, node_name):
        if not node_export.has_script_serialization and node_export.serial_size > 0:
            start = node_export.serial_offset
            limit = start + node_export.serial_size
            here = archive.tell()
            try:
                archive.seek(start)
                if summary.file_version_ue5 >= 1011:
                    ctrl = archive.read_u8()
                    if ctrl & 0x02:
                        archive.read_u8()
                for _ in range(4000):
                    if archive.tell() >= limit:
                        break
                    tag = read_property_tag(archive, name_map, tolerant=True)
                    if tag.name == "None":
                        node_export.script_serialization_start_offset = 0
                        node_export.script_serialization_end_offset = archive.tell() - start
                        break
                    archive.seek(tag.value_end_offset)
            except Exception:
                pass
            finally:
                archive.seek(here)
        return orig_script(archive, name_map, summary, node_export, import_map, export_map, linker, node_name)

    GN._read_node_script_serial = script_serial

    # ---- 3. UE 5.8 FText
    from uasset_read.serializers import graph as G
    from uasset_read.parsers import property_types as PT
    from uasset_read.parsers import property_parser as PP
    import importlib
    PU = importlib.import_module("uasset_read.parse_uasset")  # the package re-exports a function of the same name

    orig_hist = G.read_ftext_with_history

    def read_ftext_with_history(archive, history_type, tolerant=True):
        value, consumed = orig_hist(archive, history_type, tolerant)
        if history_type == 0 and _TEXT["base_extra"]:
            archive.read_i32()
            consumed += 4
        return value, consumed

    G.read_ftext_with_history = read_ftext_with_history
    GN.read_ftext_with_history = read_ftext_with_history

    orig_text_prop = PT.parse_text_property

    def parse_text_property(tag, archive):
        start = archive.tell()
        value = orig_text_prop(tag, archive)
        if _TEXT["base_extra"]:
            here = archive.tell()
            archive.seek(start + 4)
            history = archive.read_u8()
            archive.seek(here)
            if history == 0:
                archive.read_i32()
        return value

    PT.parse_text_property = parse_text_property
    PP._TYPE_HANDLER_MAP = None  # rebuild the dispatch table with the patched handler

    orig_linker_parse = PU.parse_uasset_with_linker

    def parse_uasset_with_linker(path, *args, **kwargs):
        _TEXT["base_extra"] = _TEXT["override"] if _TEXT["override"] is not None else _saved_with_58_or_later(path)
        return orig_linker_parse(path, *args, **kwargs)

    PU.parse_uasset_with_linker = parse_uasset_with_linker
    _PATCHED = True


def _saved_with_58_or_later(path: str) -> bool:
    """Read only the package summary and check SavedByEngineVersion >= 5.8."""
    try:
        from uasset_read.archive import FArchive
        from uasset_read.serializers.package_summary import read_package_summary
        with FArchive(path, tolerant=True) as ar:
            s = read_package_summary(ar)
        ev = getattr(s, "saved_by_engine_version", None)
        if ev is None or not getattr(ev, "major", 0):
            ev = getattr(s, "compatible_with_engine_version", None)
        major, minor = getattr(ev, "major", 0) or 0, getattr(ev, "minor", 0) or 0
        return (major, minor) >= (5, 8)
    except Exception:
        return False


# =========================================================================== parsing

_UE5_COMBOS = [(1, 1, 1), (1, 0, 1), (0, 1, 1), (0, 0, 1)]
_UE4_COMBOS = [(0, 0, 1), (0, 0, 0), (1, 0, 1), (1, 1, 1)]


def _walk_graphs(graphs, depth=0):
    for g in graphs:
        yield g, depth
        yield from _walk_graphs(g.subgraphs, depth + 1)


def _pin_score(result):
    total = ok = 0
    seen = set()
    for g, _ in _walk_graphs(result.graphs):
        for n in g.nodes:
            key = getattr(n, "_export_index", None) or id(n)
            if key in seen or n.class_name == "EdGraphNode_Comment":
                continue
            seen.add(key)
            total += 1
            ok += bool(n.pins)
    return ok, total


def _parse(path: str):
    """Parse with the pin-field combination that makes the most nodes readable."""
    from uasset_read.parse_uasset import parse_uasset_with_linker

    def attempt(combo):
        _FIELDS["source_index"], _FIELDS["single_precision"], _FIELDS["uobject_wrapper"] = map(bool, combo)
        return parse_uasset_with_linker(path, force_full_parse=True, preload_all=True)

    try:
        best = attempt(_UE5_COMBOS[0])
        best_score = _pin_score(best)
        if best_score[0] < best_score[1] and best.summary.file_version_ue5 >= 1015:
            # engines newer than this tool knows may flip the FText rule; try the other setting
            _TEXT["override"] = not _TEXT["base_extra"]
            try:
                r = attempt(_UE5_COMBOS[0])
                s = _pin_score(r)
                if s[0] > best_score[0]:
                    best, best_score = r, s
                else:
                    _TEXT["override"] = None
            except Exception:
                _TEXT["override"] = None
        if best_score[0] < best_score[1]:
            combos = _UE4_COMBOS if best.summary.file_version_ue5 == 0 else _UE5_COMBOS[1:]
            for combo in combos:
                try:
                    r = attempt(combo)
                except Exception:
                    continue
                s = _pin_score(r)
                if s[0] > best_score[0]:
                    best, best_score = r, s
                if s[0] == s[1]:
                    break
    finally:
        _FIELDS.update(source_index=True, single_precision=True, uobject_wrapper=True)
        _TEXT["override"] = None
    return best, best_score


# =========================================================================== value helpers

def _short(name) -> str:
    if not name:
        return ""
    name = str(name)
    if name.endswith("_GEN_VARIABLE"):
        name = name[: -len("_GEN_VARIABLE")]
    return name


def _fmt_num(v):
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s not in ("-0", "") else "0"
    return str(v)


def fmt_value(v, depth=0) -> str:
    """Compact, human readable rendering of a decoded property value."""
    if depth > 3:
        return "…"
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return _fmt_num(v)
    if isinstance(v, str):
        return v if len(v) < 120 else v[:117] + "…"
    if isinstance(v, bytes):
        return f"<{len(v)} bytes>"
    if isinstance(v, list):
        items = [fmt_value(x, depth + 1) for x in v[:8]]
        more = f", …(+{len(v) - 8})" if len(v) > 8 else ""
        return "[" + ", ".join(items) + more + "]"
    if isinstance(v, dict):
        if "object_name" in v:
            return _short(v.get("object_name"))
        if "value_name" in v:
            return str(v["value_name"]).split("::")[-1]
        if "fields" in v and isinstance(v["fields"], dict):
            return _fmt_fields(v.get("struct_type", ""), v["fields"], depth)
        if v.get("kind") == "binary_or_native_property":
            return f"<{v.get('struct_type') or v.get('type')}>"
        return "{" + ", ".join(f"{k}={fmt_value(x, depth + 1)}" for k, x in list(v.items())[:6]) + "}"
    cls = type(v).__name__
    if cls == "TextValue":
        return '"' + (getattr(v, "source_string", "") or "") + '"'
    if cls == "VectorValue":
        return f"({_fmt_num(v.x)}, {_fmt_num(v.y)}, {_fmt_num(v.z)})"
    if cls == "RotatorValue":
        return f"(P={_fmt_num(v.pitch)}, Y={_fmt_num(v.yaw)}, R={_fmt_num(v.roll)})"
    if cls == "StructValue":
        return _fmt_fields(getattr(v, "struct_type", ""), getattr(v, "fields", {}) or {}, depth)
    if hasattr(v, "object_name"):
        return _short(v.object_name)
    s = str(v)
    return s if len(s) < 100 else s[:97] + "…"


def _fmt_fields(struct_type, fields, depth):
    if not fields:
        return f"{struct_type}{{}}" if struct_type and struct_type != "UnknownStruct" else "<opaque>"
    inner = ", ".join(f"{k}={fmt_value(x, depth + 1)}" for k, x in list(fields.items())[:8])
    return f"{struct_type}{{{inner}}}" if struct_type and struct_type != "UnknownStruct" else "{" + inner + "}"


def _fields(v) -> dict:
    f = getattr(v, "fields", None)
    if f is None and isinstance(v, dict):
        f = v.get("fields")
    return f or {}


class Ctx:
    """Per-package helpers: property lookup, package index resolution, names."""

    def __init__(self, result):
        from uasset_read.serializers.object_resources import PackageIndex
        self.r = result
        self.PackageIndex = PackageIndex
        self.linker = result.linker
        self.name_map = list(result.name_map or [])
        self._props = {}
        self._by_name = {}
        for o in result.all_objects:
            if getattr(o, "is_export", False):
                self._by_name.setdefault(o.object_name, []).append(o)

    def obj(self, pkg_index: int):
        if not pkg_index or not isinstance(pkg_index, int):
            return None
        try:
            return self.linker.resolve_package_index(self.PackageIndex(int(pkg_index)))
        except Exception:
            return None

    def obj_name(self, ref) -> str:
        if ref is None:
            return ""
        if isinstance(ref, int):
            o = self.obj(ref)
            return _short(o.object_name) if o is not None else ""
        if isinstance(ref, dict):
            return _short(ref.get("object_name", ""))
        return _short(getattr(ref, "object_name", "") or "")

    def class_of(self, o) -> str:
        oc = getattr(o, "object_class", None)
        return getattr(oc, "object_name", oc) or ""

    def full_name(self, o) -> str:
        try:
            return o.get_full_name()
        except Exception:
            return ""

    def props(self, pkg_index_or_obj) -> dict:
        o = self.obj(pkg_index_or_obj) if isinstance(pkg_index_or_obj, int) else pkg_index_or_obj
        if o is None:
            return {}
        key = id(o)
        if key not in self._props:
            d = {}
            try:
                o.ensure_preloaded()
                for pv in o.serialized_properties or []:
                    if pv.name not in d:
                        d[pv.name] = pv.value
            except Exception:
                pass
            self._props[key] = d
        return self._props[key]

    def export_by_ref(self, ref, cls: str | None = None):
        """Resolve a decoded object reference (dict with full_name / object_name, or int)."""
        if isinstance(ref, int):
            return self.obj(ref)
        if not isinstance(ref, dict):
            return None
        cands = self._by_name.get(ref.get("object_name", ""), [])
        fn = ref.get("full_name")
        if fn:
            for o in cands:
                if self.full_name(o) == fn:
                    return o
        for o in cands:
            if cls is None or self.class_of(o) == cls:
                return o
        return None

    def export_by_name(self, name: str, cls: str | None = None):
        for o in self._by_name.get(name, []):
            if cls is None or self.class_of(o) == cls:
                return o
        return None

    def fname(self, idx: int, number: int) -> str:
        if 0 <= idx < len(self.name_map):
            n = self.name_map[idx]
            return f"{n}_{number - 1}" if number > 0 else n
        return "?"


# =========================================================================== pin types

_CAT_NAMES = {
    "bool": "bool", "int": "int", "int64": "int64", "real": "float", "float": "float", "double": "double",
    "name": "Name", "string": "String", "text": "Text", "byte": "byte", "exec": "exec",
    "wildcard": "wildcard", "delegate": "Delegate", "mcdelegate": "MulticastDelegate",
}


def _type_str(category, subcat, subobj_name, container=0, value_type=None):
    category = category or ""
    sub = subobj_name or ""
    if category == "object":
        base = f"{sub}*" if sub else "Object*"
    elif category == "class":
        base = f"Class<{sub}>" if sub else "Class"
    elif category == "softobject":
        base = f"SoftObject<{sub}>"
    elif category == "softclass":
        base = f"SoftClass<{sub}>"
    elif category == "interface":
        base = f"Interface<{sub}>"
    elif category in ("struct", "byte", "enum") and sub:
        base = sub
    elif category == "real":
        base = subcat if subcat in ("float", "double") else "float"
    else:
        base = _CAT_NAMES.get(category, category or "?")
    if container == 1:
        return f"Array<{base}>"
    if container == 2:
        return f"Set<{base}>"
    if container == 3:
        return f"Map<{base}, {value_type or '?'}>"
    return base


def pin_type_str(pin) -> str:
    pt = pin.pin_type
    if pt is None:
        return "?"
    return _type_str(pt.pin_category, pt.pin_subcategory, pt.pin_subcategory_object_name, pt.container_type or 0)


def _decode_var_type(ctx: Ctx, raw: bytes) -> str:
    """Decode an FEdGraphPinType blob (BPVariableDescription.VarType)."""
    try:
        ci, cn, si, sn, obj = struct.unpack_from("<iiiii", raw, 0)
        container = raw[20]
        cat, subcat = ctx.fname(ci, cn), ctx.fname(si, sn)
        subobj = ctx.obj_name(obj) if obj else ""
        vtype = None
        if container == 3 and len(raw) >= 41:
            vci, vcn, vsi, vsn, vobj = struct.unpack_from("<iiiii", raw, 21)
            vtype = _type_str(ctx.fname(vci, vcn), ctx.fname(vsi, vsn), ctx.obj_name(vobj) if vobj else "")
        return _type_str(cat, subcat, subobj, container, vtype)
    except Exception:
        return "?"


# =========================================================================== graph rendering

EXEC = "exec"
_ENTRY_CLASSES = {
    "K2Node_Event", "K2Node_CustomEvent", "K2Node_ComponentBoundEvent", "K2Node_ActorBoundEvent",
    "K2Node_FunctionEntry", "K2Node_InputAction", "K2Node_InputKey", "K2Node_InputAxisEvent",
    "K2Node_InputAxisKeyEvent", "K2Node_InputTouch", "K2Node_EnhancedInputAction",
    "K2Node_InputDebugKey", "K2Node_GeneratedBoundEvent", "K2Node_Tunnel",
}
_CALL_CLASSES = {"K2Node_CallFunction", "K2Node_CommutativeAssociativeBinaryOperator", "K2Node_PromotableOperator",
                 "K2Node_CallArrayFunction", "K2Node_CallMaterialParameterCollectionFunction",
                 "K2Node_CallParentFunction", "K2Node_Message", "K2Node_CallFunctionOnMember"}
_INFIX = [
    ("EqualEqual_", "=="), ("NotEqual_", "!="), ("GreaterEqual_", ">="), ("LessEqual_", "<="),
    ("Greater_", ">"), ("Less_", "<"), ("Add_", "+"), ("Subtract_", "-"), ("Multiply_", "*"),
    ("Divide_", "/"), ("Percent_", "%"), ("BooleanAND", "&&"), ("BooleanOR", "||"), ("BooleanXOR", "^"),
    ("And_", "&"), ("Or_", "|"),
]
_PROMOTABLE = {"Add": "+", "Subtract": "-", "Multiply": "*", "Divide": "/", "Greater": ">", "Less": "<",
               "GreaterEqual": ">=", "LessEqual": "<=", "EqualEqual": "==", "NotEqual": "!="}
_EXEC_LABELS = {
    "K2Node_IfThenElse": {"then": "true", "else": "false"},
    "K2Node_DynamicCast": {"then": "cast ok", "CastFailed": "cast failed"},
    "K2Node_ClassDynamicCast": {"then": "cast ok", "CastFailed": "cast failed"},
}
_SKIP_ARGS = ("self", "WorldContextObject", "__WorldContext", "LatentInfo")
_GHOST_TEXT = "This node is disabled"


def _is_exec(pin) -> bool:
    return pin.pin_type is not None and pin.pin_type.pin_category == EXEC


class GraphRenderer:
    def __init__(self, ctx: Ctx, graph, name: str):
        self.ctx = ctx
        self.g = graph
        self.name = name
        self.nodes = list(graph.nodes)
        # Pin GUIDs are only unique within a node, so pins are keyed by (owning node, guid).
        self.pin_owner = {}
        self.pin_by_guid = {}
        self.sub_pins = {}
        for n in self.nodes:
            for p in n.pins:
                self.pin_owner[(n._export_object_name, p.pin_id)] = (n, p)
                self.pin_by_guid.setdefault(p.pin_id, []).append((n, p))
        for n in self.nodes:
            for p in n.pins:
                if p.parent_pin and p.parent_pin.get("pin_guid"):
                    key = (p.parent_pin.get("owning_node") or n._export_object_name, p.parent_pin["pin_guid"])
                    self.sub_pins.setdefault(key, []).append(p)
        self.ids = {}
        self.exec_in = {}
        self.used_outputs = set()
        for n in self.nodes:
            for p in n.pins:
                if p.direction != 1:
                    continue
                for link in p.linked_to_raw:
                    tgt = self.resolve(link)
                    if not tgt:
                        continue
                    if _is_exec(p):
                        self.exec_in[id(tgt[0])] = self.exec_in.get(id(tgt[0]), 0) + 1
                    else:
                        self.used_outputs.add(id(p))
        self.visited = set()
        self.current_box = None
        self.comment_boxes = []
        for n in self.nodes:
            if n.class_name == "EdGraphNode_Comment":
                nd = n.node_data if isinstance(n.node_data, dict) else {}
                text = (n.node_comment or self.props(n).get("NodeComment") or "").strip()
                w, h = nd.get("node_width") or 0, nd.get("node_height") or 0
                if text:
                    self.comment_boxes.append((n.node_pos_x, n.node_pos_y, w, h, text))
        self.expr_stack = set()
        self.var_refs = {}      # self-context variable name -> type (for UE4 fallback)
        self.unused_events = []
        for n in self.nodes:
            if n.class_name in ("K2Node_VariableGet", "K2Node_VariableSet"):
                if not self._target_linked(n):
                    vn = self.var_name(n)
                    for p in n.pins:
                        if p.pin_name == vn:
                            self.var_refs.setdefault(vn, pin_type_str(p))

    # ---- helpers
    def resolve(self, ref, default_node=None):
        """(node, pin) for a serialized pin reference {owning_node, pin_guid}."""
        if not ref:
            return None
        guid = ref.get("pin_guid")
        owner = ref.get("owning_node") or (default_node._export_object_name if default_node is not None else None)
        hit = self.pin_owner.get((owner, guid))
        if hit:
            return hit
        cands = self.pin_by_guid.get(guid) or []
        return cands[0] if len(cands) == 1 else None

    def props(self, n):
        idx = getattr(n, "_export_index", None)
        return self.ctx.props(idx) if idx else {}

    def note_of(self, n) -> str:
        return (n.node_comment or self.props(n).get("NodeComment") or "").strip()

    def is_disabled(self, n) -> bool:
        if self.note_of(n).startswith(_GHOST_TEXT):
            return True
        es = self.props(n).get("EnabledState")
        return isinstance(es, dict) and "Disabled" in str(es.get("value_name", ""))

    def nid(self, n) -> str:
        if id(n) not in self.ids:
            self.ids[id(n)] = f"#{len(self.ids) + 1}"
        return self.ids[id(n)]

    def _target_linked(self, n) -> bool:
        return any(p.direction == 0 and p.pin_name == "self" and p.linked_to_raw for p in n.pins)

    def source_of(self, pin):
        """(node, pin) feeding an input pin, following reroute knots."""
        for link in pin.linked_to_raw:
            src = self.resolve(link)
            if src:
                sn, sp = src
                if sn.class_name == "K2Node_Knot":
                    ins = [p for p in sn.pins if p.direction == 0]
                    if ins and ins[0].linked_to_raw:
                        return self.source_of(ins[0])
                return src
        return None

    def exec_target(self, pin):
        for link in pin.linked_to_raw:
            tgt = self.resolve(link)
            if tgt:
                tn, _ = tgt
                if tn.class_name == "K2Node_Knot":
                    outs = [p for p in tn.pins if p.direction == 1]
                    return self.exec_target(outs[0]) if outs else None
                return tn
        return None

    def comment_for(self, n):
        best = None
        for (x, y, w, h, text) in self.comment_boxes:
            if x <= n.node_pos_x <= x + w and y <= n.node_pos_y <= y + h:
                if best is None or w * h < best[0]:
                    best = (w * h, text)
        return best[1] if best else None

    def member_ref(self, n, key="FunctionReference", data_key="function_reference"):
        nd = n.node_data if isinstance(n.node_data, dict) else {}
        fr = nd.get(data_key)
        if fr is not None and getattr(fr, "member_name", None):
            name, parent, self_ctx = fr.member_name, fr.member_parent, fr.b_self_context
        else:
            f = _fields(self.props(n).get(key))
            name = f.get("MemberName")
            mp = f.get("MemberParent")
            parent = self.ctx.obj_name(mp) if isinstance(mp, int) else mp
            self_ctx = bool(f.get("bSelfContext"))
        if isinstance(parent, str) and parent.startswith("/"):
            parent = parent.rsplit(".", 1)[-1]
        return name or "?", parent, self_ctx

    def var_name(self, n):
        f = _fields(self.props(n).get("VariableReference"))
        if f.get("MemberName"):
            return f["MemberName"]
        for p in n.pins:
            if p.pin_name not in ("self", "execute", "then", "Output_Get") and not _is_exec(p):
                return p.pin_name
        return "?"

    # ---- values
    def default_of(self, pin):
        if pin.default_object_ref is not None:
            return _short(getattr(pin.default_object_ref, "object_name", ""))
        if pin.default_text_value:
            return '"' + str(pin.default_text_value).replace("\r", "").replace("\n", "\\n") + '"'
        dv = pin.default_value
        if dv is None or dv == "":
            return None
        cat = pin.pin_type.pin_category if pin.pin_type else ""
        dv = dv.replace("\r", "").replace("\n", "\\n")
        if cat in ("string", "name"):
            return f'"{dv}"'
        if cat in ("real", "float", "double"):
            try:
                return _fmt_num(float(dv))
            except ValueError:
                return dv
        return dv

    def _is_unchanged_default(self, p) -> bool:
        if p.default_object_ref is not None or p.default_text_value:
            return False
        return (p.default_value or "") == (p.auto_default_value or "")

    def pin_value(self, n, p):
        """Expression for an input pin, or None when it is unconnected and left at its default."""
        subs = self.sub_pins.get((n._export_object_name, p.pin_id))
        if subs:
            parts = []
            for sp in subs:
                v = self.pin_value(n, sp)
                if v is not None:
                    field = sp.pin_name[len(p.pin_name) + 1:] if sp.pin_name.startswith(p.pin_name + "_") else sp.pin_name
                    parts.append(f"{field}={v}")
            return "{" + ", ".join(parts) + "}" if parts else None
        src = self.source_of(p)
        if src:
            return self.expr_from(*src)
        if p.hidden or self._is_unchanged_default(p):
            return None
        return self.default_of(p)

    def visible_inputs(self, n, skip=_SKIP_ARGS):
        return [p for p in n.pins
                if p.direction == 0 and not _is_exec(p) and p.pin_name not in skip and not p.parent_pin
                and p.pin_type is not None and (not p.hidden or p.linked_to_raw or self.sub_pins.get((n._export_object_name, p.pin_id)))]

    def arg_list(self, n, skip=_SKIP_ARGS):
        args = []
        for p in self.visible_inputs(n, skip):
            v = self.pin_value(n, p)
            if v is not None:
                args.append(f"{p.pin_name}={v}")
        return args

    def input_expr(self, n, pin_name):
        for p in n.pins:
            if p.direction == 0 and p.pin_name == pin_name:
                v = self.pin_value(n, p)
                if v is not None:
                    return v
                d = self.default_of(p)
                if d is not None:
                    return d
                cat = p.pin_type.pin_category if p.pin_type else ""
                return {"int": "0", "int64": "0", "real": "0", "float": "0", "double": "0", "byte": "0",
                        "bool": "false", "object": "None", "class": "None", "softobject": "None",
                        "softclass": "None", "interface": "None", "string": '""', "name": "None",
                        "text": '""'}.get(cat, "∅")
        return "∅"

    def target_prefix(self, n) -> str:
        for p in n.pins:
            if p.direction == 0 and p.pin_name == "self":
                src = self.source_of(p)
                return self.expr_from(*src) + "." if src else ""
        return ""

    def expr_from(self, n, out_pin) -> str:
        """Expression producing the value of `out_pin` on node `n`."""
        parent = self.resolve(out_pin.parent_pin, n) if out_pin.parent_pin else None
        if parent:
            pn, pp = parent
            field = out_pin.pin_name[len(pp.pin_name) + 1:] if out_pin.pin_name.startswith(pp.pin_name + "_") else out_pin.pin_name
            return f"{self.expr_from(pn, pp)}.{field}"
        cls = n.class_name
        pname = out_pin.pin_name
        if cls in _ENTRY_CLASSES:
            if out_pin.pin_type is not None and out_pin.pin_type.pin_category == "delegate":
                h = self.entry_header(n)
                return h.split("(")[0].split(" ", 2)[-1]  # bound event name
            return pname
        if cls == "K2Node_VariableSet":
            return self.target_prefix(n) + self.var_name(n)
        if cls in ("K2Node_DynamicCast", "K2Node_ClassDynamicCast"):
            src = self.input_expr(n, "Object" if cls == "K2Node_DynamicCast" else "Class")
            if pname == "bSuccess":
                return f"({src} is {self.cast_type(n)})"
            return f"({src} as {self.cast_type(n)})"
        if any(_is_exec(p) for p in n.pins):
            ref = self.nid(n)
            return ref if pname == "ReturnValue" else f"{ref}.{pname}"
        key = (id(n), pname)
        if key in self.expr_stack or len(self.expr_stack) > 14:
            return "…"
        self.expr_stack.add(key)
        try:
            return self.pure_expr(n, out_pin)
        finally:
            self.expr_stack.discard(key)

    def cast_type(self, n) -> str:
        t = self.props(n).get("TargetType")
        name = self.ctx.obj_name(t) if t is not None else ""
        if not name:
            for p in n.pins:
                if p.direction == 1 and p.pin_name.startswith("As"):
                    return p.pin_name[2:].replace(" ", "")
        return name or "?"

    def pure_expr(self, n, out_pin) -> str:
        cls = n.class_name
        pname = out_pin.pin_name
        if cls == "K2Node_VariableGet":
            return self.target_prefix(n) + self.var_name(n)
        if cls == "K2Node_Self":
            return "self"
        if cls in _CALL_CLASSES:
            fn, parent, _ = self.member_ref(n)
            op = None
            if cls == "K2Node_PromotableOperator":
                op = _PROMOTABLE.get(str(self.props(n).get("OperationName") or ""))
            if op is None:
                for prefix, sym in _INFIX:
                    if fn.startswith(prefix):
                        op = sym
                        break
            ins = self.visible_inputs(n)
            if op and len(ins) >= 2:
                e = "(" + f" {op} ".join(self.input_expr(n, p.pin_name) for p in ins) + ")"
            elif fn == "Not_PreBool" and ins:
                e = "!" + self.input_expr(n, ins[0].pin_name)
            elif fn.startswith("Conv_") and len(ins) == 1:
                e = f"{fn[5:]}({self.input_expr(n, ins[0].pin_name)})"
            else:
                e = f"{self.target_prefix(n)}{fn}({', '.join(self.arg_list(n))})"
            return e if pname == "ReturnValue" else f"{e}.{pname}"
        if cls == "K2Node_BreakStruct":
            ins = [p for p in n.pins if p.direction == 0]
            base = self.input_expr(n, ins[0].pin_name) if ins else "?"
            return f"{base}.{pname}"
        if cls == "K2Node_MakeStruct":
            st = self.ctx.obj_name(self.props(n).get("StructType")) or "Struct"
            return f"{st}{{{', '.join(self.arg_list(n))}}}"
        if cls == "K2Node_MakeArray":
            return "[" + ", ".join(self.input_expr(n, p.pin_name) for p in n.pins if p.direction == 0) + "]"
        if cls == "K2Node_Select":
            opts = [p for p in n.pins if p.direction == 0 and p.pin_name != "Index"]
            return f"select({self.input_expr(n, 'Index')}: " + ", ".join(self.input_expr(n, p.pin_name) for p in opts) + ")"
        if cls.startswith("K2Node_GetSubsystem"):
            return f"GetSubsystem<{self.ctx.obj_name(self.props(n).get('CustomClass'))}>()"
        if cls == "K2Node_Literal":
            return self.ctx.obj_name(self.props(n).get("ObjectRef")) or "literal"
        if cls == "K2Node_EnumLiteral":
            return self.input_expr(n, "Enum")
        if cls == "K2Node_GetArrayItem":
            ins = [p for p in n.pins if p.direction == 0]
            if len(ins) >= 2:
                return f"{self.input_expr(n, ins[0].pin_name)}[{self.input_expr(n, ins[1].pin_name)}]"
        if cls == "K2Node_MacroInstance":
            return f"{self.macro_name(n)}({', '.join(self.arg_list(n))}).{pname}"
        if cls == "K2Node_CreateDelegate":
            return f"Delegate({self.props(n).get('SelectedFunctionName') or '?'})"
        name = cls.replace("K2Node_", "").replace("AnimGraphNode_", "")
        e = f"{name}({', '.join(self.arg_list(n))})"
        return e if pname in ("ReturnValue", "Output", "Result") else f"{e}.{pname}"

    def macro_name(self, n) -> str:
        mg = _fields(self.props(n).get("MacroGraphReference")).get("MacroGraph")
        return (self.ctx.obj_name(mg) if mg else "") or "Macro"

    # ---- statements
    def params_sig(self, n) -> str:
        outs = [p for p in n.pins if p.direction == 1 and not _is_exec(p)
                and p.pin_name != "OutputDelegate" and not p.parent_pin]
        return ", ".join(f"{p.pin_name}: {pin_type_str(p)}" for p in outs)

    def entry_header(self, n) -> str:
        cls = n.class_name
        p = self.props(n)
        nd = n.node_data if isinstance(n.node_data, dict) else {}
        if cls == "K2Node_FunctionEntry":
            return f"function {self.name}({self.params_sig(n)})"
        if cls == "K2Node_CustomEvent":
            name = p.get("CustomFunctionName") or nd.get("custom_function_name") or "?"
            flags = []
            ff = p.get("FunctionFlags") or 0
            if isinstance(ff, int):
                if ff & 0x00200000:
                    flags.append("RunOnServer")
                if ff & 0x01000000:
                    flags.append("RunOnOwningClient")
                if ff & 0x00004000:
                    flags.append("Multicast")
                if ff & 0x00000080:
                    flags.append("Reliable")
            tag = f"  [{' '.join(flags)}]" if flags else ""
            return f"custom event {name}({self.params_sig(n)}){tag}"
        if cls == "K2Node_ComponentBoundEvent":
            return f"on {p.get('ComponentPropertyName') or '?'}.{p.get('DelegatePropertyName') or '?'}({self.params_sig(n)})"
        if cls == "K2Node_ActorBoundEvent":
            actor = self.ctx.obj_name(p.get("EventOwner")) or "?"
            return f"on {actor}.{p.get('DelegatePropertyName') or '?'}({self.params_sig(n)})"
        if cls == "K2Node_EnhancedInputAction":
            ia = self.ctx.obj_name(p.get("InputAction")) or nd.get("input_action_short_name") or "?"
            return f"input {ia}"
        if cls == "K2Node_InputAction":
            return f"input action {p.get('InputActionName') or '?'}"
        if cls in ("K2Node_InputKey", "K2Node_InputDebugKey"):
            key = _fields(p.get("InputKey")).get("KeyName") or fmt_value(p.get("InputKey"))
            return f"input key {key}"
        if cls == "K2Node_InputAxisEvent":
            return f"input axis {p.get('InputAxisName') or '?'}"
        if cls == "K2Node_Event":
            name, parent, _ = self.member_ref(n, "EventReference", "event_reference")
            disp = name[7:] if name.startswith("Receive") and len(name) > 7 else name
            src = f"  // override {parent}::{name}" if parent else ""
            return f"event {disp}({self.params_sig(n)}){src}"
        if cls == "K2Node_Tunnel":
            return f"macro {self.name}({self.params_sig(n)})"
        return cls.replace("K2Node_", "")

    def statement(self, n, entered_via=None) -> str:
        cls = n.class_name
        p = self.props(n)
        used = any(q.direction == 1 and not _is_exec(q) and id(q) in self.used_outputs for q in n.pins)
        prefix = f"{self.nid(n)} = " if used else ""
        dis = "   // (disabled node)" if self.is_disabled(n) else ""
        if cls in _CALL_CLASSES:
            fn, parent, _ = self.member_ref(n)
            args = ", ".join(self.arg_list(n))
            if cls == "K2Node_CallParentFunction":
                return f"{prefix}super.{fn}({args}){dis}"
            tail = "   // interface message" if cls == "K2Node_Message" else ""
            return f"{prefix}{self.target_prefix(n)}{fn}({args}){tail}{dis}"
        if cls == "K2Node_VariableSet":
            var = self.var_name(n)
            return f"{self.target_prefix(n)}{var} = {self.input_expr(n, var)}{dis}"
        if cls == "K2Node_VariableSetRef":
            return f"{self.input_expr(n, 'Target')} = {self.input_expr(n, 'Value')}"
        if cls == "K2Node_IfThenElse":
            return f"if {self.input_expr(n, 'Condition')}"
        if cls in ("K2Node_DynamicCast", "K2Node_ClassDynamicCast"):
            src = self.input_expr(n, "Object" if cls == "K2Node_DynamicCast" else "Class")
            return f"cast {src} to {self.cast_type(n)}"
        if cls == "K2Node_ExecutionSequence":
            return "sequence"
        if cls.startswith("K2Node_Switch"):
            en = self.ctx.obj_name(p.get("Enum"))
            return f"switch {self.input_expr(n, 'Selection')}" + (f"  ({en})" if en else "")
        if cls == "K2Node_MacroInstance":
            return f"{prefix}{self.macro_name(n)}({', '.join(self.arg_list(n))})"
        if cls in ("K2Node_SpawnActorFromClass", "K2Node_CreateWidget", "K2Node_ConstructObjectFromClass",
                   "K2Node_GenericCreateObject"):
            verb = {"K2Node_SpawnActorFromClass": "SpawnActor", "K2Node_CreateWidget": "CreateWidget"}.get(cls, "NewObject")
            rest = ", ".join(self.arg_list(n, skip=_SKIP_ARGS + ("Class",)))
            return f"{prefix}{verb}<{self.input_expr(n, 'Class')}>({rest})"
        if cls == "K2Node_Timeline":
            return f"timeline {p.get('TimelineName') or '?'}.{entered_via or 'Play'}()"
        if cls == "K2Node_CallDelegate":
            dname = _fields(p.get("DelegateReference")).get("MemberName", "?")
            return f"broadcast {self.target_prefix(n)}{dname}({', '.join(self.arg_list(n))})"
        if cls in ("K2Node_AddDelegate", "K2Node_AssignDelegate", "K2Node_RemoveDelegate", "K2Node_ClearDelegate"):
            dname = _fields(p.get("DelegateReference")).get("MemberName", "?")
            if cls == "K2Node_ClearDelegate":
                return f"{self.target_prefix(n)}{dname}.Clear()"
            op = "-=" if cls == "K2Node_RemoveDelegate" else "+="
            return f"{self.target_prefix(n)}{dname} {op} {self.input_expr(n, 'Delegate')}"
        if cls == "K2Node_AsyncAction" or cls.startswith(("K2Node_LatentAbilityCall", "K2Node_BaseAsyncTask", "K2Node_LatentGameplayTaskCall")):
            fn = p.get("ProxyFactoryFunctionName") or cls.replace("K2Node_", "")
            return f"{prefix}async {fn}({', '.join(self.arg_list(n))})"
        if cls == "K2Node_FunctionResult":
            args = ", ".join(self.arg_list(n))
            return f"return ({args})" if args else "return"
        if cls == "K2Node_Tunnel":
            return f"exit → {entered_via}" if entered_via else "exit"
        return f"{prefix}{cls.replace('K2Node_', '')}({', '.join(self.arg_list(n))}){dis}"

    # ---- exec traversal
    def _entered_pin(self, out_pin, target):
        for link in out_pin.linked_to_raw:
            tgt = self.resolve(link)
            if tgt and tgt[0] is target:
                return tgt[1].pin_name
        return None

    def emit_chain(self, start, lines, indent, entered_via=None):
        n, via, guard = start, entered_via, 0
        while n is not None and guard < 5000:
            guard += 1
            pad = "  " * indent
            if id(n) in self.visited:
                lines.append(f"{pad}→ goto {self.nid(n)}")
                return
            self.visited.add(id(n))
            box = self.comment_for(n)
            if box and box != self.current_box:
                lines.append(f"{pad}// ── {box.splitlines()[0][:140]} ──")
                self.current_box = box
            note = self.note_of(n)
            if note and not note.startswith(_GHOST_TEXT):
                for ln in note.splitlines()[:3]:
                    lines.append(f"{pad}// {ln[:160]}")
            label = f"[{self.nid(n)}] " if self.exec_in.get(id(n), 0) > 1 else ""
            lines.append(pad + label + self.statement(n, via))
            outs = [p for p in n.pins if p.direction == 1 and _is_exec(p)]
            linked = [(p, self.exec_target(p)) for p in outs]
            linked = [(p, t) for p, t in linked if t is not None]
            if not linked:
                return
            if len(outs) == 1:
                p, t = linked[0]
                n, via = t, self._entered_pin(p, t)
                continue
            names = _EXEC_LABELS.get(n.class_name, {})
            for p, t in linked:
                lines.append(f"{pad}  [{names.get(p.pin_name, p.pin_name)}]:")
                self.emit_chain(t, lines, indent + 2, self._entered_pin(p, t))
            return

    def render_exec(self) -> list[str]:
        lines: list[str] = []
        entries = [n for n in self.nodes if n.class_name in _ENTRY_CLASSES
                   and not (n.class_name == "K2Node_Tunnel" and any(p.direction == 0 and _is_exec(p) for p in n.pins))]
        for e in entries:
            self.visited.add(id(e))
            outs = [p for p in e.pins if p.direction == 1 and _is_exec(p)]
            linked = [(p, self.exec_target(p)) for p in outs]
            linked = [(p, t) for p, t in linked if t is not None]
            if not linked and e.class_name != "K2Node_FunctionEntry" and (self.is_disabled(e) or e.class_name == "K2Node_Event"):
                self.unused_events.append(self.entry_header(e).split("(")[0].replace("event ", ""))
                continue
            if lines:
                lines.append("")
            self.current_box = None
            box = self.comment_for(e)
            if box:
                lines.append(f"// ── {box.splitlines()[0][:140]} ──")
                self.current_box = box
            note = self.note_of(e)
            if note and not note.startswith(_GHOST_TEXT):
                for ln in note.splitlines()[:3]:
                    lines.append(f"// {ln[:160]}")
            lines.append(self.entry_header(e))
            if not linked:
                lines.append("  (no logic connected)")
            elif len(linked) == 1 and len(outs) == 1:
                self.emit_chain(linked[0][1], lines, 1, self._entered_pin(*linked[0]))
            else:
                for p, t in linked:
                    lines.append(f"  [{p.pin_name}]:")
                    self.emit_chain(t, lines, 2, self._entered_pin(p, t))
        orphans = []
        for n in self.nodes:
            if id(n) in self.visited or n.class_name in ("K2Node_Knot", "EdGraphNode_Comment"):
                continue
            ex_in = [p for p in n.pins if p.direction == 0 and _is_exec(p)]
            if ex_in and not any(p.linked_to_raw for p in ex_in):
                orphans.append(n)
        if orphans:
            lines.append("")
            lines.append("// ⚠ disconnected execution chains (never run — nothing drives their exec input):")
            for n in orphans:
                self.current_box = None
                self.emit_chain(n, lines, 1)
        if self.unused_events:
            lines.append("")
            lines.append("// unused (empty) events: " + ", ".join(self.unused_events))
        return lines

    # ---- non-exec graphs (AnimGraph, transition rules, ...)
    def render_dataflow(self) -> list[str]:
        lines: list[str] = []
        for n in self.nodes:
            if n.class_name in ("EdGraphNode_Comment", "K2Node_Knot"):
                continue
            outs = [p for p in n.pins if p.direction == 1]
            if n.pins and not any(p.linked_to_raw for p in outs):
                lines.extend(self.tree(n, 0, set()))
        return lines

    def anim_label(self, n) -> str:
        cls = n.class_name.replace("AnimGraphNode_", "").replace("K2Node_", "")
        p = self.props(n)
        extra = []
        for k, v in _fields(p.get("Node")).items():
            if isinstance(v, int) and not isinstance(v, bool) and k in (
                    "Sequence", "BlendSpace", "Montage", "PoseAsset", "Asset", "ControlRigClass", "Class"):
                nm = self.ctx.obj_name(v)
                if nm:
                    extra.append(f"{k}={nm}")
            elif isinstance(v, (bool, float)) or (isinstance(v, str) and v and v != "None"):
                extra.append(f"{k}={fmt_value(v)}")
        for key in ("EditorStateMachineGraph", "BoundGraph"):
            if p.get(key) is not None:
                extra.append(f"graph='{self.ctx.obj_name(p.get(key))}'")
        return f"{cls}({', '.join(extra[:6])})" if extra else cls

    def tree(self, n, depth, seen) -> list[str]:
        pad = "  " * depth
        if id(n) in seen or depth > 30:
            return [pad + "…"]
        seen = seen | {id(n)}
        out = [pad + ("← " if depth else "") + self.anim_label(n)]
        for p in n.pins:
            if p.direction != 0 or p.parent_pin:
                continue
            src = self.source_of(p)
            if src:
                sn, sp = src
                is_pose = bool(sp.pin_type and "Pose" in (sp.pin_type.pin_subcategory_object_name or ""))
                if is_pose:
                    out.append(f"{pad}  .{p.pin_name}:")
                    out.extend(self.tree(sn, depth + 2, seen))
                else:
                    out.append(f"{pad}  .{p.pin_name} = {self.expr_from(sn, sp)}")
            else:
                v = self.pin_value(n, p)
                if v is not None:
                    out.append(f"{pad}  .{p.pin_name} = {v}")
        return out

    def rule_expr(self) -> str | None:
        """For a transition-rule graph: the expression feeding bCanEnterTransition."""
        for n in self.nodes:
            if n.class_name == "AnimGraphNode_TransitionResult":
                v = self.input_expr(n, "bCanEnterTransition")
                return v
        return None

    def state_machine(self):
        """Returns (states, entry_state, transitions[(src, dst, bound_graph_ref)])."""
        states = {}
        for n in self.nodes:
            if n.class_name in ("AnimStateNode", "AnimStateConduitNode", "AnimStateAliasNode"):
                states[id(n)] = self.ctx.obj_name(self.props(n).get("BoundGraph")) or n.class_name
        entry = None
        trans = []
        for n in self.nodes:
            if n.class_name == "AnimStateEntryNode":
                for p in n.pins:
                    for link in p.linked_to_raw:
                        t = self.resolve(link)
                        if t:
                            entry = states.get(id(t[0]))
            if n.class_name == "AnimStateTransitionNode":
                src = dst = None
                for p in n.pins:
                    for link in p.linked_to_raw:
                        other = self.resolve(link)
                        if other:
                            if p.direction == 0:
                                src = other[0]
                            else:
                                dst = other[0]
                trans.append((states.get(id(src), "?"), states.get(id(dst), "?"), self.props(n).get("BoundGraph")))
        return list(states.values()), entry, trans

    def mode(self) -> str:
        classes = {n.class_name for n in self.nodes}
        if classes & {"AnimStateNode", "AnimStateTransitionNode", "AnimStateEntryNode"}:
            return "state machine"
        if any(_is_exec(p) for n in self.nodes for p in n.pins):
            return "exec"
        return "dataflow"


# =========================================================================== blueprint document

_BP_CLASSES = {
    "Blueprint": "Blueprint", "WidgetBlueprint": "Widget Blueprint", "AnimBlueprint": "Anim Blueprint",
    "EditorUtilityBlueprint": "Editor Utility Blueprint", "EditorUtilityWidgetBlueprint": "Editor Utility Widget",
    "GameplayAbilityBlueprint": "Gameplay Ability Blueprint", "ControlRigBlueprint": "Control Rig",
}
_CDO_SKIP = {"UberGraphFrame", "ActorLabel", "RootComponent", "InstanceComponents", "BlueprintCreatedComponents",
             "WidgetTree", "bHasScriptImplementedTick", "bHasScriptImplementedPaint", "TickPrediction",
             "TickPredictionReason", "AnimBlueprintExtension_PropertyAccess", "AnimBlueprintExtension_Base"}


def _find_blueprint_object(ctx: Ctx, asset_name: str):
    fallback = (None, "")
    for o in ctx.r.all_objects:
        if not getattr(o, "is_export", False):
            continue
        cls = ctx.class_of(o)
        if o.object_name == asset_name and (cls in _BP_CLASSES or cls.endswith("Blueprint")):
            return o, cls
        if cls.endswith("Blueprint") and fallback[0] is None:
            fallback = (o, cls)
    return fallback


def _components(ctx: Ctx, bp_props) -> list[str]:
    scs_obj = ctx.export_by_ref(bp_props.get("SimpleConstructionScript"))
    if scs_obj is None:
        return []
    transforms = {_short(c.get("name")): c.get("transforms") or {} for c in (ctx.r.components or [])}

    def node_lines(ref, depth):
        o = ctx.export_by_ref(ref)
        if o is None:
            return []
        p = ctx.props(o)
        name = p.get("InternalVariableName") or _short(o.object_name)
        cls = ctx.obj_name(p.get("ComponentClass")) or "?"
        tr = transforms.get(_short(str(name)), {})
        t = [f"{lab}={fmt_value(tr[k])}" for k, lab in
             (("relative_location", "loc"), ("relative_rotation", "rot"), ("relative_scale3d", "scale"))
             if tr.get(k) is not None]
        attach = p.get("ParentComponentOrVariableName")
        extra = f"  (attached to inherited {attach})" if attach and attach != "None" and depth == 0 else ""
        out = [f"{'  ' * depth}- {name} : {cls}" + (f"  {' '.join(t)}" if t else "") + extra]
        for ch in p.get("ChildNodes") or []:
            out.extend(node_lines(ch, depth + 1))
        return out

    lines = []
    for root in ctx.props(scs_obj).get("RootNodes") or []:
        lines.extend(node_lines(root, 0))
    return lines


def _variables(ctx: Ctx, bp_props, cdo_props):
    rows, names = [], set()
    for v in bp_props.get("NewVariables") or []:
        f = _fields(v)
        name = f.get("VarName")
        if not name:
            continue
        names.add(name)
        vt = f.get("VarType")
        tstr = _decode_var_type(ctx, vt.get("raw_data")) if isinstance(vt, dict) and vt.get("raw_data") else "?"
        flags = f.get("PropertyFlags") or 0
        tags = []
        if isinstance(flags, int):
            if flags & 0x1 and not flags & 0x10000:
                tags.append("InstanceEditable")
            if flags & 0x10:
                tags.append("ReadOnly")
            if flags & 0x20:
                tags.append("Replicated")
        rn = f.get("RepNotifyFunc")
        if rn and rn != "None":
            tags.append(f"RepNotify={rn}")
        cat = f.get("Category")
        cat_s = getattr(cat, "source_string", None) if cat is not None else None
        default = cdo_props.get(name)
        dflt = fmt_value(default) if default is not None else (f.get("DefaultValue") or "")
        rows.append(f"| {name} | {tstr} | {cat_s or ''} | {' '.join(tags)} | {str(dflt).replace('|', '/')} |")
    table = ["| Name | Type | Category | Flags | Default |", "|---|---|---|---|---|"] + rows if rows else []
    return table, names


def _widget_tree(ctx: Ctx, bp_props) -> list[str]:
    wt_obj = ctx.export_by_ref(bp_props.get("WidgetTree"), "WidgetTree")
    if wt_obj is None:
        return []

    def lines_for(o, depth, seen):
        if o is None or id(o) in seen or depth > 30:
            return []
        seen.add(id(o))
        p = ctx.props(o)
        info = [f"{k}={fmt_value(p[k])}" for k in ("Text", "ToolTipText") if p.get(k) is not None]
        if p.get("bIsVariable"):
            info.append("isVariable")
        out = [f"{'  ' * depth}- {o.object_name} : {ctx.class_of(o)}" + (f"  ({', '.join(info)})" if info else "")]
        for s in p.get("Slots") or []:
            so = ctx.export_by_ref(s)
            if so is not None:
                out.extend(lines_for(ctx.export_by_ref(ctx.props(so).get("Content")), depth + 1, seen))
        return out

    return lines_for(ctx.export_by_ref(ctx.props(wt_obj).get("RootWidget")), 0, set())


def _cdo_lines(cdo_props, var_names) -> list[str]:
    out = []
    for k, v in cdo_props.items():
        if k in _CDO_SKIP or k in var_names or k.startswith("AnimGraphNode_") or k.startswith("__"):
            continue
        if isinstance(v, dict) and v.get("type") == "export":
            continue  # default sub-object (component instance), not a tunable value
        s = fmt_value(v)
        if (s.startswith("<") and s.endswith(">")) or s.startswith("AnimNode_"):
            continue
        out.append(f"- {k} = {s}")
    return out[:40]


def _graph_key(ctx: Ctx, g) -> str:
    for n in g.nodes:
        o = ctx.obj(getattr(n, "_export_index", None))
        if o is not None and o.outer is not None:
            return ctx.full_name(o.outer)
    return f"?{g.graph_name}"


def read_blueprint(path: str, game_path: str) -> dict:
    """Parse one Blueprint asset and render it to Markdown."""
    ensure_uasset_read()
    logging.disable(logging.CRITICAL)
    _install_patches()
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    result, (ok_nodes, total_nodes) = _parse(path)
    ctx = Ctx(result)
    asset_name = Path(path).stem
    bp_obj, bp_cls = _find_blueprint_object(ctx, asset_name)
    bp_props = ctx.props(bp_obj) if bp_obj is not None else {}
    kind = _BP_CLASSES.get(bp_cls, bp_cls or "Blueprint")
    parent = ctx.obj_name(bp_props.get("ParentClass")) or (result.blueprint.parent_class if result.blueprint else "") or "?"
    parent = parent.rsplit(".", 1)[-1]
    interfaces = [nm for nm in (ctx.obj_name(_fields(it).get("Interface")) for it in bp_props.get("ImplementedInterfaces") or []) if nm]
    cdo = ctx.export_by_name(f"Default__{asset_name}_C")
    cdo_props = ctx.props(cdo) if cdo is not None else {}
    ev = getattr(result.summary, "saved_by_engine_version", None)
    saved = f"{ev.major}.{ev.minor}.{ev.patch}" if ev and getattr(ev, "major", 0) else "?"

    # ---- collect unique graphs (the parser lists nested graphs both nested and top-level)
    graphs = {}
    order = []
    for g, _ in _walk_graphs(result.graphs):
        if not g.nodes:
            continue
        key = _graph_key(ctx, g)
        if key not in graphs:
            graphs[key] = g
            order.append(key)
    role = {}
    for prop, label in (("UbergraphPages", "event graph"), ("FunctionGraphs", "function"), ("MacroGraphs", "macro"),
                        ("DelegateSignatureGraphs", "dispatcher")):
        for ref in bp_props.get(prop) or []:
            o = ctx.export_by_ref(ref)
            if o is not None:
                role[ctx.full_name(o)] = label
    for it in bp_props.get("ImplementedInterfaces") or []:
        for ref in _fields(it).get("Graphs") or []:
            o = ctx.export_by_ref(ref)
            if o is not None:
                role[ctx.full_name(o)] = "interface function"

    prefix = ""
    if bp_obj is not None:
        prefix = ctx.full_name(bp_obj) + "."
    renderers = {k: GraphRenderer(ctx, graphs[k], graphs[k].graph_name) for k in order}

    # transitions: inline rule expressions into their state machines
    rule_of = {}
    trans_title = {}
    for k, gr in renderers.items():
        if gr.mode() == "state machine":
            for src, dst, ref in gr.state_machine()[2]:
                fn = ref.get("full_name") if isinstance(ref, dict) else None
                if fn and fn in renderers:
                    trans_title[fn] = f"{src} → {dst}"
                    try:
                        rule_of[fn] = renderers[fn].rule_expr()
                    except Exception:
                        rule_of[fn] = None

    def rel_parts(key):
        rel = key[len(prefix):] if prefix and key.startswith(prefix) else key
        parts = rel.split(".")
        # keep only path components that are graphs themselves
        acc, names = [], []
        for i in range(len(parts)):
            cand = prefix + ".".join(parts[: i + 1])
            if cand in graphs:
                names.append(parts[i])
        return names or [graphs[key].graph_name]

    rank_of = {"event graph": 0, "function": 1, "interface function": 1, "macro": 2, "dispatcher": 4}

    def sort_key(k):
        names = rel_parts(k)
        root = prefix + names[0]
        rank = rank_of.get(role.get(root, role.get(k)), 3)
        # DFS in parse order: parent graphs first, children right after them
        path = [order.index(prefix + ".".join(names[: i + 1])) if prefix + ".".join(names[: i + 1]) in order
                else order.index(k) for i in range(len(names))]
        return (rank, path)

    ordered = sorted(order, key=sort_key)

    md = [f"# {asset_name}", "",
          f"`{game_path}` · {kind} · parent **{parent}**" + (f" · implements {', '.join(interfaces)}" if interfaces else ""),
          f"saved with UE {saved} · graph nodes decoded: {ok_nodes}/{total_nodes}", ""]

    comp = _components(ctx, bp_props)
    if comp:
        md += ["## Components (added in this Blueprint)", *comp, ""]
    wtree = _widget_tree(ctx, bp_props)
    if wtree:
        md += ["## Widget tree", *wtree, ""]
    nv = bp_props.get("NewVariables") or []
    if nv and not any(_fields(v).get("VarName") for v in nv):
        # uasset_read leaves arrays of structs opaque in some formats; re-read them with the tagged reader
        try:
            import data_reader
            rd = data_reader.TaggedReader(path, result, ctx)
            try:
                bp_export = next(e for e in result.export_map if e.object_name == bp_obj.object_name)
                items, _ = rd.export_stream(bp_export)
            finally:
                rd.close()
            nv2 = dict(items).get("NewVariables")
            if nv2:
                bp_props = dict(bp_props)
                bp_props["NewVariables"] = nv2
        except Exception:
            pass
    var_table, var_names = _variables(ctx, bp_props, cdo_props)
    if not var_table:
        inferred = {}
        for gr in renderers.values():
            for vn, t in gr.var_refs.items():
                inferred.setdefault(vn, t)
        comp_names = {ln.strip().lstrip("- ").split(" : ")[0] for ln in comp}
        inferred = {k: v for k, v in inferred.items() if k not in comp_names}
        if inferred and (bp_props.get("NewVariables") or not bp_props):
            var_table = ["_declarations not decodable for this engine version — listed from graph usage:_", "",
                         "| Name | Type |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(inferred.items())]
            var_names = set(inferred)
    if var_table:
        md += ["## Variables", *var_table, ""]
    cdo_l = _cdo_lines(cdo_props, var_names)
    if cdo_l:
        md += ["## Class defaults (values stored in the CDO)", *cdo_l, ""]

    summary = {"path": game_path, "kind": kind, "parent": parent, "interfaces": interfaces,
               "nodes_ok": ok_nodes, "nodes_total": total_nodes, "saved_with": saved,
               "entries": [], "calls": set(), "graphs": [], "functions": [], "dispatchers": []}

    dispatchers = []
    body = []
    for k in ordered:
        gr = renderers[k]
        r = role.get(k)
        names = rel_parts(k)
        if r == "dispatcher":
            entry = next((n for n in gr.nodes if n.class_name == "K2Node_FunctionEntry"), None)
            sig = gr.params_sig(entry) if entry is not None else ""
            dname = gr.name.replace("__DelegateSignature", "")
            dispatchers.append(f"- {dname}({sig})")
            summary["dispatchers"].append(dname)
            continue
        if k in trans_title:
            continue  # rendered inline in its state machine
        try:
            mode = gr.mode()
            if mode == "state machine":
                states, entry_state, trans = gr.state_machine()
                lines = ["states: " + ", ".join(states), f"entry → {entry_state or '?'}"]
                for src, dst, ref in trans:
                    fn = ref.get("full_name") if isinstance(ref, dict) else None
                    cond = rule_of.get(fn)
                    lines.append(f"{src} → {dst}" + (f"   when {cond}" if cond else ""))
            elif mode == "exec":
                lines = gr.render_exec()
            else:
                lines = gr.render_dataflow()
        except Exception as e:  # never let one graph kill the document
            mode, lines = "error", [f"(render failed: {type(e).__name__}: {e})"]
        missing = sum(1 for n in gr.nodes if not n.pins and n.class_name != "EdGraphNode_Comment")
        label = {"function": "function ", "macro": "macro ", "interface function": "interface function "}.get(r, "")
        path_title = " › ".join(names)
        lines = lines or ["(empty)"]
        meta = f"_{mode} graph · {len(gr.nodes)} nodes" + (f" · ⚠ {missing} nodes unreadable_" if missing else "_")
        body += ["", f"### {label}{path_title}", meta, "```text", *lines, "```"]
        summary["graphs"].append(path_title)
        if r in ("function", "interface function"):
            summary["functions"].append(names[-1])
        for n in gr.nodes:
            if n.class_name in _ENTRY_CLASSES and n.class_name not in ("K2Node_FunctionEntry", "K2Node_Tunnel"):
                h = gr.entry_header(n).split("(")[0]
                if h.replace("event ", "") not in gr.unused_events:
                    summary["entries"].append(h)
            if n.class_name in _CALL_CLASSES:
                fn, par, _ = gr.member_ref(n)
                if par and n.class_name not in ("K2Node_CommutativeAssociativeBinaryOperator", "K2Node_PromotableOperator"):
                    summary["calls"].add(f"{par}::{fn}")
    if dispatchers:
        md += ["## Event dispatchers", *dispatchers, ""]
    md.append("## Graphs")
    md += body if body else ["(no graphs)"]
    summary["calls"] = sorted(summary["calls"])
    return {"markdown": "\n".join(md) + "\n", "summary": summary}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Render one Blueprint .uasset to Markdown")
    ap.add_argument("uasset")
    ap.add_argument("--game-path", default=None)
    a = ap.parse_args()
    out = read_blueprint(a.uasset, a.game_path or Path(a.uasset).stem)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(out["markdown"])
