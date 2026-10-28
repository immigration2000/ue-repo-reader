"""Typed enum arrays: exact identity/value lookup, safe spans, bounded rendering and raw-cache reuse."""
import io
import json
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import asset_cache as C
import data_reader as D
import enum_values as E
import navigation as N
import ue_repo_digest as U


def tag(path="/Game/E_Test", name="E_Test", kind="ByteProperty"):
    enum = NS(name=name, children=[NS(name=path, children=[])] if path else [])
    inner = NS(name=kind, children=[enum])
    return NS(type="ArrayProperty", type_name=NS(name="ArrayProperty", children=[inner]), inner_type=kind)


def decode_array(values, property_tag=None):
    reader = D.TaggedReader.__new__(D.TaggedReader)
    reader.enum_spans = E.EnumSpans()
    reader.names = ["None", *dict.fromkeys(value for value in values if isinstance(value, str))]
    reader.ctx = NS(obj_name=lambda value: "Actor" if value == -1 else "",
                    fname=lambda index, number: reader.names[index] + (f"_{number - 1}" if number else ""))
    if values and isinstance(values[0], str):
        payload = b"".join(struct.pack("<ii", reader.names.index(value), 0) for value in values)
    else:
        payload = bytes(values)
    class Archive(io.BytesIO):
        def read_i32(self): return struct.unpack("<i", self.read(4))[0]
    reader.ar = Archive(struct.pack("<i", len(values)) + payload)
    property_tag = property_tag or tag()
    property_tag.value_start_offset, property_tag.value_end_offset = 0, 4 + len(payload)
    return reader, reader._enum_array(property_tag)


def catalog_asset(path="/Game/E_Test", entries=None, **summary):
    return {"markdown": "# Enum", "summary": {"class": "UserDefinedEnum", "parse_status": "ok", "issues": [],
            "path": path, "enum_values": entries or {"7": [{"name": "E_Test::Entry_7", "display": "Crate"}],
                                                     "42": [{"name": "E_Test::Entry_42", "display": "Other"}]}, **summary}}


def rendered(values=(7, 42, 255)):
    reader, typed = decode_array(list(values))
    # This literal looks exactly like an unresolved enum but is ordinary saved text.
    literal = 'literal E_Test(7; unresolved); plain [7, 42, 255]'
    text = "한글 🙂\n" + literal + "\n" + "\n".join(D.render_tree([("Codes", typed)])) + "\n"
    markdown, spans = reader.enum_spans.finish(text)
    return {"markdown": markdown, "enum_spans": spans,
            "summary": {"path": "/Game/Data", "class": "DataAsset", "headline": "saved values",
                        "parse_status": "ok", "issues": []}}


def test_enum_arrays_only_use_explicit_type_identity():
    reader, typed = decode_array([7, 42])
    assert isinstance(typed, E.EnumArray) and typed == [7, 42]
    assert E.reference_from_tag(tag()) == {"name": "E_Test", "path": "/Game/E_Test"}
    for property_tag in (NS(type="ArrayProperty", type_name=None, inner_type="ByteProperty"), tag(name="None")):
        assert type(reader._resolve(property_tag, [7, 42])) is list
    assert type(reader._resolve(tag(), [True, False])) is list
    assert reader._resolve(NS(type="ArrayProperty", type_name=None, inner_type="ObjectProperty"), [-1]) == ["Actor"]
    enum_reader, enum_array = decode_array(["E_Test::Entry_42"], tag(kind="EnumProperty"))
    assert isinstance(enum_array, E.EnumArray)
    assert not reader.enum_spans.values and not enum_reader.enum_spans.values, "array allocated render tokens eagerly"


def test_enum_fname_arrays_decode_names_not_name_index_bytes():
    reader, typed = decode_array(["E_Test::Entry_42", "E_Test::Entry_7", "E_Test::Gone"])
    # The first FName index is 1, but the enum value is 42. Byte-reading would invent [1, 0, 0].
    assert list.__getitem__(typed, 0) == "E_Test::Entry_42"
    text, spans = reader.enum_spans.finish("\n".join(D.render_tree([("Codes", typed)])))
    result = {"markdown": text, "enum_spans": spans, "summary": {}}
    E.resolve_asset_enums(result, E.EnumCatalog({"/Game/E_Test": catalog_asset()}))
    assert 'E_Test::Entry_42(42, display="Other")' in result["markdown"]
    assert 'E_Test::Entry_7(7, display="Crate")' in result["markdown"]
    assert "E_Test::Gone(value unresolved)" in result["markdown"]
    assert result["summary"]["enum_resolution"] == {"resolved": 2, "unresolved": 1}
    reader, _ = decode_array(["E_Test::Entry_42"])
    reader.enum_spans = None
    t = tag()
    t.value_start_offset, t.value_end_offset = 0, 12
    assert reader._enum_array(t) == ["E_Test::Entry_42"]
    t.value_end_offset = 11
    try:
        reader._enum_array(t)
    except ValueError:
        pass
    else:
        raise AssertionError("truncated FName array was treated as byte values")


