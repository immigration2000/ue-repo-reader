---
name: ue-repo-reader
description: Read an Unreal Engine project from a git URL or a local folder — including Blueprint logic, Level Blueprints and placed actors, DataTables, structs, enums, Behavior Trees and DataAssets decoded straight from binary .uasset files, no editor needed — and build an AI-readable digest before reviewing it. Use whenever the user shares an Unreal/UE5 repository link or project path and wants it reviewed, explained, audited, compared or navigated, or asks what a Blueprint in a repo does.
---

# UE repo reader

Unreal Blueprints are binary `.uasset` files, so reading the repo's text files alone misses most gameplay logic.
This skill turns the whole repo — C++, config, Blueprints, data assets — into Markdown you can actually read,
without launching Unreal Editor or even having the engine installed.

## 1. Build the digest

Resolve `<this-skill-dir>` to the directory containing this `SKILL.md`, regardless of whether it is under
`.agents/skills/`, `.claude/skills/` or `.github/skills/`. Keep the bundled `scripts/` beside it and quote
the script path when it contains spaces. Run from the user's work directory so clones and output stay there.

```bash
python "<this-skill-dir>/scripts/ue_repo_digest.py" <git-url-or-local-path> --out <dir>
```

Useful options:
- `--ref <branch|tag|sha>` — read something other than the default branch
- `--project <name|relative path>` — pick one when the repo holds several `.uproject` files (the tool warns)
- `--workdir <dir>` — where to clone (default `./.ue-repo-reader/<repo>`); an existing clone is reused
- `--asset-cache-dir <dir>` — persistent clean asset results (default: parser cache folder); changed bytes,
  decoder/tool versions and map external actors invalidate entries. `--no-asset-cache` forces fresh decoding.
- `--lfs-max-mb 8` — only Git-LFS `.uasset` files up to this size are downloaded (Blueprints are small;
  textures and meshes are skipped on purpose)

Requirements: Python 3.10+, `git`, and `git-lfs` for LFS repos. The first run fetches the pinned
`uasset_read` parser into `~/.cache/ue-repo-reader` (override with `UE_REPO_READER_CACHE`). Private repos use
the machine's normal git credentials. Use `python3` or `py -3` if `python` is not the right interpreter.

