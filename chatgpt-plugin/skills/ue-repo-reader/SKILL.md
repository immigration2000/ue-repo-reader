---
name: ue-repo-reader
description: Analyze an Unreal Engine project from a git URL — Blueprints, maps and data assets included — using the UE Repo Reader tools. Use whenever the user shares an Unreal repository link or asks about Blueprints, levels or data in such a repo.
---

# Unreal repo reader

Unreal Blueprints, maps and data assets are binary files, so the repository's text alone misses most of the
game. The UE Repo Reader tools decode them into a Markdown digest. Always build the digest first, then answer
from it — never guess what a Blueprint does from its name.

## 1. Build the digest

Project target is **UE 5.7+**; normal analysis currently accepts numeric 5.7/5.8 declarations in the
selected `.uproject`. Older projects, unknown build IDs/missing descriptors and newer-than-tested
declarations are refused by default. A target project can contain older-saved assets; package
compatibility is separate. Never infer the project version from its asset headers.
Unreadable UTF-8 JSON, non-object descriptors, invalid constants or duplicate fields (including nested
metadata) are unconfirmed under the tool's strict metadata policy.

Call `analyze_repo` with the URL (a `/tree/<branch>` URL or `ref` selects a branch; `project` picks one
`.uproject` when the repo has several). If the result says `status: running`, call `wait_for_analysis` with
the `job_id` until it returns `status: done` — big projects take a few minutes. Keep the `digest_id`.

Digests include the output version in their identity; re-run `analyze_repo` after an upgrade to get the current layout.
`analyze_repo(..., best_effort=true)` explicitly enables exploratory analysis outside the normal window
when the user requests it. The support classification stays below-minimum/unconfirmed/unverified;
do not treat a successful parse as support confirmation. Mode is part of the cache identity.

## 2. Read in this order

1. `INDEX.md` (returned by `analyze_repo`; if it ends with "More: call again with offset=…", read the rest with
   `read_digest_file`). It is a bounded reading map (usually about 2–4k tokens; small projects need fewer),
   with coverage, configured entry points and PageRank priority links. Scores use saved references and
   unique-name mentions; they suggest reading order, not runtime calls, dependencies or gameplay importance.
   Follow relevant links and the incoming/outgoing context in each asset's header. `CATALOG.md` preserves
   complete project settings, maps/Blueprint/data catalogs, C++ ↔ Blueprint mapping, Enhanced Input check,
   GameplayTags, full notation and Parse report; follow continuation parts too.
   Read the prominent **Project support** notice as well as decode coverage before drawing conclusions.
   An independent editor comparison is a separate optional developer workflow (`docs/EDITOR_ORACLE.md`
   in the source repo), outside these MCP tools. A reported match covers its selected profile and saved
   observations; retain unavailable fields and exclusions instead of presenting a gameplay accuracy score.
2. `maps/…md` — game mode override, Level Blueprint, placed gameplay actors with per-instance overrides.
   Tables are compact previews. Complete decoded actor/root-component saved properties are retained for
   scripts in `digest.json` → `maps_detail[map_path].actors`, with source package/export index identities.
   Native fields/opaque bytes are preserved; unavailable values stay unknown, and other component exports/class defaults are not expanded.
   Check each record's `properties_status`: `partial` means incomplete; absent properties are unknown, not defaults.
3. `blueprints/…md` — components, variables, class defaults, event dispatchers, and every graph as
   execution-flow pseudo-code (`event X`, `[true]:`, `#N = Func()`, `→ goto #N` jumps to the line labelled `[#N]`, `return <value>`, `Pin=∅` = unconnected input,
   `when auto (...)` = automatic anim transition, `⚠ disconnected` = dead code).
   `Map<K, V>` includes key/value types; `?` in a type is unspecified or unreadable, not a concrete type.
   `// Function metadata` / `// Function tooltip` show saved entry-node Category, CallInEditor and ToolTip.
   These are descriptions; absent fields are not inferred and explicit false is retained.
   Compact values use `…(+N)` for omitted entries/fields; plain `…` can also mean a string/depth limit.
   Extra class defaults show at most 40 values and report further values, opaque/native data and unexpanded subobjects.
   Omitted values are unknown here, not confirmed defaults. A display notice alone is not a parse failure,
   and complete BP/data saved values are not yet retained elsewhere; inspect the asset for missing detail.
   Machine comparisons can use `digest.json` → `blueprints[path].graph_ir` (maps: `maps_detail[path].level_bp_graph_ir`).
   It retains nonempty parsed graphs, node identity/class, pin types/defaults and saved references, with status/issues.
   `complete` covers decoder-exposed pins, not verified gameplay semantics or detection of truncated pin lists. IDs belong to this asset snapshot;
   unresolved/ambiguous links have no inferred target. Node properties/CDOs are outside the IR. Prefer Markdown
   for normal analysis and avoid loading the entire JSON into context.