def test_enum_spans_preserve_literals_numbers_and_unknown_values():
    value = rendered()
    assert "\x1e" not in value["markdown"] and "\x1f" not in value["markdown"]
    assert len(value["enum_spans"]) == 3
    E.resolve_asset_enums(value, E.EnumCatalog({"/Game/E_Test": catalog_asset()}))
    assert 'E_Test::Entry_7(7, display="Crate")' in value["markdown"]
    assert 'E_Test::Entry_42(42, display="Other")' in value["markdown"]
    assert "E_Test(255; unresolved)" in value["markdown"]
    assert "literal E_Test(7; unresolved); plain [7, 42, 255]" in value["markdown"], "ordinary text/numbers rewritten"
    assert value["summary"]["enum_resolution"] == {"resolved": 2, "unresolved": 1}
    invalid = rendered()
    invalid["enum_spans"][0]["start"] += 1
    try:
        E.resolve_asset_enums(invalid, E.EnumCatalog({}))
    except ValueError:
        pass
    else:
        raise AssertionError("stale render offsets accepted")


def test_enum_catalog_ambiguity_partial_and_aliases():
    one, two = "/Game/One/E_Test", "/Plugin/Two/E_Test"
    catalog = E.EnumCatalog({one: catalog_asset(one), two: catalog_asset(two)})
    assert catalog.label({"name": "E_Test", "path": one}, 7)
    assert catalog.label({"name": "E_Test", "path": ""}, 7) is None
    assert catalog.label({"name": "E_Test", "path": "/Unknown/E_Test"}, 7) is None
    assert catalog.label({"name": "E_Test", "path": one, "ambiguous": True}, 7) is None
    for summary in ({"parse_status": "partial"}, {"issues": [{"stage": "failed"}]}, {"newer_format": "unknown"}):
        assert E.EnumCatalog({one: catalog_asset(one, **summary)}).label({"name": "E_Test", "path": one}, 7) is None
    aliases = {"7": [{"name": "E_Test::A", "display": "A"}, {"name": "E_Test::B", "display": "B"}]}
    assert E.EnumCatalog({one: catalog_asset(one, aliases)}).label({"name": "E_Test", "path": one}, 7) is None


def test_enum_sparse_serialized_values_are_not_display_order():
    class Reader:
        names = ["E_Test::A", "E_Test::B", "E_Test::E_Test_MAX"]
        def __init__(self):
            self.ar = io.BytesIO(struct.pack("<ii", 1, 3) + b"".join(struct.pack("<iiq", i, 0, value)
                                                                   for i, value in enumerate((7, 42, 43))))
        def read_i32(self): return struct.unpack("<i", self.ar.read(4))[0]
        def read_fname(self):
            index, number = struct.unpack("<ii", self.ar.read(8))
            return self.names[index]
    items = [("DisplayNameMap", NS(entries=[{"key": "A", "value": "First"}, {"key": "B", "value": "Second"}]))]
    rows, headline, values = D._render_enum(Reader(), NS(object_name="E_Test"), items, 0)
    assert set(values) == {"7", "42"} and values["42"][0]["display"] == "Second"
    assert "| 42 | B | Second |" in rows and headline == "enum with 2 values"
    assert D._enum_names(Reader(), 0, "WrongEnum") is None
    with patch.object(D, "_enum_names", return_value=None):
        assert D._render_enum(Reader(), NS(object_name="E_Test"), items, 0)[2] == {}, "display order was trusted as values"


def test_enum_large_arrays_render_lazily_and_cache_raw_values():
    reader, typed = decode_array([7] * 200_000)
    assert D.expand_subobjects([("Codes", typed)], NS(by_name={}), "Data")[0][1] is typed
    text = "\n".join(D.render_tree([("Codes", typed)]))
    markdown, spans = reader.enum_spans.finish(text)
    assert len(spans) == 60 and len(reader.enum_spans.values) <= 80
    assert "199940 more" in markdown and "\x1e" not in markdown
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        asset = base / "A.uasset"
        asset.write_bytes(b"unchanged asset")
        cache = C.AssetCache(base / "cache", base, "test", fingerprint="enum-decoder")
        key, raw = cache.key("data", (asset, "/Game/Data", "DataAsset")), rendered((7,))
        cache.store(key, raw)
        first, second = cache.load(key), cache.load(key)
        E.resolve_asset_enums(first, E.EnumCatalog({"/Game/E_Test": catalog_asset()}))
        changed = catalog_asset()
        changed["summary"]["enum_values"]["7"][0]["display"] = "Updated"
        E.resolve_asset_enums(second, E.EnumCatalog({"/Game/E_Test": changed}))
        assert 'display="Crate"' in first["markdown"] and 'display="Updated"' in second["markdown"]
        assert cache.stats["writes"] == 1 and cache.stats["hits"] == 2
        assert cache.load(key)["markdown"] == raw["markdown"], "resolved labels polluted raw cache"
        assert json.loads(json.dumps(raw, ensure_ascii=False))["enum_spans"] == raw["enum_spans"]


def test_enum_unresolved_limits_visible_in_indexes():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = rendered((255,))
        E.resolve_asset_enums(result, E.EnumCatalog({}))
        data = {"/Game/Data": result}
        (out / "cpp").mkdir()
        (out / "cpp/CLASSES.md").write_text("# C++\n", encoding="utf-8")
        with patch.object(U, "gameplay_tags", return_value=([], None)):
            U.build_index({}, out, {"classes": [], "modules": []}, {}, {}, [], [], {}, out, None, datas=data)
        assert "enum labels unresolved" in (out / "INDEX.md").read_text(encoding="utf-8")
        assert "everything decoded cleanly" not in (out / "INDEX.md").read_text(encoding="utf-8")
        N.build_navigation({}, {}, {}, {}, data, {}, {}, {}, {}, out)
        index = (out / "INDEX.md").read_text(encoding="utf-8")
        assert "Unresolved enum labels: 1" in index and "everything decoded cleanly" not in index
