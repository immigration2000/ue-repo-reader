"""Data assets (.uasset) -> AI-readable Markdown, without the Unreal Editor.

Covers DataTables (every row), UserDefinedStructs (field definitions), UserDefinedEnums (values),
and any other data-bearing asset — DataAssets of project C++ types, InputMappingContexts,
InputActions, Blackboards, curves … — as a tree of their saved properties.

The core is a tagged-property stream reader on top of uasset_read that also descends into
arrays of structs (which uasset_read leaves opaque unless it knows the struct's schema).
"""
from __future__ import annotations

import logging
import re
import struct as _struct
from pathlib import Path

import bp_reader as B

MAX_ROWS = 300
NATIVE_BINARY_STRUCTS = {  # structs serialized as raw binary, not as tagged properties
    "Vector", "Vector2D", "Vector4", "Vector3f", "Vector3d", "Rotator", "Quat", "Guid", "Color", "LinearColor",
    "IntPoint", "IntVector", "Box", "Box2D", "Plane", "Matrix", "DateTime", "Timespan", "FrameNumber",
    "SoftObjectPath", "SoftClassPath", "GameplayTagContainer", "GameplayTag", "PerPlatformFloat", "PerPlatformInt",
    "RichCurveKey", "SimpleCurveKey", "NavAgentSelector", "FrameRate", "UniqueNetIdRepl", "Sphere",
}
_GUID_SUFFIX = re.compile(r"_\d+_[0-9A-F]{32}$")


def clean_name(n: str) -> str:
    """UserDefinedStruct field names carry '_<n>_<GUID>' suffixes on disk."""
    return _GUID_SUFFIX.sub("", str(n))


