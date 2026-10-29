# Saved Blueprint declaration IR

`read_blueprint(path, game_path)["summary"]["declaration_ir"]`, also available in
`digest.json` at `blueprints[path].declaration_ir`, exposes saved declarations
without parsing Markdown type labels. Schema **1**, basis `saved-tagged-properties`.

The fields are `parent_class`, `variables`, `function_graphs`, `widget_bindings`,
`saved_fields`, `status`, and `issues`. A variable has `name`, `type`, `flags`
(unsigned 64-bit decimal string), `category` (authored FText source), and
`default_value` (the declaration's authored string). A binding has `object_name`,
`property_name`, `function_name`, and `kind` (0 function / 1 property).

Each field can instead hold `{"status":"unknown","reason":"..."}`. A missing
collection tag is unknown, whereas a decoded explicitly saved zero-length array
is `[]`. Explicit empty text, zero flags, null references and binding kind 0 stay
distinct from absent tags. Non-widget `widget_bindings=null` means not applicable.
Top-level and record `saved_fields` mappings retain `saved`/`absent` tag presence;
a saved tag can still contain an unknown/unreadable value. Duplicate or missing
record identities invalidate the collection rather than dropping records.

Variable types expose `category`, `subcategory`, `object_index`, `object_path`,
`container` (0 scalar / 1 array / 2 set / 3 map), `is_reference`, `is_const`,
`is_weak_pointer`, `is_uobject_wrapper`, `serialize_single_precision`,
`member_reference` and `raw_hex`. `terminal` holds the map **value** type, including
its three flags. For a non-map declaration the terminal is not serialized and
remains unknown; its native constructor defaults are not inferred. `member_reference`
retains its parent index/path, FName and GUID in serialized byte order.
An unresolved nonzero package index is unknown; index 0 is an explicit null.

The bounded native type decoder requires the verified modern version gates:
UE4 file version at least 518, Framework custom version at least 37,
Release at least 31 and UE5 Release Stream at least 36. This is the **saved asset**
layout, independent of the project's EngineAssociation. Older/missing gates stay
unknown and preserve available raw bytes; compatibility rendering is unchanged.
Truncated payloads, invalid names/booleans/container kinds and extra bytes are
unknown instead of a partly guessed type. This adds no dependency or upstream patch.

`status=partial` also covers ordinary absent tags and non-map terminals; it does
not on its own imply a parse failure. Tagged stream failures remain in `issues`
and the asset's parse report. Read the actual reasons. `complete` describes only
this saved projection; it does not establish effective defaults or behavior.

CDO, inherited/runtime defaults, replication metadata, variable GUID identity,
widget SourcePath segments, map Level Blueprint declarations and graph-node properties are outside this projection.
The optional [native comparison](EDITOR_ORACLE.md) checks its available fields
against independently captured editor observations. Map terminal const/weak flags are compared for declarations; graph-pin terminal
flags remain outside the existing graph comparison scope. Saved/loaded differences must be investigated rather than hidden.

Serialization facts were checked in installed UE5.7/5.8 `EdGraphPin.cpp`,
`EdGraphNode.cpp`, and their headers. The implementation is independently written;
no engine implementation or newer `uasset_read` code was copied. Public API:
[FEdGraphTerminalType](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/FEdGraphTerminalType).
