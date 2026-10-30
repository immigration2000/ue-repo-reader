# Saved graph projection, schema 1

`read_blueprint` returns this structure as `summary.graph_ir`. Repository digests put it at
`blueprints[asset_path].graph_ir`; maps retain their Level Blueprint at
`maps_detail[map_path].level_bp_graph_ir` (null when that read failed).

This is the first W3/W1 comparison foundation. It preserves nonempty graphs found by the
parser, node identity/class, decoded pin types/defaults and structural pin references.
It does **not** contain node properties such as function member references, class defaults,
empty graphs, a complete execution model, or runtime values. Reroutes remain explicit nodes.

| Field | Contract |
|---|---|
| `schema_version` | Currently 1; incompatible changes require a new schema. |
| `asset_path` | Requested mounted asset path. Saved object paths can retain a different package location. |
| `scope`, `identity_scope`, `coverage_basis` | Explicit boundaries: decoder-exposed fields only, IDs local to this package snapshot, node counts unable to prove pin completeness. |
| `status` | `complete` means no reported gaps in the decoder-exposed projection and all counted nodes decoded. It is not a semantic accuracy score, independent verification or proof that all serialized pins decoded. `partial` requires checking issues and node coverage. |
| `nodes_decoded`, `nodes_total` | Existing parser coverage counts, excluding comment nodes; they are not pin counts or correctness scores. |
| `nodes_represented` | Non-comment node identities retained, deduplicated by valid export index or local model-object identity. Missing export identity is separately reported. A count mismatch produces an issue even at parser N/N. |
| `graphs` | Graph path/name, uninterpreted `guid_raw`, and nodes; same-name graphs retain their owning paths where available. |
| `issues` | Projection problems, also propagated to Blueprint Parse warnings and a map's Level Blueprint warnings. |

A node counts as decoded when at least one pin decoded. Truncated pin lists inside the
decoder cannot be detected from this count; compare an independent oracle for pin completeness.

Node records preserve `object_path`, `object_name`, positive `export_index`, `class`,
uninterpreted `guid_raw` and pins. IDs use the owning graph path and export index.
Missing export identities use an explicitly reported local ordinal. Export indices can change
after a save; these IDs must not be treated as persistent keys across commits. Duplicate node
or pin identities retain separate records rather than overwriting them.

Pin records preserve serialization `index`, serialized `guid`, direction, decoded type fields,
defaults and display/connectability flags exposed by the pinned parser. Map terminal fields
retain that parser's `map_key_terminal_*` names; they actually describe the **value** terminal.
`defaults` preserves available decoded `default_value`, `auto_default_value`, `default_object`
and `default_text_value` independently. None, empty text, zero and false are not conflated.
`default_object_path` retains a resolved object's full path (or explicit unknown when the index/object is unavailable).
Null means no resolved decoded object default, not proof of an effective inherited/runtime default.
Missing fields on a decoder model produce unknown records and issues instead of disappearing.
This does not establish whether a parser default was explicitly serialized or is an effective
inherited/runtime default. Object indices are package-local; FText records currently retain
decoded source text, not full localization identity.

`pin_guid_encoding` is `serialized-byte-order-hex`. Unreal's four-word display GUID must be
converted word by word before comparison; merely stripping punctuation is insufficient.
Graph/node GUID metadata is not normalized or used as a resolved pin identity.
The `guid` field retains the decoder's original spelling; the GUID embedded in each pin ID is normalized.

Every `linked_to_raw`, `sub_pins`, `parent_pin` and `ref_pass_through` reference carries:

- `reference`: decoded owner name/pin GUID and extra scalar keys. The known linker object
  `owning_node_object` is represented by its object path or explicit unknown; other object internals are outside scope.
- `status`: `resolved`, `unresolved` or `ambiguous`.
- `target`: a pin ID only when exactly one candidate matches within that graph.
- `candidates`: all matching IDs when ambiguous; the target stays null.
- `owner_path`: derived full path, null when no decoded owner object exists, or explicit unknown when unavailable;
  this is outside `reference` so it cannot overwrite a decoded field of the same name.
- `basis`: `saved_owner_path`, `saved_owner_name`, `same_node_structural`, `unavailable` or `unavailable_owner_path`.

