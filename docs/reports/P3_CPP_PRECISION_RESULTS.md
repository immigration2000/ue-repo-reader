# P3 C++ precision results

Date: 2026-11-07

Branch: `codex/p3-cpp-precision`

Base: `dcb99dc`

## Implemented result

The compatible `cpp.modules`, `cpp.classes`, and `cpp/CLASSES.md` fields remain present. A new independent
`cpp.precision` schema and `cpp/CXX_INDEX.json` preserve source-faithful C++ syntax observations. The digest
also writes:

- `cpp/FUNCTIONS.md`: function declarations/definitions, original signatures, bodies, Unreal annotations,
  source files and line ranges.
- `cpp/CALL_GRAPH.md`: caller and callee expressions, source locations, and zero/one/many spelling candidates.
- `cpp/UNRESOLVED.md`: parser gaps, unevaluated preprocessor directives, and every unresolved call target.

`scripts/cxx_index.py` scans headers, implementations, and inline files under project and plugin Source roots.
It records ordinary and Unreal classes/structs/enums, namespaces, bases, member access, functions, data members,
function bodies, calls, if/switch/loops/returns, assignments/reads, lambdas, generated-header includes, and
preprocessor boundaries. It lexically records module dependencies and target type from Build.cs/Target.cs
without claiming that UBT ran.

UCLASS/USTRUCT/UENUM/UINTERFACE/UFUNCTION/UPROPERTY and GENERATED_BODY calls are preserved as exact source
observations. Their byte ranges, plus `*_API` tokens, are space-masked in a same-length parser buffer so the
C++ grammar can recover the surrounding declaration without changing original offsets.

Declaration/definition links use qualified spelling and normalized parameter syntax. `_Implementation` and
`_Validate` links use owner plus base name. Both link types say `syntax_observed` only when there is one source
candidate and explicitly state that type equivalence, generated declarations, and UnrealHeaderTool behavior
were not checked. Calls always remain target-`unresolved`, including unique candidates.

## Compatibility and dependency behavior

The output version is 1.19.0. The prior reflected-surface fields were not deleted or renamed. The parser pins
are in `requirements-cxx.txt`, and snapshot skill installation now copies that file and `cxx_index.py`.

If the optional packages are absent or binary-incompatible, normal analysis continues. `CLASSES.md` and legacy
fields remain available; the precision schema has status `unavailable`, an explicit parser issue, empty syntax
collections, and Markdown explaining the missing result. Regex output is never relabeled as precision output.

## Added tests

`tests/cxx_index_tests.py` uses temporary hand-authored source and independent assertions for:

- ordinary functions and a multiline UFUNCTION;
- UCLASS/UPROPERTY, generated header/body, base, RPC/BlueprintNativeEvent and `_Implementation` candidate;
- namespaces, templates, overloads, duplicate function names and explicit qualification;
- if/while/return, lambdas, assignments, reads, nested calls and source spans;
- `WITH_EDITOR` recorded without evaluating its truth;
- incomplete source retained as `partial`;
- deliberately unavailable parser retained as `unavailable`;
- Build.cs dependencies and Target.cs target type as lexical observations;
- all four new precision output documents and the additive digest shape.

Tests do not serialize parser output as their expected answer. Existing fixtures, source packages, and editor
Oracle JSON were not edited.

## Test results

Final command results:

- Baseline `dcb99dc`, detached worktree, `python tests/regress.py` with the same pinned local source clones:
  158/158 unit tests, 6/6 external asset cases, 8 Native Oracle groups, 2 saved/loaded evidence checks, and
  4/4 fixed projects passed.
- Final `python tests/regress.py`: 162/162 unit tests, 6/6 external asset cases, the same 8 Native Oracle
  groups and 2 evidence checks, and 4/4 fixed projects passed. BP/node/issue expectations were not relaxed.
- Final MCP HTTP smoke: 6 tools passed, including response bounds and warm/restart/refresh plus strict/opt-in
  cache separation.
- A first final-regression attempt refused a previously materialized `eg` cache as locally changed before
  analysis. That cache was preserved under an ignored path; a fresh pinned clone passed `eg`, and the later
  complete final run passed without product or expectation changes.
- Unreal Editor/UnrealHeaderTool compilation: not run; no engine is installed or required in this Linux task.
- Clang AST comparison: not run; no UE compile database or generated headers were available.

Precision-index observations on the fixed project sources in the final run:

| Fixture | Status | Files / partial | Types | Functions | Calls | Ambiguous / unmatched call spellings |
|---|---:|---:|---:|---:|---:|---:|
| ExtractionGame (`eg`) | ok | 0 / 0 | 0 | 0 | 0 | 0 / 0 |
| ActionRoguelike (`ar`) | partial | 164 / 7 | 228 | 728 | 2,000 | 151 / 1,522 |
| Character Input (`ves`) | ok | 4 / 0 | 8 | 14 | 30 | 1 / 26 |
| BattleTank (`bt`) | ok | 26 / 0 | 25 | 104 | 184 | 14 / 144 |

`ar` remains `partial` because seven source files contain grammar recovery around complex macro/preprocessor
constructs. Those files and error spans are preserved in `CXX_INDEX.json`/`UNRESOLVED.md`; the 2,000 observed
call expressions are not promoted to resolved targets. `eg` contains no project C++ Source tree at its pinned
commit, so zero is a confirmed scan result for that checkout rather than evidence of C++ semantics.

Passing syntax fixtures establish the stated source observations only. They do not establish semantic accuracy
for every Unreal C++ project.

## Changed implementation surface

- `scripts/cxx_index.py`: precision syntax parser, IR, conservative candidate construction, Markdown renderers.
- `scripts/ue_repo_digest.py`: additive precision scan/output and version 1.19.0.
- `scripts/navigation.py`: links precision documents and labels their semantic boundary.
- `scripts/install_skill.py`: includes the pinned optional requirements in snapshot installs.
- `requirements-cxx.txt`: reproducible parser versions.
- `server/requirements.txt`, `chatgpt-plugin/skills/ue-repo-reader/SKILL.md`: server parser pins and MCP reading guidance.
- `tests/cxx_index_tests.py`, `tests/unit_tests.py`, `tests/regress.py`, `tests/skill_install_tests.py`: tests and navigation coverage.
- `README.md`, `SKILL.md`: install, output and interpretation guidance.