class TaggedReader:
    """Reads tagged-property streams straight from the package file."""

    def __init__(self, path: str, result, ctx: B.Ctx):
        from uasset_read.archive import FArchive
        from uasset_read.parsers.property_parser import parse_property_value
        from uasset_read.serializers.property_tags import read_property_tag
        self.r = result
        self.ctx = ctx
        self.fv5 = result.summary.file_version_ue5
        self.ar = FArchive(path, tolerant=True)
        self.ar._file_version_ue5 = self.fv5
        # uasset_read rejects large-but-valid tags with per-type size heuristics; bound by the file instead.
        ar = self.ar
        ar.validate_size = lambda size, *a, **k: 0 <= size <= ar._file_size - ar.tell()
        self._read_tag = read_property_tag
        self._parse_value = parse_property_value
        self.names = list(result.name_map or [])

    def close(self):
        try:
            self.ar.close()
        except Exception:
            pass

    # ---- streams
    def export_stream(self, export):
        """Tagged properties of an export. Returns (items, end_offset)."""
        self.ar.seek(export.serial_offset)
        if self.fv5 >= 1011:
            ctrl = self.ar.read_u8()
            if ctrl & 0x02:
                self.ar.read_u8()
        items = self.stream(export.serial_offset + export.serial_size)
        return items, self.ar.tell()

    def stream(self, limit, depth=0):
        items = []
        for _ in range(4000):
            if self.ar.tell() >= limit or depth > 12:
                break
            tag = self._read_tag(self.ar, self.names, tolerant=True)
            if tag.name == "None":
                break
            if not str(tag.type).endswith("Property"):
                break  # desynchronised; stop rather than emit garbage
            end = tag.value_end_offset
            val = None
            try:
                if tag.type == "ArrayProperty":
                    val = self._struct_array(tag, depth)
                elif tag.type == "StructProperty":
                    val = self._tagged_struct(tag, depth)
                if val is None:
                    self.ar.seek(tag.value_start_offset)
                    val = self._parse_value(tag, self.ar, self.names, self.r.export_map, self.r.summary, depth, True)
                    val = self._resolve(tag, val)
            except Exception as e:  # noqa: BLE001
                val = f"<unreadable {tag.type}: {type(e).__name__}>"
            if end:
                self.ar.seek(end)
            items.append((tag.name, val))
        return items

    # ---- structs
    def _struct_name(self, tag):
        tn = getattr(tag, "type_name", None)
        if tn is not None and tn.name == "StructProperty" and tn.children:
            return tn.children[0].name
        return getattr(tag, "struct_type", None) or getattr(tag, "struct_name", None)

    def _tagged_struct(self, tag, depth):
        sname = self._struct_name(tag)
        if sname == "EdGraphPinType" and tag.size > 0:  # native: keep raw bytes for bp_reader._decode_var_type
            self.ar.seek(tag.value_start_offset)
            return {"kind": "binary_or_native_property", "struct_type": sname, "raw_data": self.ar.read(tag.size)}
        if not sname or sname in NATIVE_BINARY_STRUCTS or tag.size <= 0:
            return None
        self.ar.seek(tag.value_start_offset)
        if not self._looks_tagged(tag.value_end_offset):
            return None
        fields = self.stream(tag.value_end_offset, depth + 1)
        return {"struct_type": sname, "fields": dict(fields)} if fields else None

    def _looks_tagged(self, limit) -> bool:
        pos = self.ar.tell()
        try:
            if pos + 8 > limit:
                return False
            idx = self.ar.read_i32()
            num = self.ar.read_i32()
            return 0 <= idx < len(self.names) and 0 <= num < 1000
        except Exception:
            return False
        finally:
            self.ar.seek(pos)

    def _struct_array(self, tag, depth):
        tn = getattr(tag, "type_name", None)
        sname = None
        legacy = False
        if tn is not None and tn.children:
            inner = tn.children[0]
            if inner.name != "StructProperty":
                return None
            sname = inner.children[0].name if inner.children else None
        elif getattr(tag, "inner_type", None) == "StructProperty":
            legacy = True
        else:
            return None
        self.ar.seek(tag.value_start_offset)
        n = self.ar.read_i32()
        if n < 0 or n > 200000:
            return None
        if legacy:
            inner_tag = self._read_tag(self.ar, self.names, tolerant=True)
            sname = getattr(inner_tag, "struct_type", None) or getattr(inner_tag, "struct_name", None)
        if sname in ("RichCurveKey", "SimpleCurveKey"):
            keys = []
            for _ in range(n):
                if sname == "RichCurveKey":
                    interp = self.ar.read(3)[0]
                    t, v, at, _atw, lt, _ltw = _struct.unpack("<6f", self.ar.read(24))
                    self.ar.read(4)
                    keys.append({"struct_type": "Key", "fields": {"t": t, "v": v, "interp": ("linear", "constant", "cubic", "none")[interp] if interp < 4 else interp}})
                else:
                    t, v = _struct.unpack("<2f", self.ar.read(8))
                    keys.append({"struct_type": "Key", "fields": {"t": t, "v": v}})
            return keys
        if not sname or sname in NATIVE_BINARY_STRUCTS:
            return None
        out = []
        for _ in range(n):
            if not self._looks_tagged(tag.value_end_offset):
                return None
            out.append({"struct_type": sname, "fields": dict(self.stream(tag.value_end_offset, depth + 1))})
        return out

    def _resolve(self, tag, val):
        if tag.type in ("ObjectProperty", "ClassProperty", "InterfaceProperty", "WeakObjectProperty") and isinstance(val, int):
            return self.ctx.obj_name(val) or ("None" if val == 0 else val)
        if tag.type == "ArrayProperty" and isinstance(val, list) and val and all(isinstance(x, int) for x in val):
            inner = getattr(tag, "type_name", None)
            inner_name = inner.children[0].name if inner is not None and inner.children else getattr(tag, "inner_type", "")
            if inner_name in ("ObjectProperty", "ClassProperty", "SoftObjectProperty"):
                return [self.ctx.obj_name(x) or x for x in val]
        return val

    # ---- raw helpers
    def read_i32(self):
        return self.ar.read_i32()

    def read_fname(self):
        idx, num = self.ar.read_i32(), self.ar.read_i32()
        return self.ctx.fname(idx, num)


# =========================================================================== rendering