A known owning object path takes precedence over its short name. The pinned decoder can expose it
as `owning_node_object` when a linker is available. Parent/subpin/pass-through references without
an owner use only that node's own pins, with `basis: same_node_structural`; arbitrary `linked_to_raw`
references never use this convention. A missing link owner, absent target or duplicate identity is
never repaired by guessing from a globally unique pin GUID. Extra decoded reference fields are
retained as scalars or explicitly marked unknown; they are not silently discarded.
`unavailable_owner_path` intentionally suppresses name lookup and the local structural convention
when a decoded owner object exists but its full path cannot be established.
Reciprocal link observations remain separate. These are saved structural links, not proof
that an execution path runs. Non-finite or unsupported scalar values become an explicit
unknown record and an issue instead of invalid JSON or invented text.

The asset-result cache fingerprint includes `graph_ir.py` and `declaration_ir.py`. Output versions invalidate server
and asset caches; changing only the projection module must also invalidate asset results.

## Current verification

The pinned independent UE 5.7/5.8 pin-text fixtures compare object path, pin index, GUID and
source text in this public projection as well as the parser/Markdown. Mutation checks reject
incorrect IR text even when parser/Markdown text is correct. Synthetic cases cover owner-scoped
shared GUIDs, ambiguous/missing/cross-graph references, duplicate identities, full literal text,
type/default/link mutations and structural pin references.

Q1 now also replays source-pinned native UE 5.7.4/5.8.4 captures against the full collected
node/pin names, directions, types, defaults, flags and saved links. The two pin fixtures have
9 nodes/59 pins each; eg BFL_Util adds 39 nodes/109 pins/82 nonempty reciprocal link observations.
Native source text, object paths and exact owner/GUID identities are compared independently of Markdown.
Available function tooltip/category fields also compare; absent metadata remains explicitly unknown
(3/3/11 exact metadata gaps; plus one absent NewVariables tag in each original fixture), rather than becoming inferred empty/false values. Four additional eg captures exercise structured
variable declarations through [declaration_ir](DECLARATION_IR.md); Q14 adds BP_Knife and its scalar text category,
bringing the native replay set to eight.
See [the editor oracle workflow](EDITOR_ORACLE.md) for profiles, package hashes and exclusions.

Runtime execution, function member-reference semantics, arbitrary node properties and effective
CDO/inherited defaults remain outside this verification. A native loaded graph can also differ
from saved bytes after engine load fixups; differences need investigation before blaming the reader.
Existing older-version fixtures retain their checks for compatibility; no new legacy project expansion is claimed.

## Saved membership and unlisted exports (1.17.0)

Schema 1 gains the additive `saved_membership` list and machine-readable `membership_basis` description.
Each nonempty decoded view reports its exact graph path and
`status=confirmed` with `saved_node_exports` / `unlisted_node_exports`, or `status=unknown` with a reason.
The reader locates the exact graph export and Nodes tag, validates the object-array type, tag/export bounds,
and the raw int32 count plus package-index payload. A tolerant decoder's empty list is never sufficient.
An explicit bounded zero count is valid; an absent/invalid/unresolved array causes no removal.
Unknown membership keeps the earlier decoded view and is noted in Markdown. Actual source corruption and
property-reader failures also reach the parse report. `complete` remains pin projection coverage, not a
promise that every saved membership could be established; read this list separately.
This new source-array validation covers UE5-saved packages. UE4-saved packages retain the earlier decoded
view with an explicit out-of-scope reason; this does not expand legacy format support.

The pinned parser groups additional node exports by Outer. When an export is proven absent from Nodes,
normal graph rendering/graph-only node coverage excludes it; its full decoded node/pin IR is preserved under
`blueprints[path].unlisted_graph_nodes` (maps: `maps_detail[path].level_bp_unlisted_graph_nodes`).
An absent side projection means no confirmed unlisted exports were identified, not independently verified
absence when membership is unknown. Raw references remain present: links across this projection boundary
stay unresolved with their saved owner/GUID, rather than becoming inferred active graph edges.

A separately saved `EntryNode` pointer may name an unlisted export. `entry_node_export` and
`entry_node_listed=false` retain that conflict, and Markdown warns that an entry rendered from listed-node
links is not a runtime entry guarantee. The saved pointer and package bytes are not rewritten.

Both eg ABP_Hands and ar GideonManny contain one such decoded unlisted entry export. Their graph-only
coverage decreases by one (eg1779→1778; ar1271→1270); the source exports remain available separately.
See [Q14 evidence](dev/Q14-LOADED-STATE-2026-10-30.md) for raw array spans and native observations.