4. `data/…md` — DataTable rows, struct fields, enum values, Behavior Trees, input mappings, DataAssets.
   Typed enum arrays show `Enum::Enumerator(number, display="Label")` using this project's UserDefinedEnums.
   Saved names/numbers are preserved; integers for serialized names come from that enum's value table.
   Unresolved names/numbers flag missing/ambiguous enums or unknown values.
5. `cpp/CLASSES.md`, then real C++ via `read_source_file` (a glob like `Source/**/*.h` lists files).

Read **Parse warnings** in each document, INDEX coverage and the CATALOG Parse report. Property/graph-render/Level Blueprint/
external-actor failures can occur with N/N node coverage. An unreadable Level Blueprint is unknown, not empty;
values missing after a parse failure are not confirmed class defaults.

Use `search_digest` to find where something is used (`include_source=true` also searches C++ and config).
Search is a case-insensitive literal substring, including punctuation and short names; do not send FTS or regex syntax.
Use 1–256 characters and at most 100 results. Repeated queries reuse a persistent index. If a search reports
omitted files or a coverage limit, state that limit and use the list/read tools for the missing material.

Tool text responses are capped at 20,000 characters. Follow returned offsets: read tools use character offsets,
while file lists/globs use item offsets (up to 200 entries per call). Narrow the query/folder when a response is
truncated. Large files are streamed in pages; do not treat a first page or an empty search as complete coverage.

The saved declaration projection is `digest.json` → `blueprints[path].declaration_ir` (schema 1). Use it for structured variable types/flags/authored defaults, parent and function graph references, and widget bindings. Check `saved_fields`, `status` and unknown reasons: absent tags, non-map terminal types and unsupported older saved layouts remain unknown; CDO, inherited/runtime defaults and map Level Blueprint declarations are outside this projection. Display text is not a substitute for these fields.

Graph membership: check `graph_ir.saved_membership` and `membership_basis`. For UE5-saved packages, a fully validated saved `Nodes` array overrides Outer-based grouping; confirmed unlisted exports are kept separately in `blueprints[path].unlisted_graph_nodes` / `maps_detail[path].level_bp_unlisted_graph_nodes` and excluded from graph rendering and graph-node coverage. Unknown membership keeps the decoded view with a reason; UE4-saved packages retain their legacy view without new membership validation. A saved `EntryNode` pointing outside the array is reported; rendered listed-node links do not establish runtime entry.

Scalar tagged culture-invariant `FText` source strings are decoded from their bounded payload. Unreadable text is unknown, and noncanonical narrow encodings are not assigned a guessed codepage. Text inside arrays/maps/sets still uses the earlier collection path: a blank collection text is not verified absence (follow-up Q18).

## 3. Answer well

- Quote the Blueprint/asset path and the relevant pseudo-code lines for every claim.
- State coverage from the Parse report; never guess content of nodes marked unreadable or assets not
  downloaded. Node names are internal function names (e.g. `K2_GetActorLocation`).
- Given only a URL, give an overview: what the project is, core systems and how C++, Blueprints and data
  connect, entry points (default map, GameMode, input), notable issues, and what could not be decoded.
- For reviews check: work on Tick that could be event-driven; casts/GetAllActorsOfClass/GetComponentByClass in
  Tick or loops; missing IsValid; dead code; hard-coded values that belong in data; heavy Blueprint logic that
  belongs in the C++ parent; replication flags and RPC events; delegates bound without unbinding.
- Answer in the user's language.