def _compact_struct(st, f):
    """Short forms for structs that show up everywhere in gameplay data."""
    if st == "PrimaryAssetId":
        t = f.get("PrimaryAssetType")
        tn = _fields_of(t).get("Name", t) if t is not None else "?"
        return f"{B.fmt_value(tn)}:{B.fmt_value(f.get('PrimaryAssetName'))}"
    if st in ("PrimaryAssetType",) and "Name" in f:
        return B.fmt_value(f["Name"])
    if st == "GameplayTag" and "TagName" in f:
        return B.fmt_value(f["TagName"])
    if st == "DataTableRowHandle":
        return f"{B.fmt_value(f.get('DataTable'))}.{B.fmt_value(f.get('RowName'))}"
    if st == "BlackboardKeySelector":
        k = f.get("SelectedKeyName")
        return f"bb:{B.fmt_value(k)}" if k not in (None, "None", "") else "bb:(unset)"
    if st and st.startswith("ValueOrBBKey") and "DefaultValue" in f:
        return B.fmt_value(f["DefaultValue"]) + (f" (bb:{B.fmt_value(f['Key'])})" if f.get("Key") not in (None, "None", "") else "")
    if st == "Key" and "KeyName" in f:
        return B.fmt_value(f["KeyName"])
    if st == "Key" and "t" in f:
        extra = f" {f['interp']}" if f.get("interp") not in (None, "cubic") else ""
        return f"({B.fmt_value(f['t'])}→{B.fmt_value(f['v'])}{extra})"
    if st in ("FloatRange", "Int32Range") and "LowerBound" in f:
        return f"[{_val(f.get('LowerBound'))} .. {_val(f.get('UpperBound'))}]"
    return None


def _fields_of(v):
    if isinstance(v, dict) and isinstance(v.get("fields"), dict):
        return v["fields"]
    return B._fields(v)


def _val(v, depth=0) -> str:
    """One-line value, with UserDefinedStruct field names cleaned."""
    st = (v.get("struct_type") if isinstance(v, dict) else getattr(v, "struct_type", None))
    f = _fields_of(v) if st else {}
    if st and f:
        c = _compact_struct(st, f)
        if c is not None:
            return c
    if type(v).__name__ == "MapValue":
        ents = getattr(v, "entries", None) or []
        parts = [f"{_val(e.get('key'), depth + 1)}: {_val(e.get('value'), depth + 1)}" for e in ents[:10] if isinstance(e, dict)]
        return "{" + ", ".join(parts) + (f", …(+{len(ents) - 10})" if len(ents) > 10 else "") + "}"
    if type(v).__name__ == "StructValue" and f:
        inner = ", ".join(f"{clean_name(k)}={_val(x, depth + 1)}" for k, x in list(f.items())[:10])
        return f"{st}{{{inner}}}" if depth == 0 else "{" + inner + "}"
    if isinstance(v, dict) and "fields" in v and isinstance(v["fields"], dict):
        inner = ", ".join(f"{clean_name(k)}={_val(x, depth + 1)}" for k, x in list(v["fields"].items())[:10])
        st = v.get("struct_type") or ""
        return f"{st}{{{inner}}}" if st and st not in ("UnknownStruct",) else "{" + inner + "}"
    if isinstance(v, list):
        items = [_val(x, depth + 1) for x in v[:10]]
        return "[" + ", ".join(items) + (f", …(+{len(v) - 10})" if len(v) > 10 else "") + "]"
    s = B.fmt_value(v, depth)
    return s.replace("\n", "\\n").replace("|", "/")


def render_tree(items, indent=0, max_lines=400) -> list[str]:
    lines = []
    pad = "  " * indent
    for name, v in items:
        if len(lines) > max_lines:
            lines.append(pad + "- …")
            break
        name = clean_name(name)
        one = _val(v)
        if len(one) <= 140 or not isinstance(v, (list, dict)):
            lines.append(f"{pad}- {name} = {one}")
        elif isinstance(v, dict) and "fields" in v:
            lines.append(f"{pad}- {name}: {v.get('struct_type') or ''}")
            lines.extend(render_tree(list(v["fields"].items()), indent + 1))
        else:
            lines.append(f"{pad}- {name} ({len(v)} items):")
            for i, el in enumerate(v[:60]):
                s = _val(el)
                if len(s) <= 160 or not (isinstance(el, dict) and "fields" in el):
                    lines.append(f"{pad}  - [{i}] {s}")
                else:
                    lines.append(f"{pad}  - [{i}] {el.get('struct_type') or ''}")
                    lines.extend(render_tree(list(el["fields"].items()), indent + 2))
            if len(v) > 60:
                lines.append(f"{pad}  - … {len(v) - 60} more")
    return lines


