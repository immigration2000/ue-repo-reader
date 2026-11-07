# P4 C++ ↔ Blueprint integration results

Date: 2026-11-07

Branch: `codex/p4-unified-analysis`

## Implemented output

Version 1.20.0 writes three additive files:

- `analysis/UNIFIED_ANALYSIS.json`: schema-versioned entities, relations, evidence, issues and lookup indexes;
- `analysis/OVERVIEW.md`: confidence counts and the status of every input IR;
- `analysis/UNRESOLVED.md`: every ambiguous or unavailable relationship with its reason.

The same structure is available as `digest.json.unified_analysis`. `relation_index.by_source` supports
C++/Blueprint forward exploration and `relation_index.by_target_or_candidate` supports reverse exploration.
Relations retain source identity, exact target or every candidate, asset/graph/node/pin identity, source file
and span where available, reference kind, provenance, resolution status, evidence and issues.

`scripts/unified_analysis.py` implements:

- `build_unified_analysis`: additive synthesis and partial-input propagation;
- `_semantic_reference_relation`: exact `/Script` owner plus member candidate construction without short-name
  promotion;
- `_blueprint_graph_relations`: saved execution/data pin topology and unresolved target preservation;
- `_cpp_relations`: base, call, lexical variable access, `override`, and Unreal `_Implementation/_Validate`
  candidates;
- `_bp_inputs_outputs`: graph entry/output projection and conservative return-value candidates;
- `overview_markdown` and `unresolved_markdown`: bounded human-readable reports.

`scripts/ue_repo_digest.py` creates the new directory, embeds the schema, and raises the output version to
1.20.0. `scripts/navigation.py`, both skill guides, README, and MCP instructions point readers to the new layer
and state that compiler/UHT identity is still required for verified cross-language targets.

## Relationship counts on pinned projects

These are final-regression observations, not universal accuracy scores.

| Pinned fixture | All relations: verified / candidate / ambiguous / unavailable | C++ ↔ Blueprint: verified / candidate / ambiguous / unavailable | Unified status |
|---|---:|---:|---:|
| ExtractionGame `f7335ad` | 3,699 / 360 / 0 / 848 | 0 / 0 / 0 / 542 | partial |
| ActionRoguelike `31bd384` | 2,522 / 1,156 / 158 / 4,333 | 0 / 89 / 7 / 449 | partial |
| Character Input `bc6badd` | 0 / 12 / 1 / 67 | 0 / 1 / 0 / 6 | partial |
| BattleTank `19ffc19` | 0 / 115 / 14 / 423 | 0 / 7 / 0 / 17 | partial |
| Total | 6,221 / 1,643 / 173 / 5,671 | 0 / 97 / 7 / 1,014 | partial |

The 6,221 `verified` relations are exact saved Blueprint pin source/target identities or exact saved
MacroGraph object paths within graph IR. They are not independently editor-verified runtime calls. The verified
C++ ↔ Blueprint count is deliberately zero.
ExtractionGame contains no project C++ at its pinned commit, so its Blueprint-only success is not counted as
cross-language validation. ActionRoguelike contains both C++ and Blueprint and supplies the main fixed-project
integration observation; its P3 syntax input remains partial in seven files and P2 native semantic validation
remains unavailable.

## Added counterexamples

`tests/unified_analysis_tests.py` adds four independent assertion groups covering:

- same-named overloads and wrong GUIDs without false verification;
- duplicate C++ class names and duplicate Blueprint graph names without collapse;
- missing references and incomplete P2/P3 input propagation;
- exact saved pin flow and MacroGraph object paths separated from inferred runtime order;
- same-asset Blueprint function candidates, including duplicate graph names;
- saved/loaded mismatch propagation;
- Blueprint variable use candidates;
- inheritance, `override`, BlueprintNativeEvent `_Implementation`, interface calls and runtime uncertainty;
- function inputs/outputs with a return-value name retained as a candidate rather than a proven role.

The real CLI rerun test also requires all three analysis files and byte-equivalent embedded/file JSON.

## Test results

| Command/check | Result |
|---|---|
| Integrated P2/P3 baseline full regression | PASS: 169 unit tests, external assets, native/evidence checks, four projects |
| Final `tests/regress.py` with pinned local checkouts | PASS: 173 unit tests, 6 external assets, 8 existing Native Oracle groups, 2 evidence checks, 4 projects |
| Direct P4 synthetic tests and Python compilation | PASS |
| ActionRoguelike 5.8 digest with both C++ and Blueprint | PASS; 8,169 relations, counts above |
| Real MCP HTTP smoke | PASS: 6 tools, response bounds, warm/restart/refresh, strict/opt-in cache separation |
| UE 5.7/5.8 P2 plugin build and new semantic capture | NOT RUN: Unreal Engine/toolchain unavailable in this Linux task |
| Clang AST/UHT semantic comparison | NOT RUN: no matching compile database, generated headers or engine toolchain |

One standalone unit-test invocation initially failed before product tests completed because
`UE_REPO_READER_CACHE` was omitted and the managed environment made `/home/agent/.cache` read-only. Re-running
with `/workspace/shared/ue-repo-reader-cache` passed all 173 tests. This was an environment invocation failure;
no expectation or product code was changed to hide it.

Existing `tests/fixtures.json`, `tests/asset_fixtures.json`, original packages, eight editor Oracle JSON files,
and three independent evidence JSON files have no working-tree changes.
