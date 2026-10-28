---
name: ue-repo-reader
description: Analyze an Unreal Engine project from a git URL — Blueprints, maps and data assets included — using the UE Repo Reader tools. Use whenever the user shares an Unreal repository link or asks about Blueprints, levels or data in such a repo.
---

# Unreal repo reader

Unreal Blueprints, maps and data assets are binary files, so the repository's text alone misses most of the
game. The UE Repo Reader tools decode them into a Markdown digest. Always build the digest first, then answer
from it — never guess what a Blueprint does from its name.

## 1. Build the digest

Call `analyze_repo` with the URL (a `/tree/<branch>` URL or `ref` selects a branch; `project` picks one
`.uproject` when the repo has several). If the result says `status: running`, call `wait_for_analysis` with
the `job_id` until it returns `status: done` — big projects take a few minutes. Keep the `digest_id`.

Digests include the output version in their identity; re-run `analyze_repo` after an upgrade to get the current layout.

## 2. Read in this order

1. `INDEX.md` (returned by `analyze_repo`; if it ends with "More: call again with offset=…", read the rest with
   `read_digest_file`). It is a bounded reading map (usually about 2–4k tokens; small projects need fewer),
   with coverage, configured entry points and PageRank priority links. Scores use saved references and
   unique-name mentions; they suggest reading order, not runtime calls, dependencies or gameplay importance.
   Follow relevant links and the incoming/outgoing context in each asset's header. `CATALOG.md` preserves
   complete project settings, maps/Blueprint/data catalogs, C++ ↔ Blueprint mapping, Enhanced Input check,
   GameplayTags, full notation and Parse report; follow continuation parts too.
2. `maps/…md` — game mode override, Level Blueprint, placed gameplay actors with per-instance overrides.
3. `blueprints/…md` — components, variables, class defaults, event dispatchers, and every graph as
   execution-flow pseudo-code (`event X`, `[true]:`, `#N = Func()`, `→ goto #N` jumps to the line labelled `[#N]`, `return <value>`, `Pin=∅` = unconnected input,
   `when auto (...)` = automatic anim transition, `⚠ disconnected` = dead code).
   `Map<K, V>` includes key/value types; `?` in a type is unspecified or unreadable, not a concrete type.
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