_CONTAINER = {"None": 0, "Array": 1, "Set": 2, "Map": 3}


def _obj_label(ctx, obj) -> str:
    if obj in (None, 0, "None", ""):
        return ""
    if hasattr(obj, "asset_path"):  # SoftObjectPathValue
        p = str(getattr(obj, "asset_path", "") or "")
        return "" if p in ("", "None", "None.None") else p.rsplit(".", 1)[-1]
    if isinstance(obj, str):
        return obj.rsplit(".", 1)[-1]
    return ctx.obj_name(obj)


def _pin_type_from_desc(ctx, f) -> str:
    cat = f.get("Category") or ""
    sub = f.get("SubCategory") or ""
    obj_name = _obj_label(ctx, f.get("SubCategoryObject"))
    ct = f.get("ContainerType")
    ct = B.fmt_value(ct) if ct is not None else "None"
    container = _CONTAINER.get(ct.split("::")[-1], 0)
    vt = None
    if container == 3:
        pv = f.get("PinValueType") or {}
        pvf = pv.get("fields", {}) if isinstance(pv, dict) else B._fields(pv)
        vt = B._type_str(pvf.get("TerminalCategory"), pvf.get("TerminalSubCategory"),
                         _obj_label(ctx, pvf.get("TerminalSubCategoryObject")))
    return B._type_str(cat, sub, obj_name, container, vt)


def _enum_names(reader: TaggedReader, end_of_props: int, enum_name: str):
    """UEnum::Names (TArray<TPair<FName,int64>>) that follows the tagged properties."""
    for skip in (4, 8, 0, 12, 20):
        try:
            reader.ar.seek(end_of_props + skip)
            n = reader.read_i32()
            if not 0 < n < 5000:
                continue
            out = []
            for _ in range(n):
                name = reader.read_fname()
                value = _struct.unpack("<q", reader.ar.read(8))[0]
                out.append((name, value))
            if out and all("::" in nm or nm.endswith("_MAX") for nm, _ in out):
                return out
        except Exception:
            continue
    return None


def _render_enum(reader, export, items, end):
    props = dict(items)
    display = {}
    dnm = props.get("DisplayNameMap")
    entries = getattr(dnm, "entries", None) or []
    for e in entries:
        k = e.get("key") if isinstance(e, dict) else None
        v = e.get("value") if isinstance(e, dict) else None
        if k is not None:
            display[str(k)] = B.fmt_value(v).strip('"')
    names = _enum_names(reader, end, export.object_name)
    rows = ["| Value | Enumerator | Display name |", "|---|---|---|"]
    count = 0
    if names:
        for nm, value in names:
            short = nm.split("::")[-1]
            if short.endswith("_MAX"):
                continue
            rows.append(f"| {value} | {short} | {display.get(short, '')} |")
            count += 1
    else:
        for i, (k, v) in enumerate(display.items()):
            rows.append(f"| {i} | {k} | {v} |")
            count += 1
    return rows, f"enum with {count} values"


def _render_struct(reader, ctx, export, items):
    props = dict(items)
    ref = props.get("EditorData")
    ed = ctx.export_by_name(ref) if isinstance(ref, str) else ctx.export_by_ref(ref)
    descs = []
    if ed is not None:
        e_export = next((x for x in reader.r.export_map if x.object_name == ed.object_name), None)
        if e_export is not None:
            ed_items, _ = reader.export_stream(e_export)
            descs = dict(ed_items).get("VariablesDescriptions") or []
    rows = ["| Field | Type | Default | Tooltip |", "|---|---|---|---|"]
    n = 0
    for d in descs if isinstance(descs, list) else []:
        f = d.get("fields", {}) if isinstance(d, dict) else {}
        if not f:
            continue
        name = f.get("FriendlyName") or clean_name(f.get("VarName") or "?")
        tip = B.fmt_value(f.get("ToolTip")) if f.get("ToolTip") not in (None, "") else ""
        dv = f.get("DefaultValue")
        rows.append(f"| {name} | {_pin_type_from_desc(ctx, f)} | {B.fmt_value(dv) if dv not in (None, '') else ''} | {tip.strip(chr(34))} |")
        n += 1
    if n == 0:
        return None, "struct (fields not decodable)"
    return rows, f"struct with {n} fields"


