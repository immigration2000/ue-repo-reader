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

## 2. Read in this order

1. `INDEX.md` (returned by `analyze_repo`; if it ends with "More: call again with offset=…", read the rest with
   `read_digest_file`). It has the project summary, maps, Blueprint catalog, data assets, the C++ ↔ Blueprint
   map, and the parse report, plus the pseudo-code legend.
2. `maps/…md` — game mode override, Level Blueprint, placed gameplay actors with per-instance overrides.
3. `blueprints/…md` — components, variables, class defaults, event dispatchers, and every graph as
   execution-flow pseudo-code (`event X`, `[true]:`, `#N = Func()`, `→ goto`, `⚠ disconnected` = dead code).
4. `data/…md` — DataTable rows, struct fields, enum values, Behavior Trees, input mappings, DataAssets.
5. `cpp/CLASSES.md`, then real C++ via `read_source_file` (a glob like `Source/**/*.h` lists files).

Use `search_digest` to find where something is used (`include_source=true` also searches C++ and config).

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
