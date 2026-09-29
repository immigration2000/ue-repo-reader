---
name: ue-repo-reader
description: Read an Unreal Engine project from a git URL or a local folder — including Blueprint logic, Level Blueprints and placed actors, DataTables, structs, enums, Behavior Trees and DataAssets decoded straight from binary .uasset files, no editor needed — and build an AI-readable digest before reviewing it. Use whenever the user shares an Unreal/UE5 repository link or project path and wants it reviewed, explained, audited, compared or navigated, or asks what a Blueprint in a repo does.
---

# UE repo reader

Unreal Blueprints are binary `.uasset` files, so reading the repo's text files alone misses most gameplay logic.
This skill turns the whole repo — C++, config, Blueprints, data assets — into Markdown you can actually read,
without launching Unreal Editor or even having the engine installed.

## 1. Build the digest

```bash
python <this-skill-dir>/scripts/ue_repo_digest.py <git-url-or-local-path> --out <dir>
```

Useful options:
- `--ref <branch|tag|sha>` — read something other than the default branch
- `--project <name|relative path>` — pick one when the repo holds several `.uproject` files (the tool warns)
- `--workdir <dir>` — where to clone (default `./.ue-repo-reader/<repo>`); an existing clone is reused
- `--lfs-max-mb 8` — only Git-LFS `.uasset` files up to this size are downloaded (Blueprints are small;
  textures and meshes are skipped on purpose)

Requirements: Python 3.10+, `git`, and `git-lfs` for LFS repos. The first run fetches the pinned
`uasset_read` parser into `~/.cache/ue-repo-reader` (override with `UE_REPO_READER_CACHE`). Private repos use
the machine's normal git credentials. Use `python3` or `py -3` if `python` is not the right interpreter.

A local path works too (e.g. the user's own checkout) — then nothing is cloned.

## 2. Read it in this order

1. `<out>/INDEX.md` — read all of it first. It has the project summary (modules, plugins, default map and
   game mode), the Blueprint catalog with parents and entry points, the C++ ↔ Blueprint map, the
   non-Blueprint logic/data assets, and the parse report. It also explains the pseudo-code notation.
2. `<out>/blueprints/<content path>.md` — one file per Blueprint: components, variables, class defaults,
   event dispatchers, and every graph rendered as execution-flow pseudo-code (anim graphs as pose trees,
   state machines as `A → B when <rule>`).
3. `<out>/maps/<content path>.md` — one file per map: game mode override, World Partition / streaming
   sub-levels, the Level Blueprint graphs, every placed gameplay actor (label, object name, class,
   location, rotation, per-instance overrides such as instance-editable variables) and an environment
   summary (meshes, lights, landscape…). World Partition external actors are merged in. Blueprint files
   end with `Placed in levels`.
4. `<out>/data/<content path>.md` — data assets: DataTables (every row), UserDefinedStructs (fields, types,
   defaults), UserDefinedEnums (values and display names), StringTables, Behavior Trees (full tree with
   decorators, services and blackboard keys), Blackboards, StateTrees (state hierarchy), EQS queries,
   input mapping contexts and actions, curves (keys), and DataAssets of project C++ types (saved values).
   Each file ends with **Used by** (Blueprints/data assets that reference it).
5. `<out>/cpp/CLASSES.md` to locate C++ types, then read the **real** C++ sources in the clone for details.

Cross-check both directions: when a Blueprint calls project C++ (`INDEX.md` lists these), read that C++;
when C++ declares a `BlueprintImplementableEvent`/`BlueprintNativeEvent`, grep `blueprints/` for the event
name to find its Blueprint implementation.

## 3. Be honest about coverage

State the limits that apply, briefly:
- Nodes that could not be decoded are flagged (`⚠ N nodes unreadable`) and listed in the parse report —
  don't guess their content.
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