A local path works too (e.g. the user's own checkout) — then nothing is cloned.

Use a dedicated `--out` directory. It can be new, empty, or a recognized ue-repo-reader digest; an existing
digest is replaced, including its generated `blueprints/`, `data/`, `maps/`, `cpp/` and `config/` folders.
The input repository, its ancestors, symlinks/junctions, and output directories with unrelated top-level
entries are rejected. If an incomplete run left an unrecognized output, choose a new `--out` directory.

## 2. Read it in this order

1. `<out>/INDEX.md` — read all of it first: bounded reading map (usually about 2–4k tokens; fewer for small
   projects), coverage/limits, configured entry points and PageRank priority links. Ranks use saved references
   and unique-name mentions, with configured-entry seeds; they suggest reading order, not runtime behavior
   or proven dependencies. Follow the links relevant to the question. Each asset starts with context links.
   `<out>/CATALOG.md` preserves the complete project settings, map/Blueprint/data catalogs, C++ ↔ Blueprint
   mapping, Enhanced Input check, GameplayTag summary, full pseudo-code legend and Parse report.
2. `<out>/blueprints/<content path>.md` — one file per Blueprint: components, widget tree (non-default widget
   properties and `[slot …]` layout), property bindings, widget animations, timelines (length, tracks, curve keys), variables, class defaults,
   event dispatchers, and every graph rendered as execution-flow pseudo-code (anim graphs as pose trees,
   state machines as `A → B when <rule>`, `when auto (...)` = automatic transition; functions show
   `-> Out: T` and `return <value>`; `Pin=∅` = object input left unconnected; `$N` = shared pure expression, see the graph's `// where` block).
   `Map<K, V>` includes key/value types; `?` in a type means unspecified in the saved declaration or unreadable.
   `// Function metadata` and `// Function tooltip` comments show saved Category, CallInEditor and ToolTip
   from the function entry. They describe the function; missing fields are not inferred and explicit false is kept.
3. `<out>/maps/<content path>.md` — one file per map: game mode override, World Partition / streaming
   sub-levels, the Level Blueprint graphs, every placed gameplay actor (label, object name, class,
   location, rotation, per-instance overrides such as instance-editable variables) and an environment
   summary (meshes, lights, landscape…). World Partition external actors are merged in. Blueprint files
   end with `Placed in levels`. Map tables are compact previews (up to eight overrides, shortened values).
   Scripts can obtain complete decoded actor/root-component saved properties from
   `digest.json` → `maps_detail[map_path].actors`: source package/export index identify each actor;
   native values retain their fields, opaque bytes use base64, and unavailable values stay explicitly unknown.
   Check each record's `properties_status`: `partial` means an incomplete read/conversion; absent properties are unknown, not defaults.
   Other component exports and unsaved class defaults are not expanded into these records.
4. `<out>/data/<content path>.md` — data assets: DataTables (every row), UserDefinedStructs (fields, types,
   defaults), UserDefinedEnums (values and display names), StringTables, Behavior Trees (full tree with
   decorators, services and blackboard keys), Blackboards, StateTrees (state hierarchy), EQS queries,
   input mapping contexts and input actions (value type, triggers, modifiers with settings), anim montages (slots, sections, notifies by time), curves (keys), and DataAssets of project C++ types (saved values).
   Each file ends with **Used by** (Blueprints/data assets that reference it).
   Arrays with explicit enum type metadata use `Enum::Enumerator(number, display="Label")`, resolved from
   this project's decoded UserDefinedEnums. Serialized names/numbers are preserved; numeric values for saved
   names come from that enum's value table. An unresolved name/number means an unknown value or a missing/
   ambiguous enum; ordinary byte arrays remain numeric.
5. `<out>/config/GameplayTags.md` (when the project uses tags) — every tag, where it is defined (ini, tag
   DataTable or native C++), who uses it, tags used but never defined, redirects.
6. `<out>/cpp/CLASSES.md` to locate C++ types, then read the **real** C++ sources in the clone for details.

Skip `digest.json` (a machine-readable copy of the same facts). A file that ends with
`→ continued in X.part2.md` is split; read the parts in order.

Read each document's **Parse warnings**, the INDEX coverage summary and the CATALOG Parse report. Property, graph-rendering, Level Blueprint,
and external-actor failures are reported even when all graph nodes have decoded pins. An unreadable Level
Blueprint is **unknown**, not an empty graph; missing values after a parse failure are not confirmed defaults.

Cross-check both directions: when a Blueprint calls project C++ (`CATALOG.md` lists these), read that C++;
when C++ declares a `BlueprintImplementableEvent`/`BlueprintNativeEvent`, grep `blueprints/` for the event
name to find its Blueprint implementation.

## 3. Be honest about coverage

State the limits that apply, briefly:
- Nodes that could not be decoded are flagged (`⚠ N nodes unreadable`) and listed in the parse report —
  don't guess their content.
- `Parse warnings` means part of the asset could not be read or rendered. Quote those limits even if node
  coverage is N/N; a map can have unreadable properties, a failed Level Blueprint or missing external actors.
- LFS files that were skipped or failed to download are listed in the parse report; if Blueprints are
  missing because of that, say so and suggest re-running where LFS access works.
- The digest is a static read of saved assets. It cannot show runtime values, and node names are internal
  function names (`K2_GetActorLocation`), not always the editor's display titles.
- Only the chosen `.uproject` is covered when a repo has several.
- Map actor locations are the root component's relative location (world location unless attached).
  Materials, Niagara, MetaSounds, animations, meshes and textures are counted, not read.
- Data assets show only values saved in the asset; a missing field means the class/struct default.
  StateTree task and condition instances are not decoded (the state hierarchy and the Blueprints the tree
  references are). "Used by" is found by name references, not by C++/config lookups.

## 4. Blueprint review checklist

When asked to review, look for these in the rendered graphs:
- work on `event Tick` that could be event-driven or timer-based; `GetAllActorsOfClass`, casts or
  `GetComponentByClass` inside Tick or loops
- missing `IsValid` before using references that can be destroyed; cast results used without `[cast ok]`
- `⚠ disconnected execution chains` (dead code) and `unused (empty) events`
- hard-coded numbers that belong in variables, DataAssets or DataTables (and, the other way, DataTable
  rows or DataAsset values that look inconsistent — compare them side by side in `data/`)
- logic duplicated between Blueprints, or heavy Blueprint logic that belongs in the C++ parent
- level logic: Level Blueprints doing gameplay work that belongs in actors/GameMode; hard references to
  placed actors; placed instances whose overrides differ unexpectedly (compare rows in `maps/`)
- replication: `Replicated`/`RepNotify` flags on variables, `RunOnServer`/`Multicast` custom events, work
  that should be gated by `Switch Has Authority`
- delegates bound (`+=`) without a matching unbind, timers never cleared

Quote the relevant pseudo-code lines and the Blueprint path when you report a finding.

## Troubleshooting

- **"LFS error … access denied / authentication"**: the environment can't fetch that repo's LFS objects.
  Run where the user's git credentials work (their own machine), or pass a local checkout path.
- **Blueprint failed / timed out**: listed in the parse report; the rest of the digest is still valid.
  Re-run with a larger `--timeout` if many time out.
- **Engine version**: tested on assets saved by UE 4.25 through 5.8.3 (UE 5.8 changed FText serialization;
  handled automatically from each file's saved-by engine version). Newer engines are probed; per-file node
  counts show exactly how much decoded.