def _render_datatable(reader, ctx, export, items, end):
    props = dict(items)
    rs = props.get("RowStruct")
    row_struct = rs if isinstance(rs, str) else (ctx.obj_name(rs) or "?")
    reader.ar.seek(end)
    has_guid = reader.read_i32()
    if has_guid == 1:
        reader.ar.read(16)
    elif has_guid != 0:
        reader.ar.seek(end)
    n = reader.read_i32()
    if not 0 <= n <= 1_000_000:
        return None, f"DataTable of {row_struct} (rows not decodable)", row_struct
    rows = []
    limit = export.serial_offset + export.serial_size
    for _ in range(n):
        name = reader.read_fname()
        fields = reader.stream(limit)
        rows.append((name, fields))
    cols = []
    for _, fields in rows:
        for k, _v in fields:
            ck = clean_name(k)
            if ck not in cols:
                cols.append(ck)
    lines = []
    shown = rows[:MAX_ROWS]
    cells = [[_val(dict((clean_name(k), v) for k, v in f).get(c)) if c in {clean_name(k) for k, _ in f} else ""
              for c in cols] for _, f in shown]
    wide = len(cols) > 12 or any(len(x) > 90 for row in cells for x in row)
    if not cols:
        lines += ["| Row |", "|---|"] + [f"| {name} |" for name, _ in shown]
    elif not wide:
        lines += ["| Row | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
        for (name, _), cs in zip(shown, cells):
            lines.append(f"| {name} | " + " | ".join(cs) + " |")
    else:
        for name, fields in shown:
            lines.append(f"### {name}")
            lines += render_tree(fields)
            lines.append("")
    if n > MAX_ROWS:
        lines.append(f"\n_… {n - MAX_ROWS} more rows not shown (of {n})._")
    note = "_Only values saved in the asset are shown; a column left empty means the row uses the struct's default._"
    return [note, ""] + lines, f"{n} rows of {row_struct}", row_struct


class ExportProps:
    """Lazy per-export property cache (by object name) through the TaggedReader."""

    def __init__(self, reader, ctx):
        self.reader, self.ctx = reader, ctx
        self.by_name = {}
        for i, e in enumerate(reader.r.export_map):
            self.by_name.setdefault(e.object_name, e)
        self.cache = {}

    def get(self, name):
        if not isinstance(name, str) or name not in self.by_name:
            return {}
        if name not in self.cache:
            try:
                items, _ = self.reader.export_stream(self.by_name[name])
            except Exception:
                items = []
            self.cache[name] = dict(items)
        return self.cache[name]

    def cls(self, name):
        e = self.by_name.get(name)
        if e is None:
            return ""
        o = self.ctx.obj(self.reader.r.export_map.index(e) + 1)
        return self.ctx.class_of(o) if o is not None else ""


_BT_SKIP = {"TreeAsset", "ParentNode", "NodeName", "Children", "Services", "Decorators", "CachedDescription",
            "DecoratorOps", "bInjectedNode", "NodeInstance"}


def _bt_label(ep, name):
    cls = ep.cls(name)
    p = ep.get(name)
    short = cls
    for pre in ("BTComposite_", "BTTask_", "BTDecorator_", "BTService_"):
        if short.startswith(pre):
            short = short[len(pre):]
    title = f'{short} "{B.fmt_value(p["NodeName"])}"' if p.get("NodeName") else short
    desc = p.get("CachedDescription")
    if desc:
        return f"{title} — {B.fmt_value(desc)}"
    args = [f"{k}={_val(v)}" for k, v in p.items() if k not in _BT_SKIP and not k.startswith("Node")]
    return f"{title}({', '.join(args)})" if args else title


def _render_bt(ep, root):
    lines = []

    def walk(comp, depth, seen):
        pad = "  " * depth
        if comp in seen or depth > 40:
            lines.append(pad + "…")
            return
        seen = seen | {comp}
        lines.append(pad + _bt_label(ep, comp))
        p = ep.get(comp)
        for sv in p.get("Services") or []:
            lines.append(f"{pad}  ⚙ service {_bt_label(ep, sv)}")
        for ch in p.get("Children") or []:
            f = ch.get("fields", {}) if isinstance(ch, dict) else {}
            for dec in f.get("Decorators") or []:
                lines.append(f"{pad}  ◆ if {_bt_label(ep, dec)}")
            if f.get("ChildComposite") not in (None, "None"):
                walk(f["ChildComposite"], depth + 1, seen)
            elif f.get("ChildTask") not in (None, "None"):
                lines.append(f"{pad}  - {_bt_label(ep, f['ChildTask'])}")
    walk(root, 0, set())
    return lines


def _render_state_tree(items):
    states = dict(items).get("States") or []
    lines = []
    for st in states if isinstance(states, list) else []:
        f = st.get("fields", {}) if isinstance(st, dict) else {}
        if not f:
            continue
        depth = f.get("Depth") or 0
        bits = []
        for key, lab in (("TasksNum", "tasks"), ("EnterConditionsNum", "enter conditions"), ("TransitionsNum", "transitions")):
            if f.get(key):
                bits.append(f"{f[key]} {lab}")
        typ = B.fmt_value(f.get("Type")) if f.get("Type") is not None else ""
        linked = f.get("LinkedAsset")
        extra = f" → linked {B.fmt_value(linked)}" if linked not in (None, "None") else ""
        lines.append(f"{'  ' * int(depth)}- {B.fmt_value(f.get('Name'))}" + (f" [{typ}]" if typ and typ != "State" else "")
                     + (f" ({', '.join(bits)})" if bits else "") + extra)
    return lines


def _render_mapping_context(items):
    d = dict(items)
    maps = d.get("Mappings")
    if maps is None and isinstance(d.get("DefaultKeyMappings"), dict):
        maps = d["DefaultKeyMappings"].get("fields", {}).get("Mappings")
    if not isinstance(maps, list):
        return None
    rows = ["| Action | Key | Modifiers | Triggers |", "|---|---|---|---|"]
    for m in maps:
        f = m.get("fields", {}) if isinstance(m, dict) else {}
        rows.append(f"| {_val(f.get('Action'))} | {_val(f.get('Key'))} | "
                    f"{', '.join(_val(x) for x in f.get('Modifiers') or []) or ''} | "
                    f"{', '.join(_val(x) for x in f.get('Triggers') or []) or ''} |")
    return rows


_NO_EXPAND = {"EdGraph", "BTGraph", "EditorData", "Schema", "TreeAsset", "ParentNode", "AssetImportData",
              "ThumbnailInfo", "Outer"}


def expand_subobjects(items, ep, main_name, depth=0, seen=None):
    """Replace names of this package's own sub-objects with their saved properties."""
    seen = set() if seen is None else seen
    out = []

    def conv(v, key):
        if depth > 3 or key in _NO_EXPAND:
            return v
        if isinstance(v, str) and v in ep.by_name and v != main_name and v not in seen:
            props = ep.get(v)
            cls = ep.cls(v) or v
            if not props:
                return cls
            props = [(k2, x) for k2, x in props.items() if not k2.startswith("Node") and k2 not in ("TreeAsset", "ParentNode")]
            return {"struct_type": cls, "fields": dict(expand_subobjects(props, ep, main_name, depth + 1, seen | {v}))}
        if isinstance(v, list):
            return [conv(x, key) for x in v]
        if isinstance(v, dict) and isinstance(v.get("fields"), dict):
            return {"struct_type": v.get("struct_type"), "fields": {k: conv(x, k) for k, x in v["fields"].items()}}
        return v

    for k, v in items:
        out.append((k, conv(v, k)))
    return out


def _render_string_table(reader, end):
    """UStringTable native payload: namespace, key -> source string map, then metadata."""
    for skip in (4, 0, 8):
        try:
            reader.ar.seek(end + skip)
            ns = reader.ar.read_fstring()
            n = reader.read_i32()
            if not 0 <= n < 200000:
                continue
            entries = [(reader.ar.read_fstring(), reader.ar.read_fstring()) for _ in range(n)]
            rows = [f"Namespace: `{ns}`", "", "| Key | Source string |", "|---|---|"]
            rows += [f"| {k} | {v.replace(chr(10), ' ').replace('|', '/')} |" for k, v in entries[:MAX_ROWS]]
            if n > MAX_ROWS:
                rows.append(f"\n_… {n - MAX_ROWS} more entries_")
            return rows, n
        except Exception:
            continue
    return None, 0


def _render_blackboard(items):
    keys = dict(items).get("Keys")
    if not isinstance(keys, list):
        return None
    rows = ["| Key | Type | Details | Instance synced |", "|---|---|---|---|"]
    for k in keys:
        f = k.get("fields", {}) if isinstance(k, dict) else {}
        kt = f.get("KeyType")
        if isinstance(kt, dict):
            tname = str(kt.get("struct_type") or "?")
            details = ", ".join(f"{a}={_val(b)}" for a, b in (kt.get("fields") or {}).items())
        else:
            tname, details = str(kt), ""
        tname = tname.replace("BlackboardKeyType_", "")
        rows.append(f"| {B.fmt_value(f.get('EntryName'))} | {tname} | {details} | {B.fmt_value(f.get('bInstanceSynced', False))} |")
    parent = dict(items).get("Parent")
    return rows, parent


def _references(result, ctx) -> list[str]:
    """Project assets this package imports (by object name), for cross-referencing."""
    out = []
    for o in result.all_objects:
        if getattr(o, "is_export", True):
            continue
        fn = ctx.full_name(o)
        pkg = fn.split(".")[0] if fn else ""
        if not pkg.startswith("/") or pkg.startswith(("/Script/", "/Engine/")):
            continue
        name = _short(o.object_name)
        if ctx.class_of(o) == "Package" or name in out:
            continue
        out.append(name)
    return out


def _short(n):
    return B._short(n)


def read_data_asset(path: str, game_path: str, asset_class: str) -> dict:
    B.ensure_uasset_read()
    logging.disable(logging.CRITICAL)
    B._install_patches()
    from uasset_read.parse_uasset import parse_uasset_with_linker
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    result = parse_uasset_with_linker(path, force_full_parse=True, preload_all=True)
    ctx = B.Ctx(result)
    stem = Path(path).stem
    export = next((e for e in result.export_map if e.object_name == stem), None) or \
        next((e for e in result.export_map if getattr(e, "b_is_asset", False)), None)
    if export is None:
        raise ValueError("main export not found")
    reader = TaggedReader(path, result, ctx)
    try:
        items, end = reader.export_stream(export)
        ev = getattr(result.summary, "saved_by_engine_version", None)
        saved = f"{ev.major}.{ev.minor}.{ev.patch}" if ev and getattr(ev, "major", 0) else "?"
        md = [f"# {stem}", "", f"`{game_path}` · **{asset_class}** · saved with UE {saved}", ""]
        headline = asset_class
        extra = {}
        body = None
        if asset_class == "UserDefinedEnum":
            body, headline = _render_enum(reader, export, items, end)
            md += ["## Values", *body, ""]
        elif asset_class == "UserDefinedStruct":
            body, headline = _render_struct(reader, ctx, export, items)
            if body:
                md += ["## Fields", *body, ""]
        elif asset_class in ("DataTable", "CompositeDataTable"):
            body, headline, rs = _render_datatable(reader, ctx, export, items, end)
            extra["row_struct"] = rs
            md += [f"Row struct: **{rs}**", ""]
            if body:
                md += ["## Rows", *body, ""]
        elif asset_class == "BehaviorTree":
            ep = ExportProps(reader, ctx)
            root = dict(items).get("RootNode")
            bb = dict(items).get("BlackboardAsset")
            if root not in (None, "None"):
                body = _render_bt(ep, root)
                md += [f"Blackboard: **{B.fmt_value(bb)}**", "", "## Tree",
                       "_`◆ if` = decorator on the next child · `⚙ service` = service on the composite_", "",
                       "```text", *body, "```", ""]
                headline = f"behavior tree, {sum(1 for l in body if l.strip().startswith('-'))} tasks"
        elif asset_class == "StateTree":
            body = _render_state_tree(items) or None
            if body:
                md += ["## States", *body, "",
                       "_Task/condition instances are stored as instanced structs and are not decoded; "
                       "see References for the task and condition Blueprints this tree uses._", ""]
                headline = f"state tree, {len(body)} states"
        elif asset_class == "StringTable":
            body, n = _render_string_table(reader, end)
            if body:
                md += ["## Entries", *body, ""]
                headline = f"string table, {n} entries"
        elif asset_class == "BlackboardData":
            exp = expand_subobjects(items, ExportProps(reader, ctx), export.object_name)
            res = _render_blackboard(exp)
            if res:
                body, parent = res
                md += ["## Keys", *body, ""]
                if parent not in (None, "None"):
                    md += [f"Parent blackboard: **{B.fmt_value(parent)}**", ""]
                headline = f"blackboard, {len(body) - 2} keys"
        elif asset_class == "InputMappingContext":
            body = _render_mapping_context(items)
            if body:
                md += ["## Mappings", *body, ""]
                headline = f"input mapping context, {len(body) - 2} mappings"
        skip = {"AssetImportData", "ThumbnailInfo", "PackageMetaData", "EditorData", "Guid", "UniqueNameId", "EdGraph",
                "UniqueNameIndex", "DisplayNameMap", "RowStructPathName", "RowStruct"}
        if asset_class in ("BehaviorTree", "StateTree", "InputMappingContext", "BlackboardData") and body:
            skip |= {"Keys", "Parent"}
            skip |= {"RootNode", "BTGraph", "LastEditedDocuments", "States", "Mappings", "DefaultKeyMappings",
                     "Nodes", "Transitions", "InstanceDataStorage", "SharedInstanceData", "Parameters",
                     "PropertyBindings", "EditorData", "ContextDataDescs", "LastCompiledEditorDataHash",
                     "Frames", "NumContextData", "NumGlobalInstanceData", "EvaluatorsBegin", "GlobalTasksBegin",
                     "IDToStateMappings", "IDToNodeMappings", "IDToTransitionMappings", "DefaultInstanceData",
                     "DefaultEvaluationScopeInstanceData", "DefaultExecutionRuntimeData"}
        rest = [(k, v) for k, v in items if k not in skip]
        try:
            rest = expand_subobjects(rest, ExportProps(reader, ctx), export.object_name)
        except Exception:
            pass
        if rest:
            title = "Properties" if body is None else "Other properties"
            md += [f"## {title}", *render_tree(rest), ""]
        elif body is None:
            md += ["_(no saved properties — everything is at its class defaults)_", ""]
        if body is None and asset_class not in ("UserDefinedEnum", "UserDefinedStruct", "DataTable"):
            headline = f"{asset_class}, {len(rest)} saved properties"
        refs = _references(result, ctx)
        if refs:
            md += ["## References (project assets used)", ", ".join(f"`{r}`" for r in refs[:60])
                   + (" …" if len(refs) > 60 else ""), ""]
        summary = {"path": game_path, "class": asset_class, "headline": headline, "references": refs, **extra}
        return {"markdown": "\n".join(md) + "\n", "summary": summary}
    finally:
        reader.close()


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Render one data asset (.uasset) to Markdown")
    ap.add_argument("uasset")
    ap.add_argument("--class", dest="cls", default="DataAsset")
    ap.add_argument("--game-path", default=None)
    a = ap.parse_args()
    out = read_data_asset(a.uasset, a.game_path or Path(a.uasset).stem, a.cls)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(out["markdown"])
