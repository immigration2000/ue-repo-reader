"""Culture-invariant FText payloads, exact field boundaries, and display/IR propagation."""
import io
import struct
from types import SimpleNamespace as NS

import bp_reader as B
import data_reader as D


def payload(text="Control", *, wide=False):
    content = text.encode("utf-16-le" if wide else "latin-1") + (b"\0\0" if wide else b"\0")
    length = -len(content) // 2 if wide else len(content)
    return struct.pack("<Ibii", 2, -1, 1, length) + content


def test_invariant_text_preserves_ansi_utf16_empty_and_exact_source():
    for text, wide in (("InnerFunctions", False), ("caf\xe9", True), ("한글\n`category`", True), ("", False)):
        assert D.invariant_text_source(payload(text, wide=wide)) == text
    assert D.invariant_text_source(struct.pack("<Ibi", 0, -1, 0)) == ""
    assert D.invariant_text_source(struct.pack("<Ibii", 2, -1, 1, 0)) == ""


def test_invariant_text_refuses_truncation_invalid_lengths_flags_and_boundaries():
    raw = payload()
    values = [raw[:i] for i in range(len(raw))]
    values += [raw + b"\0", raw[:5] + struct.pack("<i", 2) + raw[9:],
               raw[:9] + struct.pack("<i", 2**31 - 1) + raw[13:], raw[:-1] + b"X",
               payload("bad\0text"), payload("caf\xe9"), struct.pack("<Ibii", 2, -1, 1, -2) + b"\0\xd8\0\0",
               struct.pack("<Ibi", 0, -1, 0) + b"extra"]
    for value in values:
        try:
            D.invariant_text_source(value)
        except (ValueError, UnicodeError):
            continue
        raise AssertionError("invalid invariant payload was interpreted as a saved string")


def reader(raw, version=32):
    r = object.__new__(D.TaggedReader)
    r.r = NS(summary=NS(custom_versions=[NS(guid=D._EDITOR_VERSION_GUID, version=version)]))
    r.ar = io.BytesIO(raw)
    return r


def test_invariant_text_uses_saved_editor_gate_and_reaches_tagged_stream_errors():
    B.ensure_uasset_read()
    raw = payload("범주", wide=True)
    tag = NS(name="Category", type="TextProperty", size=len(raw), value_start_offset=0,
             value_end_offset=len(raw))
    assert reader(raw)._invariant_text(tag).source_string == "범주"
    assert reader(raw, 31)._invariant_text(tag) is None
    assert reader(bytes(5))._invariant_text(NS(size=5, value_start_offset=0)) is None
    for size in (0, 1, 4, len(raw) - 1):
        try:
            reader(raw)._invariant_text(NS(size=size, value_start_offset=0))
        except ValueError:
            pass
        else:
            raise AssertionError("invalid bounded None history silently fell back to the old empty text")
    broken = payload()[:-1]
    r = reader(broken)
    r.names, r.issues, r.export_name = [], [], "BP"
    r._read_tag = lambda *a, **k: NS(name="Category", type="TextProperty", size=len(broken),
                                    value_start_offset=0, value_end_offset=len(broken))
    items = r.stream(len(broken))
    assert items[0][0] == "Category" and "unreadable TextProperty" in items[0][1]
    assert r.issues[0]["stage"] == "properties" and "FString" in r.issues[0]["message"]


def test_invariant_category_display_uses_saved_declaration_and_unknown_is_visible():
    ctx = NS(issues=[])
    variable = {"fields": {"VarName": "Location", "Category": NS(source_string=""), "PropertyFlags": 0}}
    ir = {"variables": [{"name": "Location", "category": "InnerFunctions"}]}
    rows, _ = B._variables(ctx, {"NewVariables": [variable]}, {}, declarations=ir)
    assert "| InnerFunctions |" in "\n".join(rows)
    ir["variables"][0]["category"] = {"status": "unknown", "reason": "read failure"}
    rows, _ = B._variables(ctx, {"NewVariables": [variable]}, {}, declarations=ir)
    assert "| ? |" in "\n".join(rows)
