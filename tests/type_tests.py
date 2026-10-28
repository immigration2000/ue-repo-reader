"""Pin/declaration types: missing terminal types are unknown, never an invented concrete type."""
import struct
from types import SimpleNamespace as NS

import bp_reader as B
import data_reader as D


class Context:
    names = ["None", "byte", "real", "double", "struct", "object", "int", "string"]
    objects = {-1: "E_Crates", -2: "RuntimeItem", -3: "Actor"}
    def __init__(self):
        self.issues = []
    def fname(self, index, number):
        return self.names[index]
    def obj_name(self, index):
        return self.objects.get(index, "")


def declaration(category, obj=0, container=0, value=(0, 0, 0)):
    raw = struct.pack("<iiiiiB", category, 0, 0, 0, obj, container)
    if container == 3:
        cat, sub, ref = value
        raw += struct.pack("<iiiii", cat, 0, sub, 0, ref)
    return raw


def test_map_declaration_value_types_and_unknown():
    ctx = Context()
    for value, expected in (((6, 0, 0), "int"), ((2, 3, 0), "double"), ((4, 0, -2), "RuntimeItem"),
                            ((5, 0, -3), "Actor*"), ((0, 0, 0), "?")):
        assert B._decode_var_type(ctx, declaration(1, -1, 3, value)) == f"Map<E_Crates, {expected}>"
    assert not ctx.issues, "an explicitly unset type was treated as a parser failure"
    assert B._decode_var_type(ctx, declaration(1, -1, 1)) == "Array<E_Crates>"
    assert B._decode_var_type(ctx, declaration(4, -2, 2)) == "Set<RuntimeItem>"
    assert B._decode_var_type(ctx, declaration(7)) == "String"
    truncated = declaration(1, -1, 3)[:28]
    assert B._decode_var_type(ctx, truncated, "NewVar") == "?"
    assert ctx.issues[0]["stage"] == "variable_type" and ctx.issues[0]["context"] == "NewVar"


def test_map_graph_and_struct_descriptor_value_types():
    for category, sub, obj, expected in (("int", "", None, "int"), ("struct", "", "RuntimeItem", "RuntimeItem"),
                                         ("object", "", "Actor", "Actor*"), ("real", "double", None, "double"),
                                         ("None", "None", None, "?")):
        pt = NS(pin_category="byte", pin_subcategory="", pin_subcategory_object_name="E_Crates", container_type=3,
                map_key_terminal_category=category, map_key_terminal_sub_category=sub,
                map_key_terminal_sub_category_object_name=obj)
        assert B.pin_type_str(NS(pin_type=pt)) == f"Map<E_Crates, {expected}>"
        desc = {"Category": "byte", "SubCategoryObject": "E_Crates", "ContainerType": "Map",
                "PinValueType": {"fields": {"TerminalCategory": category, "TerminalSubCategory": sub,
                                           "TerminalSubCategoryObject": obj}}}
        assert D._pin_type_from_desc(Context(), desc) == f"Map<E_Crates, {expected}>"
    assert B.pin_type_str(NS(pin_type=None)) == "?"


def test_map_unset_type_note_with_and_without_tooltip():
    ctx = Context()
    fields = {"VarName": "NewVar", "VarType": {"raw_data": declaration(1, -1, 3)}}
    for metadata in ({}, {"NewVar": {"tooltip": "Map used later"}}):
        rows, names = B._variables(ctx, {"NewVariables": [{"fields": fields}]}, {}, metadata)
        text = "\n".join(rows)
        assert names == {"NewVar"} and "Map<E_Crates, ?>" in text and "unspecified" in text
        assert "Map<E_Crates, None>" not in text
