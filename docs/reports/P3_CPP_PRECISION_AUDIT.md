# P3 C++ precision audit

Date: 2026-11-07

Base commit: `dcb99dc`

Scope: source indexing only; no Unreal Engine, UnrealHeaderTool, compiler, or game-project modification

## Existing implementation

`scripts/ue_repo_digest.py::scan_cpp()` was a reflected-surface convenience index. It searched project
`Source` and one plugin-source level, parsed `*.Build.cs` dependency strings, then inspected only `*.h` files
containing `UCLASS`, `USTRUCT`, `UENUM`, or `UINTERFACE`. Regular C++ classes and functions, every `*.cpp`
body, namespaces, source ranges, overloads, control flow, calls, lambdas, and preprocessor context were absent.

The regex split each reflected type at the next reflected declaration rather than at a parsed C++ body. It
selected only UFUNCTION/UPROPERTY declarations with a small set of Blueprint, RPC, edit, replication, or
config words. Nested macro arguments and complicated declarators could exceed its regex grammar. The output
gave no parse status or provenance, and `cpp/CLASSES.md` correctly told readers to open the source, but the
machine-readable `cpp` object did not distinguish an empty result from unsupported syntax.

The C++ to Blueprint catalog mapping used normalized class and function names. A short-name match could be
useful for navigation, but it did not prove class identity, overload choice, virtual dispatch, or generated
event/RPC behavior. Graph IR preserves saved Blueprint identities where they are available; it does not
supply C++ type resolution. Declaration IR describes saved Blueprint declarations, not native C++ ASTs.

## Accuracy risks confirmed from code

- A project containing only ordinary C++ or implementations in `*.cpp` produced no function-body evidence.
- Calls were not indexed at all, so there was no way to separate a proven target from a same-name guess.
- The previous type/function records had no line range or byte span for source verification.
- `WITH_EDITOR` and other conditional branches had no visible “not evaluated” state.
- `_Implementation` and `_Validate` definitions were not related to reflected declarations, even as candidates.
- `*.generated.h`, generated declarations, and UnrealHeaderTool output were unavailable but not represented as
  an explicit precision-index boundary.
- Module dependencies were lexical string matches. UBT execution and target rules were not observed.

These findings come from direct inspection of the implementation and new hand-authored counterexamples. They
do not treat the old regex output or the new parser's own output as an independent semantic oracle.

## Parser choice

| Approach | What it can establish | Main cost / boundary | Decision |
|---|---|---|---|
| Existing regex | A narrow reflected header surface | Loses C++ grammar, bodies, spans, and calls | Retained only for API/output compatibility |
| tree-sitter-cpp | Concrete syntax, error recovery, byte/line spans, declarations and body expressions | No preprocessor execution, type system, overload lookup, templates, generated code, or virtual dispatch | Implemented as a syntax index |
| Clang AST | Typed declarations, overload selection and many direct call targets under a real compile configuration | Requires compile commands, UE headers/toolchain/defines and platform-specific generated headers; incomplete projects still fail | Kept as a separate future semantic resolver |

Pinning `tree-sitter==0.25.2` and `tree-sitter-cpp==0.23.4` makes the Linux parser reproducible. Unreal macros
and export macros can make otherwise valid source appear malformed to the grammar. The implementation records
their exact source ranges, masks only those bytes with spaces for parsing, and retains original byte offsets.
This is parser preparation, not preprocessor or UnrealHeaderTool emulation.

## Accuracy contract

The precision index is schema 1. Direct source facts use `syntax_observed`; unresolved types, call targets,
  preprocessor outcomes, and unavailable parser results use `unresolved`. `semantic_resolved` is reserved for a
future typed engine. The tree-sitter implementation emits a `semantic_resolved_count` of zero.

Each symbol/body observation carries its source file, line range, symbol name, qualified spelling when it can
be formed from syntax, parser name, resolution status, byte/line source span, and issues. A unique spelling
candidate remains an unresolved call target. Partial syntax trees remain in the output with file errors and a
top-level `partial` status instead of being reported as complete.

## Verification status

- **Analyzed:** previous regex paths, current C++/Blueprint name mapping, new syntax schema and fallback.
- **Independently tested at source-fixture level:** expected names, spans, ambiguity, macros, invalid source,
  preprocessor boundaries, Build.cs/Target.cs lexical observations, and output files were authored separately
  from parser output.
- **Regression scope:** the repository's fixed-project regression is reported in the results document.
- **Not independently verified:** typed overload targets, engine/generated declarations, compiled RPC behavior,
  template instantiation, virtual dispatch, or whole-project Unreal build correctness.
